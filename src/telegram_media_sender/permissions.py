"""Find Telegram chats where the current account may publish media."""
from __future__ import annotations

from typing import Any


def can_publish(entity: Any) -> bool:
    """Check real Telethon chat types, including default group bans."""
    from telethon.tl.types import Channel, Chat

    bans = ("view_messages", "send_messages", "send_plain", "send_media", "send_photos",
            "send_videos", "send_docs", "send_audios", "send_voices", "send_roundvideos")

    def restricted(rights):
        return any(getattr(rights, name, False) for name in bans)

    if isinstance(entity, Channel):
        if entity.left or entity.min:
            return False
        if entity.broadcast:
            return bool(entity.creator or (entity.admin_rights and entity.admin_rights.post_messages))
        if not entity.megagroup or restricted(entity.banned_rights):
            return False
        return bool(entity.creator or entity.admin_rights or not restricted(entity.default_banned_rights))
    if isinstance(entity, Chat):
        if entity.left or entity.deactivated or entity.migrated_to:
            return False
        return bool(entity.creator or entity.admin_rights or not restricted(entity.default_banned_rights))
    return bool(getattr(entity, "can_post_messages", False) or getattr(entity, "can_send_messages", False))
