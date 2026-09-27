import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from telegram_media_sender.telegram_transport import TelethonWeeklyTransport
from telegram_media_sender.weekly_journal import UncertainReceiptError


class FakeClient:
    def __init__(self):
        self.requests = []
        self.prepared = []
        self.incomplete_receipt = False

    async def get_input_entity(self, target):
        return ("input", target)

    async def __call__(self, request):
        self.requests.append(request)
        return object()

    def _get_response_message(self, request, result, entity):
        if isinstance(request, list):
            if self.incomplete_receipt:
                return []
            return [SimpleNamespace(id=41 + index) for index, _ in enumerate(request)]
        return SimpleNamespace(id=41)

    async def _file_to_media(self, path, **kwargs):
        self.prepared.append((path, kwargs))
        if kwargs.get("progress_callback"):
            kwargs["progress_callback"](1, 2)
        return object(), SimpleNamespace(media="uploaded"), False


class WeeklyTransportTests(unittest.TestCase):
    def test_text_uses_saved_random_id_on_raw_message_request(self):
        client = FakeClient()
        transport = TelethonWeeklyTransport(client, "chat")
        message_id = asyncio.run(transport.send_text("Week 1", 123456))
        self.assertEqual(message_id, 41)
        request = client.requests[0]
        self.assertEqual((request.message, request.random_id), ("Week 1", 123456))

    def test_media_uses_saved_random_id_and_sequential_single_media_request(self):
        client = FakeClient()
        transport = TelethonWeeklyTransport(client, "chat")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "video.mp4"
            path.write_bytes(b"video")
            message_id = asyncio.run(transport.send_file(path, 654321))
        self.assertEqual(message_id, 41)
        request = client.requests[0]
        self.assertEqual(request.random_id, 654321)
        self.assertEqual(len(client.requests), 1)
        self.assertTrue(client.prepared[0][1]["supports_streaming"])
        self.assertFalse(client.prepared[0][1]["force_document"])

    def test_zip_is_prepared_as_document(self):
        client = FakeClient()
        transport = TelethonWeeklyTransport(client, "chat")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "materials.zip"
            path.write_bytes(b"zip")
            asyncio.run(transport.send_file(path, 654321))
        self.assertTrue(client.prepared[0][1]["force_document"])

    def test_album_preserves_per_item_request_ids_and_returns_every_receipt(self):
        client = FakeClient()
        transport = TelethonWeeklyTransport(client, "chat")
        progress = []
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("one.srt", "two.srt")]
            for path in paths:
                path.write_text("subtitle")
            ids = asyncio.run(transport.send_album(paths, [123, 456],
                                                   progress=lambda *args: progress.append(args)))
        self.assertEqual(ids, [41, 42])
        request = client.requests[0]
        self.assertEqual([part.random_id for part in request.multi_media], [123, 456])
        self.assertEqual([part.message for part in request.multi_media], ["", ""])
        self.assertEqual(progress, [(0, 1, 2), (1, 1, 2)])

    def test_album_rejects_more_than_ten_files_before_network_request(self):
        client = FakeClient()
        transport = TelethonWeeklyTransport(client, "chat")
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f"{index}.srt" for index in range(11)]
            for path in paths:
                path.write_text("subtitle")
            with self.assertRaises(ValueError):
                asyncio.run(transport.send_album(paths, list(range(11))))
        self.assertEqual(client.requests, [])

    def test_incomplete_album_receipt_is_reported_as_uncertain(self):
        client = FakeClient()
        client.incomplete_receipt = True
        transport = TelethonWeeklyTransport(client, "chat")
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("one.srt", "two.srt")]
            for path in paths:
                path.write_text("subtitle")
            with self.assertRaises(UncertainReceiptError):
                asyncio.run(transport.send_album(paths, [123, 456]))


if __name__ == "__main__":
    unittest.main()
