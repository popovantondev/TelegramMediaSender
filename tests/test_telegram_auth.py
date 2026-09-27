import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telethon.errors import SessionPasswordNeededError

from telegram_media_sender.telegram_auth import connect_and_authorize


class TelegramAuthTests(unittest.TestCase):
    def test_shared_sign_in_flow_handles_code_and_two_factor(self):
        client = SimpleNamespace(
            connect=AsyncMock(),
            is_user_authorized=AsyncMock(return_value=False),
            send_code_request=AsyncMock(return_value=SimpleNamespace(phone_code_hash="hash")),
            sign_in=AsyncMock(side_effect=[SessionPasswordNeededError(None), None]),
        )
        prompts = []

        def ask_input(prompt, secret):
            prompts.append((prompt, secret))
            return "password" if secret else "12345"

        asyncio.run(connect_and_authorize(client, {"phone": "+49123"}, ask_input, "en"))

        client.connect.assert_awaited_once()
        client.sign_in.assert_any_await("+49123", "12345", phone_code_hash="hash")
        client.sign_in.assert_any_await(password="password")
        self.assertEqual([secret for _prompt, secret in prompts], [False, True])

    def test_authorized_session_does_not_prompt(self):
        client = SimpleNamespace(
            connect=AsyncMock(),
            is_user_authorized=AsyncMock(return_value=True),
            send_code_request=AsyncMock(),
            sign_in=AsyncMock(),
        )
        asyncio.run(connect_and_authorize(client, {"phone": "+49123"},
                                         lambda *_args: self.fail("unexpected prompt"), "en"))
        client.sign_in.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
