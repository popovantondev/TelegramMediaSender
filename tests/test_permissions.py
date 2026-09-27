import unittest
from unittest.mock import patch

from telegram_media_sender.permissions import can_publish, is_forum_chat


class FakeChannel:
    megagroup = True
    broadcast = False
    forum = True
    left = False
    min = False
    creator = False
    admin_rights = None
    default_banned_rights = None
    banned_rights = None


class PermissionTests(unittest.TestCase):
    def test_forum_group_is_explicitly_unsupported_until_topic_selection_exists(self):
        with patch("telethon.tl.types.Channel", FakeChannel):
            entity = FakeChannel()
            self.assertTrue(is_forum_chat(entity))
            self.assertFalse(can_publish(entity))

    def test_non_forum_group_remains_eligible_when_no_default_send_ban_exists(self):
        with patch("telethon.tl.types.Channel", FakeChannel):
            entity = FakeChannel()
            entity.forum = False
            self.assertFalse(is_forum_chat(entity))
            self.assertTrue(can_publish(entity))


if __name__ == "__main__":
    unittest.main()
