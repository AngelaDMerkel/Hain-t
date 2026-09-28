import tempfile
import unittest
from pathlib import Path

from app.storage import MeasurementStore
from bridge.dro_bridge import parse_dro_line


class DroLineTests(unittest.TestCase):
    def test_parses_captured_dro_output(self):
        parsed = parse_dro_line("X =+  2511.05 R")
        self.assertEqual(parsed["axis"], "X")
        self.assertEqual(parsed["value"], 2511.05)
        self.assertEqual(parsed["unit"], "mm")

    def test_parses_negative_inches(self):
        parsed = parse_dro_line('Y =-  1.250 " R')
        self.assertEqual(parsed["value"], -1.25)
        self.assertEqual(parsed["unit"], "in")

    def test_rejects_unrecognized_line(self):
        self.assertIsNone(parse_dro_line("not a measurement"))


class MeasurementStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "dro.sqlite3"
        self.store = MeasurementStore(self.path)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_adds_timestamped_measurement(self):
        saved = self.store.add("x", 2511.05, "mm", "X =+  2511.05 R")
        self.assertEqual(saved["id"], 1)
        self.assertEqual(saved["axis"], "X")
        self.assertTrue(saved["received_at"])
        self.assertTrue(saved["stored_at"])
        self.assertEqual(self.store.summary()["count"], 1)

    def test_recent_is_newest_first(self):
        self.store.add("X", 1)
        self.store.add("Y", 2)
        self.assertEqual([row["axis"] for row in self.store.recent()], ["Y", "X"])

    def test_limit_is_applied(self):
        for value in range(3):
            self.store.add("X", value)
        self.assertEqual(len(self.store.recent(2)), 2)

    def test_snapshot_saves_axes_with_one_timestamp(self):
        saved = self.store.add_snapshot(
            [
                {"axis": "X", "value": 10.25, "unit": "mm"},
                {"axis": "Y", "value": -2.5, "unit": "mm"},
            ]
        )
        self.assertEqual([row["axis"] for row in saved], ["X", "Y"])
        self.assertEqual(saved[0]["stored_at"], saved[1]["stored_at"])
        self.assertEqual(self.store.summary()["count"], 2)


if __name__ == "__main__":
    unittest.main()
