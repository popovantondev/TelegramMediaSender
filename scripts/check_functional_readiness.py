"""Offline acceptance probes: temporary files, fake Telegram, no user credentials.

Run with .venv/bin/python scripts/check_functional_readiness.py.
Exit 1 means an acceptance criterion failed. JSON includes observed behavior.
These probes deliberately cover gaps beyond the existing unit suite.
"""
import asyncio
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QTreeWidgetItemIterator
from telegram_media_sender.gui import MediaSenderWindow
from telegram_media_sender.storage import SenderStorage
from telegram_media_sender.weekly_journal import WeeklyJournal
from telegram_media_sender.weekly_plan import scan_weekly_folder, build_weekly_plan
from telegram_media_sender.weekly_worker import WeeklyQueueRunner, WeeklyStop


class Transport:
    def __init__(self):
        self.sent = []

    async def send_text(self, text, random_id):
        self.sent.append(("text", text, random_id))
        return len(self.sent) + 100

    async def send_file(self, path, random_id, progress=None):
        self.sent.append(("file", path.name, random_id))
        if progress:
            progress(path.stat().st_size, path.stat().st_size)
        return len(self.sent) + 100

    async def reconnect(self):
        pass


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        folder = root / "study"
        day = folder / "Неделя 1" / "2026-08-03"
        day.mkdir(parents=True)
        (day / "Лекция 1.mp4").write_bytes(b"first")
        (day / "Лекция 2.mp4").write_bytes(b"second")
        scan = scan_weekly_folder(folder)
        yield root, scan, build_weekly_plan(scan)


@contextmanager
def window_fixture():
    with fixture() as (root, scan, plan):
        settings_file = root / "settings.ini"
        settings = QSettings(str(settings_file), QSettings.Format.IniFormat)
        settings.setValue("weekly/root", str(root / "missing"))
        settings.sync()
        window = MediaSenderWindow(language="ru", persist_state=False,
                                   storage=SenderStorage(root=root / "data"),
                                   settings_file=settings_file)
        window.show()
        APP.processEvents()
        try:
            yield window, scan, plan
        finally:
            thread = window.weekly_widget._scan_thread
            if thread and thread.isRunning():
                thread.wait(5000)
                APP.processEvents()
            window.close()
            window.deleteLater()
            APP.processEvents()


RESULTS = []


def check(name, okay, observed):
    RESULTS.append({"check": name, "passed": bool(okay), "observed": observed})


def ui_probes():
    with window_fixture() as (window, scan, plan):
        widget = window.weekly_widget
        check("media_empty_table_visible", window.table_frame.isVisible(),
              {"visible": window.table_frame.isVisible()})
        window.mode_tabs.setCurrentIndex(1)
        APP.processEvents()
        check("weekly_empty_table_visible", widget.tree_frame.isVisible(),
              {"visible": widget.tree_frame.isVisible()})
        widget._scan_ready(scan)
        APP.processEvents()
        check("weekly_scanned_table_visible", widget.tree_frame.isVisible()
              and widget.tree.topLevelItemCount() == 1,
              {"visible": widget.tree_frame.isVisible(), "weeks": widget.tree.topLevelItemCount()})

        old_status = widget.status.text()
        enabled = widget.send_button.isEnabled()
        widget.send_button.click()
        check("no_target_has_visible_feedback", not enabled or widget.status.text() != old_status,
              {"send_enabled": enabled, "visible_status": widget.status.text(),
               "hidden_media_status": window.status.text(), "worker_started": window.worker is not None})

        widget.set_all(False)
        before = widget.send_button.isEnabled()
        widget.set_enabled(False)
        widget.set_enabled(True)
        check("empty_selection_stays_disabled", not widget.send_button.isEnabled(),
              {"before": before, "after_reenable": widget.send_button.isEnabled(),
               "selected_items": len(widget.selected_plan().items)})
        widget.set_all(True)

        journal = WeeklyJournal(window.storage.root)
        transport = Transport()
        asyncio.run(WeeklyQueueRunner(plan, journal, transport,
                                     progress=window.update_weekly_progress).run())
        check("successful_file_progress_finishes_at_100", window.file_progress.value() == 100,
              {"file_progress": window.file_progress.value(),
               "overall_progress": window.overall_progress.value()})
        states = []
        it = QTreeWidgetItemIterator(widget.tree)
        while it.value():
            item = it.value()
            if item.data(0, Qt.ItemDataRole.UserRole):
                states.append(item.data(3, Qt.ItemDataRole.UserRole))
            it += 1
        check("successful_rows_leave_queued_state", all(s != "queued" for s in states), states)

        widget.root = scan.root
        widget._scan_failed("simulated permission error")
        with patch.object(widget, "set_root") as rescan:
            widget.refresh()
            check("refresh_recovers_after_scan_error", rescan.called,
                  {"rescan_requested": rescan.called, "table_visible": widget.tree_frame.isVisible(),
                   "summary": widget.summary.text()})


