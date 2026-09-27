"""Telegram's runtime upload cap and the app's explicit per-file product cap."""
from __future__ import annotations

from dataclasses import dataclass

APP_MAX_FILE_BYTES = 2_000_000_000
TELEGRAM_UPLOAD_PART_BYTES = 512 * 1024


@dataclass(frozen=True)
class UploadLimitError(ValueError):
    name: str
    size: int
    limit: int

    def __str__(self):
        return f"File {self.name} exceeds the Telegram upload limit ({self.limit} bytes)."


async def account_upload_limit(client, *, premium: bool) -> int:
    """Read the connected account's current Telegram part-count limit."""
    from telethon.tl.functions.help import GetAppConfigRequest

    response = await client(GetAppConfigRequest(hash=0))
    config = getattr(response, "config", None)
    values = getattr(config, "value", None)
    if values is None:
        raise RuntimeError("Telegram did not provide its current upload limits.")
    params = {entry.key: getattr(entry.value, "value", None) for entry in values}
    key = "upload_max_fileparts_premium" if premium else "upload_max_fileparts_default"
    part_count = params.get(key)
    if not isinstance(part_count, (int, float)) or int(part_count) <= 0:
        raise RuntimeError("Telegram's current account upload limit is unavailable.")
    telegram_limit = int(part_count) * TELEGRAM_UPLOAD_PART_BYTES
    return min(APP_MAX_FILE_BYTES, telegram_limit)
