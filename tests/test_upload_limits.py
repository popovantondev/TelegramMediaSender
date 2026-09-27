import asyncio
import unittest
from types import SimpleNamespace

from telethon.tl import types

from telegram_media_sender.upload_limits import (
    APP_MAX_FILE_BYTES, TELEGRAM_UPLOAD_PART_BYTES, account_upload_limit,
)


class UploadLimitTests(unittest.TestCase):
    def test_account_limit_uses_current_telegram_config_and_app_cap(self):
        class Client:
            async def __call__(self, request):
                self.request = request
                return SimpleNamespace(config=types.JsonObject(value=[
                    types.JsonObjectValue("upload_max_fileparts_default", types.JsonNumber(3000)),
                    types.JsonObjectValue("upload_max_fileparts_premium", types.JsonNumber(8000)),
                ]))

        default = asyncio.run(account_upload_limit(Client(), premium=False))
        premium = asyncio.run(account_upload_limit(Client(), premium=True))
        self.assertEqual(default, 3000 * TELEGRAM_UPLOAD_PART_BYTES)
        self.assertEqual(premium, APP_MAX_FILE_BYTES)

    def test_missing_runtime_account_limit_fails_closed(self):
        class Client:
            async def __call__(self, _request):
                return SimpleNamespace(config=types.JsonObject(value=[]))

        with self.assertRaisesRegex(RuntimeError, "upload limit is unavailable"):
            asyncio.run(account_upload_limit(Client(), premium=False))


if __name__ == "__main__":
    unittest.main()
