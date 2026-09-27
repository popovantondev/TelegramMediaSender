import asyncio
import tempfile
import hashlib
import json
from dataclasses import replace
import unittest
from unittest.mock import patch
from pathlib import Path

from telegram_media_sender.weekly_journal import WeeklyJournal
from telegram_media_sender.publication_plan_import import load_publication_plan
from telegram_media_sender.upload_limits import UploadLimitError
from telegram_media_sender.weekly_plan import (FileCategory, ItemKind, UploadMode, WeeklyPlanItem,
    WeeklyUploadPlan, scan_weekly_folder, build_weekly_plan)
from telegram_media_sender.weekly_worker import WeeklyQueueRunner, WeeklyStop


class FakeTransport:
    def __init__(self, journal=None, run_id=None):
        self.sent = []
        self.journal = journal
        self.run_id = run_id
        self.album_failures = 0
        self.on_album = None

    async def send_text(self, text, random_id):
        self.sent.append(("text", text, random_id))
        return 100 + len(self.sent)

    async def send_file(self, path, random_id, progress=None):
        if self.journal and self.run_id:
            statuses = [r["status"] for r in self.journal.run_items(self.run_id)]
            if len(self.sent):
                self.assert_previous_sent = statuses[0] == "sent"
        self.sent.append(("file", Path(path).name, random_id))
        if progress:
            progress(Path(path).stat().st_size, Path(path).stat().st_size)
        return 100 + len(self.sent)

    async def reconnect(self):
        pass

    async def send_album(self, paths, random_ids, progress=None):
        self.sent.append(("album", [Path(path).name for path in paths], list(random_ids)))
        if self.on_album:
            self.on_album()
        if self.album_failures:
            self.album_failures -= 1
            raise ConnectionError("acknowledgement lost")
        if progress:
            for index, path in enumerate(paths):
                size = Path(path).stat().st_size
                progress(index, size, size)
        return [200 + index for index in range(len(paths))]


class WeeklyWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.source = self.root / "study"
        self.video = self.source / "Неделя 1/2026-08-03/Лекция 1.mp4"
        self.video.parent.mkdir(parents=True)
        self.video.write_bytes(b"video")
        self.scan = scan_weekly_folder(self.source)
        self.plan = build_weekly_plan(self.scan)
        self.journal = WeeklyJournal(self.data)

    def tearDown(self):
        self.temp.cleanup()

    def test_runner_sends_sequentially_and_records_each_receipt(self):
        transport = FakeTransport()
        progress = []
        counts = asyncio.run(WeeklyQueueRunner(self.plan, self.journal, transport,
                                               progress=progress.append).run())
        self.assertEqual(counts["sent"], 3)  # week header, day header and one media file
        self.assertEqual([row[0] for row in transport.sent], ["text", "text", "file"])
        self.assertEqual(sum(r["status"] == "sent" for r in self.journal.run_items(1)), 3)
        self.assertEqual(progress[-1]["phase"], "completed")

    def test_second_run_skips_already_sent_items(self):
        first = FakeTransport()
        asyncio.run(WeeklyQueueRunner(self.plan, self.journal, first).run())
        second = FakeTransport()
        counts = asyncio.run(WeeklyQueueRunner(self.plan, self.journal, second).run())
        self.assertEqual(second.sent, [])
        self.assertEqual(counts["sent"], 0)

    def test_media_group_plan_sends_subtitle_batch_as_one_durable_album(self):
        paths = []
        items = []
        for index in (1, 2):
            path = self.root / f"lesson.{index}.ru.srt"
            path.write_text(f"subtitle {index}")
            paths.append(path)
            items.append(WeeklyPlanItem(
                key=f"file:{path.name}", kind=ItemKind.FILE, week_key="bundle:lesson",
                day_key=None, category=FileCategory.SUBTITLES, path=path,
                relative_path=path.name, name=path.name, size=path.stat().st_size,
                mtime_ns=path.stat().st_mtime_ns, position=index,
                group_key="bundle:lesson", operation_key="bundle:lesson:subtitles:0"))
        plan = WeeklyUploadPlan(tuple(items), self.root, "profile", 1, 2, "test",
                                mode=UploadMode.MEDIA_GROUPS)
        transport = FakeTransport()
        result = asyncio.run(WeeklyQueueRunner(plan, self.journal, transport).run())
        self.assertEqual(result["sent"], 2)
        self.assertEqual(transport.sent[0][0:2], ("album", [path.name for path in paths]))
        rows = self.journal.run_items(1)
        self.assertEqual([row["status"] for row in rows], ["sent", "sent"])
        self.assertEqual([row["message_id"] for row in rows], [200, 201])

    def test_album_network_retry_reuses_persisted_request_ids(self):
        paths, items = [], []
        for index in (1, 2):
            path = self.root / f"retry.{index}.srt"
            path.write_text(f"subtitle {index}")
            paths.append(path)
            items.append(WeeklyPlanItem(
                key=f"file:{path.name}", kind=ItemKind.FILE, week_key="bundle:retry",
                day_key=None, category=FileCategory.SUBTITLES, path=path,
                relative_path=path.name, name=path.name, size=path.stat().st_size,
                mtime_ns=path.stat().st_mtime_ns, position=index,
                group_key="bundle:retry", operation_key="bundle:retry:subtitles:0"))
        plan = WeeklyUploadPlan(tuple(items), self.root, "profile", 1, 2, "test",
                                mode=UploadMode.MEDIA_GROUPS)
        transport = FakeTransport()
        transport.album_failures = 1

        async def no_wait(_seconds):
            return None

        result = asyncio.run(WeeklyQueueRunner(plan, self.journal, transport,
            sleep=no_wait, reconcile=lambda *_args: None).run())
        self.assertEqual(result["sent"], 2)
        self.assertEqual(transport.sent[0][2], transport.sent[1][2])
        self.assertEqual([row["status"] for row in self.journal.run_items(1)], ["sent", "sent"])

    def test_file_mutation_after_plan_stops_before_sending(self):
        self.video.write_bytes(b"different")
        transport = FakeTransport()
        with self.assertRaises(Exception):
            asyncio.run(WeeklyQueueRunner(self.plan, self.journal, transport).run())
        self.assertEqual(transport.sent, [])

    def test_file_over_connected_account_cap_is_rejected_before_queue_creation(self):
        transport = FakeTransport()
        with self.assertRaises(UploadLimitError):
            asyncio.run(WeeklyQueueRunner(self.plan, self.journal, transport,
                                           max_file_bytes=1).run())
        self.assertEqual(transport.sent, [])
        with self.journal._connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)

    def _imported_plan(self):
        root = self.root / "prepared"
        day = root / "Неделя 1" / "2026-08-03"
        day.mkdir(parents=True)
        file = day / "clip.mp4"
        file.write_bytes(b"synthetic video")
        manifest = {
            "format": "study-archive-publication-plan", "schema_version": 1,
            "project_id": "00000000-0000-4000-8000-000000000101", "revision": 9,
            "items": [
                {"id": "00000000-0000-4000-8000-000000000102", "kind": "text",
                 "week": 1, "date": None, "text": "Текст недели"},
                {"id": "00000000-0000-4000-8000-000000000103", "kind": "text",
                 "week": 1, "date": "2026-08-03", "text": "Точный текст дня"},
                {"id": "00000000-0000-4000-8000-000000000104", "kind": "file",
                 "week": 1, "date": "2026-08-03", "path": "Неделя 1/2026-08-03/clip.mp4",
                 "name": "clip.mp4", "size": file.stat().st_size,
                 "sha256": hashlib.sha256(file.read_bytes()).hexdigest()},
            ],
        }
        path = root / "publication-plan.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        return load_publication_plan(path), file

    def test_imported_plan_keeps_exact_text_id_order_and_journal_binding(self):
        plan, _file = self._imported_plan()
        plan = replace(plan, profile_id="profile-A", account_id=12,
                       chat_id=-345, chat_title="Test chat")
        transport = FakeTransport()
        result = asyncio.run(WeeklyQueueRunner(plan, self.journal, transport).run())
        self.assertEqual(result["sent"], 3)
        self.assertEqual([row[:2] for row in transport.sent], [
            ("text", "Текст недели"), ("text", "Точный текст дня"), ("file", "clip.mp4")])
        rows = self.journal.run_items(1)
        self.assertEqual([row["item_key"] for row in rows], [item.key for item in plan.items])
        saved = self.journal.latest_unfinished_plan()
        self.assertIsNone(saved)
        from telegram_media_sender.weekly_journal import _deserialize_plan
        with self.journal._connect() as db:
            serialized = db.execute("SELECT plan_json FROM runs WHERE run_id=1").fetchone()[0]
        restored = _deserialize_plan(serialized)
        self.assertEqual((restored.publication_project_id, restored.publication_revision,
                          restored.profile_id, restored.chat_id),
                         (plan.publication_project_id, 9, "profile-A", -345))

    def test_study_archive_prep_export_fixture_runs_in_exact_order(self):
        manifest = (Path(__file__).parent / "fixtures"
                    / "study_archive_prep_publication_plan_v1" / "publication-plan.json")
        plan = replace(load_publication_plan(manifest), profile_id="profile-A",
                       account_id=12, chat_id=-345, chat_title="Synthetic test chat")
        transport = FakeTransport()
        confirmations = []

        def confirm(_run_id, rows):
            confirmations.append(len(rows))
            return True

        result = asyncio.run(WeeklyQueueRunner(plan, self.journal, transport,
                                               confirmation=confirm).run())

        self.assertEqual(confirmations, [8])
        self.assertEqual(result["sent"], 8)
        self.assertEqual([row[:2] for row in transport.sent], [
            ("text", "Неделя 1 03.08 - 03.08"),
            ("text", "2026-08-03"),
            ("file", "lecture.mkv"),
            ("file", "lecture.ru.srt"),
            ("file", "lecture.srt"),
            ("file", "03_Скриншоты.zip"),
            ("file", "04_Дополнительные_материалы.zip"),
            ("text", "Дополнительная заметка"),
        ])
        rows = self.journal.run_items(1)
        self.assertEqual([row["item_key"] for row in rows], [item.key for item in plan.items])
        self.assertTrue(all(row["status"] == "sent" and row["message_id"] for row in rows))

    def test_imported_file_change_after_final_confirmation_blocks_all_sending(self):
        plan, file = self._imported_plan()
        transport = FakeTransport()

        def change_after_history_check(_run_id, _rows):
            file.write_bytes(b"changed video!!!")
            return True

        with self.assertRaises(Exception):
            asyncio.run(WeeklyQueueRunner(plan, self.journal, transport,
                                          confirmation=change_after_history_check).run())
        self.assertEqual(transport.sent, [])

    def test_journal_run_identity_includes_publication_revision_and_target(self):
        plan, _file = self._imported_plan()
        base = replace(plan, profile_id="p1", account_id=1, chat_id=-100,
                       chat_title="First")
        first = self.journal.save_plan(base)
        for changed in (replace(base, publication_revision=10),
                        replace(base, profile_id="p2"),
                        replace(base, chat_id=-200)):
            self.assertNotEqual(first, self.journal.save_plan(changed))

    def test_queue_waits_for_separate_confirmation_after_reconciliation(self):
        transport = FakeTransport()
        phases = []
        async def confirm(_run_id, _rows):
            phases.append("reviewed")
            return False
        with self.assertRaises(WeeklyStop):
            asyncio.run(WeeklyQueueRunner(self.plan, self.journal, transport,
                                          confirmation=confirm).run())
        self.assertEqual(phases, ["reviewed"])
        self.assertEqual(transport.sent, [])
        self.assertEqual(self.journal.run_items(1)[0]["status"], "pending")

    def test_network_recovery_reconciles_uncertain_item_before_retrying(self):
        class LostAcknowledgementTransport(FakeTransport):
            def __init__(self):
                super().__init__()
                self.failed_once = False

            async def send_text(self, text, random_id):
                if not self.failed_once:
                    self.failed_once = True
                    raise TimeoutError("acknowledgement was lost")
                return await super().send_text(text, random_id)

        transport = LostAcknowledgementTransport()
        reconciliations = []

        async def reconcile(run_id, rows):
            reconciliations.append(1)
            if len(reconciliations) == 2:
                uncertain = next(row for row in rows if row["status"] == "uncertain")
                self.journal.mark_found_in_chat(uncertain["item_id"], 777)

        ticks = [0]
        def fast_monotonic():
            ticks[0] += 1
            return ticks[0]

        with patch("telegram_media_sender.weekly_worker.time.monotonic", fast_monotonic):
            result = asyncio.run(WeeklyQueueRunner(
                self.plan, self.journal, transport, reconcile=reconcile,
                sleep=lambda _seconds: asyncio.sleep(0),
            ).run())

        self.assertEqual(len(reconciliations), 2)
        self.assertEqual(len(transport.sent), 2)  # the lost-ack message was not sent again
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["uncertain"], 0)

    def test_flood_wait_during_network_retry_keeps_queue_and_reuses_attempt(self):
        flood_error = type("FloodWaitError", (Exception,), {"seconds": 1})

        class FloodDuringRetryTransport(FakeTransport):
            def __init__(self):
                super().__init__()
                self.calls = 0
                self.random_ids = []

            async def send_text(self, text, random_id):
                self.calls += 1
                self.random_ids.append(random_id)
                if self.calls == 1:
                    raise TimeoutError("connection dropped")
                if self.calls == 2:
                    raise flood_error("slow down")
                return await super().send_text(text, random_id)

        transport = FloodDuringRetryTransport()
        ticks = [0]
        def fast_monotonic():
            ticks[0] += 1
            return ticks[0]

        with patch("telegram_media_sender.weekly_worker.time.monotonic", fast_monotonic):
            result = asyncio.run(WeeklyQueueRunner(
                self.plan, self.journal, transport,
                sleep=lambda _seconds: asyncio.sleep(0),
            ).run())

        self.assertEqual(transport.calls, 4)  # retry, then the next text header
        self.assertEqual(transport.random_ids[0], transport.random_ids[1])
        self.assertEqual(transport.random_ids[1], transport.random_ids[2])
        self.assertNotEqual(transport.random_ids[2], transport.random_ids[3])
        self.assertEqual(result["uncertain"], 0)

    def test_repeated_flood_wait_retries_same_persisted_request(self):
        flood = type("FloodWaitError", (Exception,), {"seconds": 1})

        class RepeatedFloodTransport(FakeTransport):
            def __init__(self):
                super().__init__()
                self.calls = 0
                self.ids = []

            async def send_text(self, text, random_id):
                self.calls += 1
                self.ids.append(random_id)
                if self.calls < 3:
                    raise flood("wait")
                return await super().send_text(text, random_id)

        transport = RepeatedFloodTransport()
        ticks = [0]
        def fast_monotonic():
            ticks[0] += 1
            return ticks[0]
        with patch("telegram_media_sender.weekly_worker.time.monotonic", fast_monotonic):
            result = asyncio.run(WeeklyQueueRunner(
                self.plan, self.journal, transport,
                sleep=lambda _seconds: asyncio.sleep(0),
            ).run())
        self.assertEqual(transport.ids[0], transport.ids[1])
        self.assertEqual(transport.ids[1], transport.ids[2])
        self.assertEqual(result["uncertain"], 0)
        self.assertEqual(result["error"], 0)
        self.assertEqual(self.journal.run_items(1)[0]["status"], "sent")

    def test_network_error_after_flood_wait_reconciles_and_resumes(self):
        flood = type("FloodWaitError", (Exception,), {"seconds": 1})

        class FloodThenNetworkTransport(FakeTransport):
            def __init__(self):
                super().__init__()
                self.calls = 0
                self.ids = []

            async def send_text(self, text, random_id):
                self.calls += 1
                self.ids.append(random_id)
                if self.calls == 1:
                    raise flood("wait")
                if self.calls == 2:
                    raise TimeoutError("network dropped")
                return await super().send_text(text, random_id)

        transport = FloodThenNetworkTransport()
        ticks = [0]
        def fast_monotonic():
            ticks[0] += 1
            return ticks[0]
        with patch("telegram_media_sender.weekly_worker.time.monotonic", fast_monotonic):
            result = asyncio.run(WeeklyQueueRunner(
                self.plan, self.journal, transport,
                reconcile=lambda *_args: None,
                sleep=lambda _seconds: asyncio.sleep(0),
            ).run())
        self.assertEqual(transport.ids[:3], [transport.ids[0]] * 3)
        self.assertEqual(result["uncertain"], 0)
        self.assertEqual(self.journal.run_items(1)[0]["status"], "sent")


if __name__ == "__main__":
    unittest.main()
