"""Offline checks for task storage locks."""
from pathlib import Path
import os
import tempfile
import unittest

from tests.local_temp import local_test_directory
from workflow.storage import batch_lock


class TaskStoragePathTests(unittest.TestCase):
    def test_stale_batch_marker_is_reclaimed_for_recovery(self):
        with local_test_directory("stale-batch-marker") as temporary:
            marker = Path(temporary) / "jobs" / ".student.pipeline.lock"
            marker.parent.mkdir(parents=True)
            marker.write_text(str(2**31 - 1), encoding="utf-8")

            with batch_lock(marker):
                self.assertEqual(marker.read_text(encoding="utf-8"), str(os.getpid()))

            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
