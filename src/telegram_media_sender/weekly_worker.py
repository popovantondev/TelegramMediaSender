"""Sequential execution primitives for the weekly upload mode."""
from __future__ import annotations

import asyncio
import socket
import threading
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QThread, Signal

from .weekly_journal import FileChangedError, UncertainReceiptError, WeeklyJournal
from .publication_plan_import import PublicationPlanImportError, revalidate_publication_item
from .upload_limits import APP_MAX_FILE_BYTES, UploadLimitError
from .weekly_plan import ItemKind, UploadMode, WeeklyPlanItem, WeeklyUploadPlan


class WeeklyStop(RuntimeError):
    def __init__(self, immediate: bool = False):
        super().__init__("Weekly upload was stopped by the user.")
        self.immediate = immediate


class WeeklyQueueRunner:
    """Execute exactly one immutable plan, persisting each result before advancing."""

    def __init__(self, plan: WeeklyUploadPlan, journal: WeeklyJournal, transport,
                 *, progress: Callable[[dict], None] | None = None,
                 stop_event: threading.Event | None = None,
                 reconcile: Callable[[int, list], object] | None = None,
                 confirmation: Callable[[int, list], object] | None = None,
                 sleep: Callable[[float], object] = asyncio.sleep,
                 max_file_bytes: int = APP_MAX_FILE_BYTES):
        self.plan = plan
        self.journal = journal
        self.transport = transport
        self.progress = progress or (lambda _value: None)
        self.stop_event = stop_event or threading.Event()
        self.reconcile = reconcile
        self.confirmation = confirmation
        self.sleep = sleep
        self.max_file_bytes = max_file_bytes
        self._immediate = False

    def request_stop(self, immediate: bool = False) -> None:
        self._immediate = self._immediate or immediate
        self.stop_event.set()

    async def _sleep_interruptibly(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.stop_event.is_set():
                raise WeeklyStop(self._immediate)
            await self.sleep(min(1.0, end - time.monotonic()))

    async def _send_one(self, item: WeeklyPlanItem, row, random_id: int, run_id: int) -> int:
        if item.kind is ItemKind.TEXT:
            return await self.transport.send_text(item.text or "", random_id)
        if item.path is None:
            raise ValueError(f"File item has no path: {item.key}")
        if self.plan.publication_project_id:
            try:
                await asyncio.to_thread(revalidate_publication_item, self.plan.root,
                                        item.relative_path or "", item.size, item.sha256 or "")
            except PublicationPlanImportError as exc:
                raise FileChangedError(str(exc)) from exc
        current = await asyncio.to_thread(self.journal.fingerprint, item.path, use_cache=False)
        if (current.size, current.mtime_ns, current.sha256) != (
                row["file_size"], row["mtime_ns"], row["sha256"]):
            raise FileChangedError(f"File changed before upload: {item.relative_path}")
        before = item.path.stat()
        if (before.st_size, before.st_mtime_ns) != (row["file_size"], row["mtime_ns"]):
            raise FileChangedError(f"File changed before upload: {item.relative_path}")

        def on_progress(current_bytes, total_bytes):
            self.progress({"phase": "uploading", "item": item,
                           "run_id": run_id, "item_key": item.key, "status": "sending",
                           "current_bytes": current_bytes, "current_total_bytes": total_bytes})

        return await self.transport.send_file(item.path, random_id, progress=on_progress)

    async def _send_reconciled_single(self, item: WeeklyPlanItem, row, run_id: int):
        """Safely finish one album member after chat history resolved its siblings."""
        attempt_id, random_id = self.journal.begin_attempt(row["item_id"])
        delays = (2, 5, 10, 30, 60)
        delay_index = 0
        while True:
            if self.stop_event.is_set():
                self.journal.mark_status(row["item_id"], "pending")
                self.journal.set_run_state(run_id, "paused")
                raise WeeklyStop(self._immediate)
            try:
                message_id = await self._send_one(item, row, random_id, run_id)
                self.journal.mark_sent(row["item_id"], attempt_id, message_id)
                return "sent", message_id
            except asyncio.CancelledError:
                self.journal.mark_uncertain(row["item_id"], attempt_id,
                                            "Upload interrupted before confirmation.")
                self.journal.set_run_state(run_id, "paused")
                raise WeeklyStop(True)
            except FileChangedError as error:
                self.journal.mark_error(row["item_id"], attempt_id, str(error))
                self.journal.set_run_state(run_id, "failed")
                raise
            except Exception as error:
                flood = type(error).__name__ in {"FloodWaitError", "SlowModeWaitError"}
                network = isinstance(error, (ConnectionError, TimeoutError, OSError,
                                             socket.gaierror, UncertainReceiptError))
                if not flood and not network:
                    self.journal.mark_error(row["item_id"], attempt_id, str(error))
                    self.journal.set_run_state(run_id, "failed")
                    raise
                self.journal.mark_uncertain(row["item_id"], attempt_id, str(error))
                if flood:
                    delay = max(1, int(getattr(error, "seconds", 1)))
                    phase = "waiting_flood"
                else:
                    delay = delays[min(delay_index, len(delays) - 1)]
                    delay_index = min(delay_index + 1, len(delays) - 1)
                    phase = "waiting_network"
                self.progress({"phase": phase, "retry_seconds": delay, "item": item})
                try:
                    await self._sleep_interruptibly(delay)
                except WeeklyStop:
                    self.journal.set_run_state(run_id, "paused")
                    raise
                if network:
                    await self.transport.reconnect()
                    if self.reconcile is not None:
                        result = self.reconcile(run_id, self.journal.run_items(run_id))
                        if asyncio.iscoroutine(result):
                            await result
                    refreshed = next((candidate for candidate in self.journal.run_items(run_id)
                                      if candidate["item_id"] == row["item_id"]), None)
                    if refreshed and refreshed["status"] in {"sent", "skipped"}:
                        return refreshed["status"], refreshed["message_id"]
                attempt_id, random_id = self.journal.begin_attempt(row["item_id"])

    async def _send_media_operations(self, run_id: int, rows: list,
                                     items_by_key: dict[str, WeeklyPlanItem],
                                     counts: dict[str, int]) -> dict[str, int]:
        """Send media plans by their persisted operation boundaries.

        Only complete pending subtitle batches are albums. If recovery leaves a
        partially confirmed operation, remaining items are sent individually.
        """
        grouped: list[list] = []
        for row in rows:
            key = row["operation_key"] or row["item_key"]
            if grouped and (grouped[-1][0]["operation_key"] or grouped[-1][0]["item_key"]) == key:
                grouped[-1].append(row)
            else:
                grouped.append([row])

        total_bytes = sum(row["file_size"] for row in rows if row["kind"] == ItemKind.FILE.value)
        confirmed_bytes = sum(row["file_size"] for row in rows if row["kind"] == ItemKind.FILE.value
                              and (row["status"] == "sent" or row["error"] == "found_in_chat"))
        self.progress({"phase": "uploading", "run_id": run_id, "total": len(rows),
                       "total_bytes": total_bytes, "confirmed_bytes": confirmed_bytes})
        delays = (2, 5, 10, 30, 60)
        for operation_rows in grouped:
            pending = [row for row in operation_rows if row["status"] not in {"sent", "skipped"}]
            if not pending:
                counts["skipped"] += sum(row["status"] == "skipped" for row in operation_rows)
                continue
            operation_key = pending[0]["operation_key"] or pending[0]["item_key"]
            # A subset that survived an interrupted/partially reviewed album
            # must never be resent as a fresh all-or-nothing batch.
            album = len(pending) > 1 and len(pending) == len(operation_rows)
            items = [items_by_key[row["item_key"]] for row in pending]
            if any(item.kind is not ItemKind.FILE for item in items):
                raise RuntimeError("Grouped Telegram operations may contain files only.")
            if album and not callable(getattr(self.transport, "send_album", None)):
                raise RuntimeError("The Telegram transport does not support durable albums.")
            if self.stop_event.is_set():
                self.journal.set_run_state(run_id, "paused")
                raise WeeklyStop(self._immediate)

            started = (self.journal.begin_operation([row["item_id"] for row in pending], operation_key)
                       if album else [self.journal.begin_attempt(pending[0]["item_id"])])
            attempts = [(row["item_id"], pair[0]) for row, pair in zip(pending, started)]
            random_ids = [pair[1] for pair in started]
            uncertain = False
            delay_index = 0
            while True:
                try:
                    if self.stop_event.is_set():
                        self.journal.mark_operation_uncertain(attempts, "Stopped before Telegram confirmed the operation.")
                        self.journal.set_run_state(run_id, "paused")
                        raise WeeklyStop(self._immediate)
                    for item, row in zip(items, pending):
                        if item.path is None:
                            raise ValueError(f"File item has no path: {item.key}")
                        if self.plan.publication_project_id:
                            try:
                                await asyncio.to_thread(revalidate_publication_item, self.plan.root,
                                    item.relative_path or "", item.size, item.sha256 or "")
                            except PublicationPlanImportError as exc:
                                raise FileChangedError(str(exc)) from exc
                        current = await asyncio.to_thread(self.journal.fingerprint, item.path, use_cache=False)
                        if (current.size, current.mtime_ns, current.sha256) != (
                                row["file_size"], row["mtime_ns"], row["sha256"]):
                            raise FileChangedError(f"File changed before upload: {item.relative_path}")
                    self.progress({"phase": "uploading", "run_id": run_id, "item": items[0],
                                   "item_key": items[0].key, "status": "sending",
                                   "current_bytes": 0, "current_total_bytes": sum(i.size for i in items)})
                    if album:
                        last_progress = {"time": 0.0}

                        def album_progress(file_index, current_bytes, file_total):
                            now = time.monotonic()
                            if (now - last_progress["time"] < 0.15
                                    and current_bytes < file_total):
                                return
                            last_progress["time"] = now
                            item = items[file_index]
                            value = min(max(int(current_bytes), 0), item.size)
                            self.progress({"phase": "uploading", "run_id": run_id, "item": item,
                                           "item_key": item.key, "status": "sending",
                                           "current_bytes": value, "current_total_bytes": item.size})

                        receipt_ids = await self.transport.send_album(
                            [item.path for item in items], random_ids, progress=album_progress)
                    else:
                        receipt_ids = [await self._send_one(items[0], pending[0], random_ids[0], run_id)]
                    if len(receipt_ids) != len(pending):
                        raise RuntimeError("Telegram returned an incomplete operation receipt.")
                    self.journal.mark_operation_sent([
                        (row["item_id"], attempt_id, message_id)
                        for row, (attempt_id, _), message_id in zip(pending, started, receipt_ids)
                    ])
                    counts["sent"] += len(pending)
                    confirmed_bytes += sum(row["file_size"] for row in pending)
                    for item, message_id in zip(items, receipt_ids):
                        self.progress({"phase": "uploading", "run_id": run_id, "item": item,
                                       "item_key": item.key, "status": "sent", "message_id": message_id,
                                       "current_bytes": item.size, "current_total_bytes": item.size,
                                       "confirmed_bytes": confirmed_bytes, "total_bytes": total_bytes})
                    break
                except WeeklyStop:
                    raise
                except asyncio.CancelledError:
                    self.journal.mark_operation_uncertain(attempts, "Upload interrupted before confirmation.")
                    self.journal.set_run_state(run_id, "paused")
                    raise WeeklyStop(True)
                except FileChangedError as error:
                    for item_id, attempt_id in attempts:
                        self.journal.mark_error(item_id, attempt_id, str(error))
                    self.journal.set_run_state(run_id, "failed")
                    self.progress({"phase": "failed", "run_id": run_id, "item": items[0],
                                   "item_key": items[0].key, "status": "error", "error": str(error)})
                    raise
                except Exception as error:
                    is_flood = type(error).__name__ in {"FloodWaitError", "SlowModeWaitError"}
                    is_network = isinstance(error, (ConnectionError, TimeoutError, OSError,
                                                    socket.gaierror, UncertainReceiptError))
                    if not is_flood and not is_network:
                        for item_id, attempt_id in attempts:
                            self.journal.mark_error(item_id, attempt_id, str(error))
                        self.journal.set_run_state(run_id, "failed")
                        self.progress({"phase": "failed", "run_id": run_id, "item": items[0],
                                       "item_key": items[0].key, "status": "error", "error": str(error)})
                        raise
                    if not uncertain:
                        counts["uncertain"] += len(pending)
                        uncertain = True
                    self.journal.mark_operation_uncertain(attempts, str(error))
                    if is_flood:
                        delay = max(1, int(getattr(error, "seconds", 1)))
                        phase = "waiting_flood"
                    else:
                        delay = delays[min(delay_index, len(delays) - 1)]
                        phase = "waiting_network"
                        delay_index = min(delay_index + 1, len(delays) - 1)
                    self.progress({"phase": phase, "retry_seconds": delay, "item": items[0]})
                    await self._sleep_interruptibly(delay)
                    if is_network:
                        await self.transport.reconnect()
                        if self.reconcile is not None:
                            result = self.reconcile(run_id, self.journal.run_items(run_id))
                            if asyncio.iscoroutine(result):
                                await result
                        refreshed = {row["item_key"]: row for row in self.journal.run_items(run_id)}
                        refreshed_rows = [refreshed[item.key] for item in items]
                        resolved = [row["status"] in {"sent", "skipped"} for row in refreshed_rows]
                        if all(resolved):
                            counts["uncertain"] = max(0, counts["uncertain"] - len(pending))
                            counts["sent"] += sum(row["status"] == "sent" for row in refreshed_rows)
                            counts["skipped"] += sum(row["status"] == "skipped" for row in refreshed_rows)
                            confirmed_bytes += sum(row["file_size"] for row in refreshed_rows)
                            break
                        if any(resolved):
                            # Atomic albums cannot be replayed partially. Persist
                            # the unresolved members as single-file operations.
                            counts["sent"] += sum(row["status"] == "sent" for row in refreshed_rows)
                            counts["skipped"] += sum(row["status"] == "skipped" for row in refreshed_rows)
                            resolved_bytes = sum(row["file_size"] for row, done in zip(refreshed_rows, resolved)
                                                 if done)
                            confirmed_bytes += resolved_bytes
                            counts["uncertain"] = max(0, counts["uncertain"] - sum(resolved))
                            for index, (row, item) in enumerate(zip(pending, items)):
                                if resolved[index]:
                                    continue
                                status, message_id = await self._send_reconciled_single(item, row, run_id)
                                if status == "sent":
                                    counts["sent"] += 1
                                    confirmed_bytes += row["file_size"]
                                else:
                                    counts["skipped"] += 1
                                counts["uncertain"] = max(0, counts["uncertain"] - 1)
                            break
                    started = (self.journal.begin_operation([row["item_id"] for row in pending], operation_key)
                               if album else [self.journal.begin_attempt(pending[0]["item_id"])])
                    attempts = [(row["item_id"], pair[0]) for row, pair in zip(pending, started)]
                    random_ids = [pair[1] for pair in started]
        self.journal.set_run_state(run_id, "completed")
        self.progress({"phase": "completed", **counts})
        return counts

    async def run(self) -> dict[str, int]:
        total_plan_bytes = self.plan.total_bytes
        self.progress({"phase": "preparing", "items": len(self.plan.items), "total_bytes": total_plan_bytes})
        fingerprints = {}
        for item in self.plan.items:
            if item.kind is ItemKind.FILE:
                if item.size > self.max_file_bytes:
                    raise UploadLimitError(item.name or item.key, item.size, self.max_file_bytes)
                if not item.path:
                    raise ValueError(f"File item has no path: {item.key}")
                fingerprints[item.key] = await asyncio.to_thread(
                    self.journal.fingerprint, item.path,
                    # Re-read every source before freezing this queue. A cache
                    # keyed by size/mtime cannot detect a replacement that
                    # preserves both metadata values.
                    use_cache=False)
                if ((fingerprints[item.key].size, fingerprints[item.key].mtime_ns) != (item.size, item.mtime_ns)
                        or (self.plan.publication_project_id
                            and fingerprints[item.key].sha256 != item.sha256)):
                    raise FileChangedError(f"File changed since the plan was scanned: {item.relative_path}")
        run_id = self.journal.save_plan(self.plan, fingerprints)
        counts = {"sent": 0, "skipped": 0, "error": 0, "uncertain": 0}
        items_by_key = {item.key: item for item in self.plan.items}
        with self.journal.executor_lock():
            self.progress({"phase": "reconciling", "run_id": run_id})
            rows = self.journal.run_items(run_id)
            self.journal.resume_interrupted(run_id)
            if self.reconcile is not None:
                result = self.reconcile(run_id, rows)
                if asyncio.iscoroutine(result):
                    await result
                rows = self.journal.run_items(run_id)
            if self.confirmation is not None:
                accepted = self.confirmation(run_id, rows)
                if asyncio.iscoroutine(accepted):
                    accepted = await accepted
                if not accepted:
                    self.journal.set_run_state(run_id, "paused")
                    raise WeeklyStop(False)
            if self.plan.publication_project_id:
                try:
                    for item in self.plan.items:
                        if item.kind is ItemKind.FILE:
                            await asyncio.to_thread(
                                revalidate_publication_item, self.plan.root,
                                item.relative_path or "", item.size, item.sha256 or "")
                except PublicationPlanImportError as error:
                    self.journal.set_run_state(run_id, "failed")
                    self.progress({"phase": "failed", "run_id": run_id,
                                   "error": str(error)})
                    raise FileChangedError(str(error)) from error
            if self.plan.mode is UploadMode.MEDIA_GROUPS:
                self.journal.set_run_state(run_id, "sending")
                return await self._send_media_operations(
                    run_id, self.journal.run_items(run_id), items_by_key, counts)
            self.journal.set_run_state(run_id, "sending")
            total_bytes = sum(row["file_size"] for row in rows if row["kind"] == ItemKind.FILE.value)
            confirmed_bytes = sum(row["file_size"] for row in rows
                                  if row["kind"] == ItemKind.FILE.value and
                                  (row["status"] == "sent" or row["error"] == "found_in_chat"))
            self.progress({"phase": "uploading", "run_id": run_id, "total": len(rows),
                           "total_bytes": total_bytes, "confirmed_bytes": confirmed_bytes})
            for row in rows:
                item = items_by_key.get(row["item_key"])
                if item is None or row["status"] == "sent":
                    continue
                if row["status"] == "skipped":
                    if row["error"] == "found_in_chat":
                        counts["skipped"] += 1
                    continue
                if self.stop_event.is_set():
                    self.journal.mark_status(row["item_id"], "pending")
                    self.journal.set_run_state(run_id, "paused")
                    raise WeeklyStop(self._immediate)
                attempt_id, random_id = self.journal.begin_attempt(row["item_id"])
                self.progress({"phase": "uploading", "run_id": run_id, "item": item,
                               "item_key": item.key, "status": "sending",
                               "current_bytes": 0, "current_total_bytes": item.size})
                uncertain = False
                network_delay_index = 0
                network_delays = (2, 5, 10, 30, 60)
                request_started = False
                while True:
                    if self.stop_event.is_set():
                        if not uncertain:
                            self.journal.mark_status(row["item_id"], "pending")
                        self.journal.set_run_state(run_id, "paused")
                        raise WeeklyStop(self._immediate)
                    try:
                        request_started = True
                        message_id = await self._send_one(item, row, random_id, run_id)
                    except asyncio.CancelledError:
                        if request_started:
                            self.journal.mark_uncertain(
                                row["item_id"], attempt_id,
                                "Upload interrupted before confirmation.")
                            self.progress({"phase": "uploading", "run_id": run_id,
                                           "item_key": item.key, "status": "uncertain", "item": item})
                        else:
                            self.journal.mark_status(row["item_id"], "pending")
                        self.journal.set_run_state(run_id, "paused")
                        raise
                    except FileChangedError as error:
                        self.journal.mark_error(row["item_id"], attempt_id, str(error))
                        counts["error"] += 1
                        self.journal.set_run_state(run_id, "failed")
                        self.progress({"phase": "failed", "run_id": run_id, "item": item,
                                       "item_key": item.key, "status": "error", "error": str(error)})
                        raise
                    except Exception as error:
                        error_name = type(error).__name__
                        flood_wait = error_name in {"FloodWaitError", "SlowModeWaitError"}
                        network_error = isinstance(error, (ConnectionError, TimeoutError,
                                                           OSError, socket.gaierror,
                                                           UncertainReceiptError))
                        if not flood_wait and not network_error:
                            self.journal.mark_error(row["item_id"], attempt_id, str(error))
                            counts["error"] += 1
                            self.journal.set_run_state(run_id, "failed")
                            self.progress({"phase": "failed", "run_id": run_id, "item": item,
                                           "item_key": item.key, "status": "error", "error": str(error)})
                            raise

                        self.journal.mark_uncertain(row["item_id"], attempt_id, str(error))
                        self.progress({"phase": "uploading", "run_id": run_id, "item": item,
                                       "item_key": item.key, "status": "uncertain"})
                        if not uncertain:
                            counts["uncertain"] += 1
                            uncertain = True

                        if flood_wait:
                            delay = max(1, int(getattr(error, "seconds", 1)))
                            self.progress({"phase": "waiting_flood", "retry_seconds": delay,
                                           "item": item})
                            try:
                                await self._sleep_interruptibly(delay)
                            except WeeklyStop:
                                self.journal.set_run_state(run_id, "paused")
                                raise
                            attempt_id, random_id = self.journal.begin_attempt(row["item_id"])
                            request_started = False
                            self.progress({"phase": "uploading", "run_id": run_id, "item": item,
                                           "item_key": item.key, "status": "sending",
                                           "current_bytes": 0, "current_total_bytes": item.size})
                            continue

                        # A transport failure can mean Telegram received the request
                        # but its acknowledgement was lost. Reconnect and reconcile
                        # chat history before retrying with the same persisted ID.
                        while True:
                            delay = network_delays[network_delay_index]
                            self.progress({"phase": "waiting_network", "retry_seconds": delay,
                                           "item": item})
                            try:
                                await self._sleep_interruptibly(delay)
                                await self.transport.reconnect()
                                if self.reconcile is not None:
                                    result = self.reconcile(run_id, self.journal.run_items(run_id))
                                    if asyncio.iscoroutine(result):
                                        await result
                                refreshed = next((candidate for candidate in self.journal.run_items(run_id)
                                                  if candidate["item_id"] == row["item_id"]), None)
                                if (refreshed and refreshed["status"] == "skipped"
                                        and refreshed["error"] == "found_in_chat"):
                                    counts["uncertain"] = max(0, counts["uncertain"] - 1)
                                    counts["skipped"] += 1
                                    if item.kind is ItemKind.FILE:
                                        confirmed_bytes += row["file_size"]
                                    self.progress({"phase": "reconciling", "item": item,
                                                   "run_id": run_id, "item_key": item.key,
                                                   "status": "skipped", "found_in_chat": item.key,
                                                   "confirmed_bytes": confirmed_bytes,
                                                   "total_bytes": total_bytes})
                                    break
                                attempt_id, random_id = self.journal.begin_attempt(row["item_id"])
                                request_started = False
                                self.progress({"phase": "uploading", "run_id": run_id, "item": item,
                                               "item_key": item.key, "status": "sending",
                                               "current_bytes": 0, "current_total_bytes": item.size})
                                break
                            except asyncio.CancelledError:
                                self.journal.set_run_state(run_id, "paused")
                                raise
                            except WeeklyStop:
                                self.journal.set_run_state(run_id, "paused")
                                raise
                            except Exception as recovery_error:
                                recovery_flood = type(recovery_error).__name__ in {
                                    "FloodWaitError", "SlowModeWaitError"}
                                recovery_network = isinstance(
                                    recovery_error,
                                    (ConnectionError, TimeoutError, OSError, socket.gaierror))
                                if not recovery_flood and not recovery_network:
                                    self.journal.set_run_state(run_id, "failed")
                                    self.progress({"phase": "failed", "run_id": run_id, "item": item,
                                                   "item_key": item.key, "status": "error",
                                                   "error": str(recovery_error)})
                                    raise
                                if recovery_flood:
                                    delay = max(1, int(getattr(recovery_error, "seconds", 1)))
                                    phase = "waiting_flood"
                                else:
                                    network_delay_index = min(network_delay_index + 1,
                                                              len(network_delays) - 1)
                                    delay = network_delays[network_delay_index]
                                    phase = "waiting_network"
                                self.progress({"phase": phase, "retry_seconds": delay,
                                               "item": item})
                                try:
                                    await self._sleep_interruptibly(delay)
                                except WeeklyStop:
                                    self.journal.set_run_state(run_id, "paused")
                                    raise
                                # Retry the recovery phase. Never resend until the
                                # history check has succeeded.
                        if refreshed and refreshed["status"] == "skipped" and refreshed["error"] == "found_in_chat":
                            break
                        continue
                    else:
                        # Persist success before reporting it or starting the next item.
                        self.journal.mark_sent(row["item_id"], attempt_id, message_id)
                        if uncertain:
                            counts["uncertain"] = max(0, counts["uncertain"] - 1)
                        counts["sent"] += 1
                        if item.kind is ItemKind.FILE:
                            confirmed_bytes += row["file_size"]
                        self.progress({"phase": "uploading", "item": item,
                                       "item_key": item.key, "run_id": run_id,
                                       "status": "sent", "message_id": message_id,
                                       "completed_items": counts["sent"],
                                       "current_bytes": item.size,
                                       "current_total_bytes": item.size,
                                       "confirmed_bytes": confirmed_bytes,
                                       "total_bytes": total_bytes})
                        break
                if self.stop_event.is_set():
                    self.journal.set_run_state(run_id, "paused")
                    raise WeeklyStop(self._immediate)
            self.progress({"phase": "completed", **counts})
            self.journal.set_run_state(run_id, "completed")
        return counts


class WeeklyUploadThread(QThread):
    """Own the Telegram session and sequential runner away from the Qt UI thread."""

    progress = Signal(object)
    completed = Signal(object)
    cancelled = Signal(bool)
    failed = Signal(str)
    input_requested = Signal(str, bool, object)
    match_review = Signal(object, object)
    confirmation_ready = Signal(object)

    def __init__(self, plan: WeeklyUploadPlan, profile: dict, profile_store, storage,
                 language: str = "en", max_file_bytes: int = APP_MAX_FILE_BYTES):
        super().__init__()
        self.plan = plan
        self.profile = profile
        self.profile_store = profile_store
        self.storage = storage
        self.language = language
        self.max_file_bytes = max_file_bytes
        self._stop_event = threading.Event()
        self._immediate = False
        self._loop = None
        self._task = None
        self._confirmation_future = None

    def request_stop(self, immediate: bool = False):
        self._immediate = self._immediate or immediate
        self._stop_event.set()
        if immediate and self._loop and self._task:
            self._loop.call_soon_threadsafe(self._task.cancel)

    def check_stopped(self):
        if self._stop_event.is_set():
            raise WeeklyStop(self._immediate)

    def ask_input(self, prompt: str, secret: bool) -> str:
        event = threading.Event()
        answer = {"value": ""}
        self.input_requested.emit(prompt, secret, (event, answer))
        if not event.wait(300) or not answer["value"]:
            raise RuntimeError("Telegram sign-in was cancelled.")
        return answer["value"]

    def ask_match_review(self, conflicts: list[dict]):
        event = threading.Event()
        answer = {"value": None}
        self.match_review.emit(conflicts, (event, answer))
        if not event.wait(300) or answer["value"] is None:
            raise RuntimeError("Chat-history matches were not reviewed.")
        return answer["value"]

    def confirm_upload(self, accepted: bool):
        if self._loop and self._confirmation_future:
            self._loop.call_soon_threadsafe(
                lambda: (not self._confirmation_future.done()) and self._confirmation_future.set_result(bool(accepted)))

    def run(self):
        try:
            with self.storage.telegram_operation_lock():
                result = asyncio.run(self._work())
            self.completed.emit(result)
        except WeeklyStop as stop:
            self.cancelled.emit(stop.immediate)
        except asyncio.CancelledError:
            self.cancelled.emit(True)
        except UploadLimitError as error:
            from .i18n import tr
            limit_mb = max(1, error.limit // (1024 * 1024))
            self.failed.emit(tr("File exceeds the Telegram upload limit: {name} ({limit} MB).",
                                self.language, name=error.name, limit=limit_mb))
        except Exception as error:
            self.failed.emit(str(error))

    async def _work(self):
        from dataclasses import replace
        from telethon import TelegramClient, utils
        from .mac_sleep import IdleSleepInhibitor
        from .telegram_transport import TelethonWeeklyTransport
        from .telegram_auth import connect_and_authorize

        if not self.profile or not self.profile.get("api_id") or not self.profile.get("api_hash"):
            raise RuntimeError("Select a Telegram profile with API ID and API Hash.")
        session = self.profile_store.session_path(self.profile, self.storage.root)
        client = TelegramClient(str(session), int(self.profile["api_id"]), self.profile["api_hash"])
        try:
            await connect_and_authorize(client, self.profile, self.ask_input, self.language,
                                        self.check_stopped)
            me = await client.get_me()
            from .upload_limits import account_upload_limit
            self.max_file_bytes = await account_upload_limit(client, premium=bool(getattr(me, "premium", False)))
            target_entity = await client.get_entity(self.plan.chat_id or self.plan.chat_title)
            if not getattr(me, "id", None) or not getattr(target_entity, "id", None):
                raise RuntimeError("Telegram account or chat could not be verified.")
            active_plan = replace(self.plan, account_id=int(me.id),
                                  chat_id=utils.get_peer_id(target_entity))
            transport = TelethonWeeklyTransport(client, target_entity)

            async def reconcile(run_id, rows):
                self.progress.emit({"phase": "reconciling", "run_id": run_id})
                wanted_text = {item.text for item in active_plan.items
                               if item.kind is ItemKind.TEXT and item.text}
                wanted_files = {(item.name, item.size) for item in active_plan.items
                                if item.kind is ItemKind.FILE and item.name}
                existing_text = {}
                existing_files = {}
                # Telethon paginates this iterator. Keep only candidates relevant
                # to the immutable plan, and do not silently ignore older history.
                scanned = 0
                async for message in client.iter_messages(target_entity, limit=None):
                    self.check_stopped()
                    scanned += 1
                    text = getattr(message, "message", None)
                    if text in wanted_text:
                        existing_text.setdefault(text, []).append(int(message.id))
                    media_file = getattr(message, "file", None)
                    name, size = getattr(media_file, "name", None), getattr(media_file, "size", None)
                    if name and type(size) is int and (name, size) in wanted_files:
                        existing_files.setdefault((name, size), []).append(int(message.id))
                    if scanned % 500 == 0:
                        self.progress.emit({"phase": "reconciling", "scanned_messages": scanned})
                item_candidates = {}
                reserved_owners = {
                    int(row["message_id"]): row["item_key"]
                    for row in rows
                    if row["message_id"] is not None and row["status"] in {"sent", "skipped"}
                }
                for item in active_plan.items:
                    candidates = (existing_text.get(item.text, []) if item.kind is ItemKind.TEXT
                                  else existing_files.get((item.name, item.size), []))
                    item_candidates[item.key] = candidates
                conflicts = []
                matches = {}
                for item in active_plan.items:
                    candidates = item_candidates.get(item.key, [])
                    unassigned_rows = [r for r in rows if r["item_key"] == item.key and r["status"] not in {"sent", "skipped"}]
                    # A filename/size or text match is only a hint, even when
                    # unique. The user must explicitly bind it to this item.
                    if candidates and unassigned_rows:
                        selectable = [message_id for message_id in candidates
                                      if message_id not in reserved_owners or reserved_owners[message_id] == item.key]
                        conflicts.append({"key": item.key, "name": item.name or item.text or item.key,
                                          "relative_path": item.relative_path or "",
                                          "message_ids": selectable, "kind": item.kind.value})
                choices = {}
                if conflicts:
                    self.progress.emit({"phase": "reconciling", "ambiguous": len(conflicts)})
                    choices = await asyncio.to_thread(self.ask_match_review, conflicts)
                    if choices == "cancel":
                        WeeklyJournal(self.storage.root).set_run_state(run_id, "paused")
                        raise WeeklyStop(False)
                matches.update({key: message_id for key, message_id in choices.items() if message_id is not None})
                journal = WeeklyJournal(self.storage.root)
                item_lookup = {i.key: i for i in active_plan.items}
                used_ids = set(reserved_owners)
                for row in rows:
                    if row["status"] in {"sent", "skipped"}:
                        continue
                    item = item_lookup.get(row["item_key"])
                    if item is None:
                        continue
                    message_id = matches.get(item.key)
                    if message_id is not None:
                        if message_id in used_ids:
                            raise RuntimeError("One Telegram message cannot match more than one plan item.")
                        journal.mark_found_in_chat(row["item_id"], message_id)
                        used_ids.add(message_id)
                        self.progress.emit({"phase": "reconciling", "run_id": run_id,
                                            "item_key": item.key, "status": "skipped",
                                            "found_in_chat": item.key})

            async def confirm_after_check(run_id, rows):
                self._confirmation_future = asyncio.get_running_loop().create_future()
                self.progress.emit({"phase": "awaiting_confirmation", "run_id": run_id})
                found_rows = [row for row in rows if row["status"] == "skipped" and row["error"] == "found_in_chat"]
                for row in rows:
                    state = row["status"]
                    if state == "sending":
                        state = "uncertain"
                    self.progress.emit({"phase": "reconciling", "run_id": run_id,
                                        "item_key": row["item_key"], "status": state})
                pending_rows = [row for row in rows if row["status"] not in {"sent", "skipped"}]
                report = {
                    "run_id": run_id,
                    "found_in_chat": len(found_rows),
                    "pending": len(pending_rows),
                    "pending_files": sum(row["kind"] == ItemKind.FILE.value for row in pending_rows),
                    "pending_bytes": sum(row["file_size"] for row in pending_rows
                                         if row["kind"] == ItemKind.FILE.value),
                }
                self.confirmation_ready.emit({"plan": active_plan, "report": report})
                return await self._confirmation_future

            runner = WeeklyQueueRunner(active_plan, WeeklyJournal(self.storage.root), transport,
                                       progress=self.progress.emit, stop_event=self._stop_event,
                                       reconcile=reconcile, confirmation=confirm_after_check,
                                       max_file_bytes=self.max_file_bytes)
            self._loop = asyncio.get_running_loop()
            try:
                with IdleSleepInhibitor():
                    self._task = asyncio.create_task(runner.run())
                    return await self._task
            except asyncio.CancelledError:
                raise WeeklyStop(True)
        finally:
            await client.disconnect()
