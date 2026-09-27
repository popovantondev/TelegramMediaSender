"""Shared Telegram connection and sign-in flow for both sender modes."""
from __future__ import annotations

import asyncio
from typing import Callable

from .i18n import tr


async def connect_and_authorize(client, profile: dict,
                                ask_input: Callable[[str, bool], str],
                                language: str = "en",
                                check_cancel: Callable[[], None] | None = None) -> None:
    """Connect a Telethon client and authorize it using the existing profile."""
    from telethon.errors import SessionPasswordNeededError

    check = check_cancel or (lambda: None)
    await client.connect()
    check()
    if await client.is_user_authorized():
        return
    phone = profile.get("phone")
    if not phone:
        raise RuntimeError(tr("The profile has no phone number.", language))
    sent_code = await client.send_code_request(phone)
    code = await asyncio.to_thread(ask_input, tr("Telegram sign-in code", language), False)
    check()
    try:
        await client.sign_in(phone, code, phone_code_hash=sent_code.phone_code_hash)
    except SessionPasswordNeededError:
        password = await asyncio.to_thread(
            ask_input, tr("Telegram two-step verification password", language), True
        )
        check()
        await client.sign_in(password=password)
    check()
