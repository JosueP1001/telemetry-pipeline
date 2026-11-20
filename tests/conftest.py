import asyncio
import threading
import time

import pytest

from telemetry.collector import Collector


class RunningCollector:
    """Runs a Collector on its own event loop in a background thread."""

    def __init__(self, db_path, device_timeout):
        self.loop = asyncio.new_event_loop()
        self.collector = Collector("127.0.0.1", 0, 0, str(db_path), device_timeout)
        self._thread = threading.Thread(target=self.loop.run_forever, daemon=True)

    def start(self):
        self._thread.start()
        asyncio.run_coroutine_threadsafe(self.collector.start(), self.loop).result(5)

    def stop(self):
        asyncio.run_coroutine_threadsafe(self.collector.stop(), self.loop).result(5)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(5)

    def wait_for(self, predicate, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(0.02)
        return False


@pytest.fixture
def running(tmp_path):
    rc = RunningCollector(tmp_path / "t.db", device_timeout=0.5)
    rc.start()
    yield rc
    rc.stop()
