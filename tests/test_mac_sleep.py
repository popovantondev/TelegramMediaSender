import unittest
from unittest.mock import Mock

from telegram_media_sender.mac_sleep import IdleSleepInhibitor


class IdleSleepInhibitorTests(unittest.TestCase):
    def test_non_macos_is_a_noop(self):
        popen = Mock()
        with IdleSleepInhibitor(platform="linux", popen=popen):
            pass
        popen.assert_not_called()

    def test_macos_starts_temporary_assertion_and_releases_it(self):
        process = Mock()
        process.poll.return_value = None
        popen = Mock(return_value=process)
        with IdleSleepInhibitor(platform="darwin", popen=popen,
                                which=lambda _name: "/usr/bin/caffeinate"):
            popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0][1:], ["-i", "-w", popen.call_args.args[0][-1]])
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=3)

    def test_missing_macos_utility_blocks_queue_start(self):
        with self.assertRaisesRegex(RuntimeError, "caffeinate is unavailable"):
            with IdleSleepInhibitor(platform="darwin", which=lambda _name: None):
                self.fail("queue should not start without the required sleep assertion")


if __name__ == "__main__":
    unittest.main()
