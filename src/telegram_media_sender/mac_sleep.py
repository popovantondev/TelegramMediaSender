"""Temporary macOS idle-sleep assertion for active Telegram queues."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys


class IdleSleepInhibitor:
    """Prevent automatic idle sleep while active, without changing system settings.

    The caffeinate child is tied to this process PID as a crash-safety backstop;
    normal exits terminate it immediately. Display sleep remains allowed.
    """

    def __init__(self, *, platform: str | None = None, popen=None, which=None):
        self.platform = platform or sys.platform
        self._popen = popen or subprocess.Popen
        self._which = which or shutil.which
        self._process = None

    def __enter__(self):
        if self.platform != "darwin":
            return self
        executable = self._which("caffeinate")
        if not executable:
            raise RuntimeError("macOS caffeinate is unavailable; the upload queue cannot protect against idle sleep.")
        self._process = self._popen(
            [executable, "-i", "-w", str(os.getpid())],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if self._process.poll() is not None:
            self._process = None
            raise RuntimeError("macOS could not enable the temporary idle-sleep assertion.")
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        process, self._process = self._process, None
        if process is None:
            return False
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        return False