def queue_probes():
    with fixture() as (root, scan, plan):
        journal = WeeklyJournal(root / "journal")
        first = Transport()
        runner = WeeklyQueueRunner(plan, journal, first)
        def stop_after_file(event):
            if event.get("message_id") and event["item"].path:
                runner.request_stop()
        runner.progress = stop_after_file
        try:
            asyncio.run(runner.run())
        except WeeklyStop:
            pass
        saved = WeeklyJournal(root / "journal").latest_unfinished_plan()
        second = Transport()
        asyncio.run(WeeklyQueueRunner(saved["plan"], WeeklyJournal(root / "journal"), second).run())
        check("stop_restart_resume_no_repeats", len(first.sent) == 3 and len(second.sent) == 1,
              {"before_stop": len(first.sent), "after_restart": len(second.sent)})

    with fixture() as (root, scan, plan):
        journal = WeeklyJournal(root / "journal")
        first_ids = []
        async def interrupted_upload():
            started = asyncio.Event()
            class BlockingTransport(Transport):
                async def send_file(self, path, random_id, progress=None):
                    first_ids.append(random_id)
                    started.set()
                    await asyncio.Event().wait()
            task = asyncio.create_task(WeeklyQueueRunner(plan, journal, BlockingTransport()).run())
            await asyncio.wait_for(started.wait(), 5)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        asyncio.run(interrupted_upload())
        saved = WeeklyJournal(root / "journal").latest_unfinished_plan()
        uncertain = [r for r in journal.run_items(1) if r["status"] == "uncertain"]
        second = Transport()
        asyncio.run(WeeklyQueueRunner(saved["plan"], WeeklyJournal(root / "journal"), second).run())
        check("immediate_stop_keeps_uncertain_and_reuses_id",
              saved["state"] == "paused" and len(uncertain) == 1
              and len(second.sent) == 2 and second.sent[0][2] == first_ids[0],
              {"saved_state": saved["state"], "uncertain_items": len(uncertain),
               "remaining_files": len(second.sent), "same_request_id": second.sent[0][2] == first_ids[0]})

    flood = type("FloodWaitError", (Exception,), {"seconds": 1})
    for second_error, label in [(flood, "repeated_flood_wait_recovers"),
                                (TimeoutError, "network_error_after_flood_recovers")]:
        with fixture() as (root, scan, plan):
            class FlakyTransport(Transport):
                calls = 0
                async def send_text(self, text, random_id):
                    self.calls += 1
                    if self.calls == 1:
                        raise flood("wait")
                    if self.calls == 2:
                        raise second_error("retry scenario")
                    return await super().send_text(text, random_id)
            transport = FlakyTransport()
            journal = WeeklyJournal(root / "journal")
            ticks = iter(range(10000))
            error = None
            with patch("telegram_media_sender.weekly_worker.time.monotonic", lambda: next(ticks)):
                try:
                    asyncio.run(WeeklyQueueRunner(plan, journal, transport,
                        sleep=lambda _: asyncio.sleep(0)).run())
                except Exception as exc:
                    error = type(exc).__name__
            rows = journal.run_items(1)
            check(label, error is None and all(row["status"] == "sent" for row in rows),
                  {"exception": error, "calls": transport.calls,
                   "first_item_status": rows[0]["status"]})


if __name__ == "__main__":
    APP = QApplication.instance() or QApplication([])
    ui_probes()
    queue_probes()
    output = Path("previews/functional-audit-2026-09-27")
    output.mkdir(parents=True, exist_ok=True)
    (output / "acceptance-results.json").write_text(
        json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")
    for result in RESULTS:
        print(("PASS" if result["passed"] else "FAIL"), result["check"], result["observed"])
    raise SystemExit(any(not result["passed"] for result in RESULTS))
