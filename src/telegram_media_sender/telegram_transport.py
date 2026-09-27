"""The pinned Telethon 1.42.0 adapter for stable-ID sequential sends."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .weekly_journal import UncertainReceiptError


class TelethonWeeklyTransport:
    """Send one text or one file using a journal-owned random_id.

    Telethon's ``send_file`` creates its own request and random_id. This adapter
    keeps the pinned private preparation/response helpers in one place so the
    weekly sender can persist its own id before the network request.
    """

    TELETHON_VERSION = "1.42.0"

    def __init__(self, client, target):
        self.client = client
        self.target = target
        self._entity = None

    async def reconnect(self):
        await self.client.disconnect()
        await self.client.connect()

    async def _input_entity(self):
        if self._entity is None:
            self._entity = await self.client.get_input_entity(self.target)
        return self._entity

    async def send_text(self, text: str, random_id: int) -> int:
        from telethon.tl.functions.messages import SendMessageRequest

        entity = await self._input_entity()
        request = SendMessageRequest(peer=entity, message=text, random_id=random_id)
        result = await self.client(request)
        message = self.client._get_response_message(request, result, entity)
        if message is None or not getattr(message, "id", None):
            raise UncertainReceiptError("Telegram did not return a message id for the text message.")
        return int(message.id)

    async def send_file(self, path: Path, random_id: int, *, progress: Callable | None = None) -> int:
        from telethon.tl.functions.messages import SendMediaRequest

        path = Path(path)
        before = path.stat()
        suffix = path.suffix.casefold()
        video = suffix in {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi"}
        audio_video = video or suffix in {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}
        force_document = not audio_video
        supports_streaming = video and suffix in {".mp4", ".m4v"}
        entity = await self._input_entity()
        # These are Telethon 1.42.0 internals; keep usage isolated here.
        file_handle, media, _is_image = await self.client._file_to_media(
            str(path), force_document=force_document, progress_callback=progress,
            supports_streaming=supports_streaming, nosound_video=True,
        )
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError(f"File changed while Telegram was preparing it: {path.name}")
        if media is None:
            raise TypeError(f"Telethon could not prepare {path.name} as media")
        request = SendMediaRequest(peer=entity, media=media, message="", random_id=random_id)
        result = await self.client(request)
        message = self.client._get_response_message(request, result, entity)
        if message is None or not getattr(message, "id", None):
            raise UncertainReceiptError("Telegram did not return a message id for the media message.")
        return int(message.id)

    async def send_album(self, paths: list[Path], random_ids: list[int], *,
                         progress: Callable | None = None) -> list[int]:
        """Upload and send one journalled Telegram album (at most ten files).

        Telethon 1.42's private preparation helpers are deliberately isolated in
        this adapter. Telegram returns one message per InputSingleMedia; map the
        result back through Telethon's random-id response helper.
        """
        from telethon import types
        from telethon.tl.functions.messages import SendMultiMediaRequest

        paths = [Path(path) for path in paths]
        if not paths or len(paths) != len(random_ids) or len(paths) > 10:
            raise ValueError("An album must contain one to ten files and matching request IDs.")
        prepared = []
        before_stats = []
        for index, (path, random_id) in enumerate(zip(paths, random_ids)):
            before = path.stat()
            suffix = path.suffix.casefold()
            video = suffix in {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi"}
            audio_video = video or suffix in {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}
            def item_progress(current, total, item_index=index):
                if progress:
                    progress(item_index, current, total)

            file_handle, media, _ = await self.client._file_to_media(
                str(path), force_document=not audio_video,
                progress_callback=item_progress,
                supports_streaming=video and suffix in {".mp4", ".m4v"},
                nosound_video=True,
            )
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise RuntimeError(f"File changed while Telegram was preparing it: {path.name}")
            if media is None:
                raise TypeError(f"Telethon could not prepare {path.name} as media")
            before_stats.append((after.st_size, after.st_mtime_ns))
            prepared.append(types.InputSingleMedia(media=media, message="", random_id=random_id))

        for path, expected in zip(paths, before_stats):
            current = path.stat()
            if (current.st_size, current.st_mtime_ns) != expected:
                raise RuntimeError(f"File changed before Telegram album send: {path.name}")
        entity = await self._input_entity()
        request = SendMultiMediaRequest(peer=entity, multi_media=prepared)
        result = await self.client(request)
        messages = self.client._get_response_message(random_ids, result, entity)
        if not isinstance(messages, (list, tuple)) or len(messages) != len(paths):
            raise UncertainReceiptError("Telegram returned an incomplete album receipt.")
        ids = [int(getattr(message, "id", 0) or 0) for message in messages]
        if any(message_id <= 0 for message_id in ids) or len(set(ids)) != len(ids):
            raise UncertainReceiptError("Telegram returned an invalid album receipt.")
        return ids
