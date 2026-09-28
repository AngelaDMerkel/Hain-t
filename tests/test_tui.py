import unittest
from datetime import datetime, timezone

from desktop.tui import format_axis, grouped_positions, live_state, render_screen


class TuiFormattingTests(unittest.TestCase):
    def test_formats_axis_value(self):
        self.assertEqual(format_axis({"value": 2087.65, "unit": "mm"}), "+2,087.650 mm")

    def test_groups_x_and_y_rows_into_positions(self):
        rows = [
            {"axis": "Y", "value": 2, "unit": "mm", "stored_at": "2026-01-01T12:00:00+00:00"},
            {"axis": "X", "value": 1, "unit": "mm", "stored_at": "2026-01-01T12:00:00+00:00"},
        ]
        positions = grouped_positions(rows)
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["axes"]["X"]["value"], 1)
        self.assertEqual(positions[0]["axes"]["Y"]["value"], 2)

    def test_marks_recent_position_live(self):
        now = datetime(2026, 1, 1, 12, 0, 1, tzinfo=timezone.utc)
        state, is_live = live_state({"updated_at": "2026-01-01T12:00:00+00:00"}, now)
        self.assertEqual(state, "Live")
        self.assertTrue(is_live)

    def test_renders_controls_and_coordinates_without_color(self):
        screen = render_screen(
            {
                "axes": {
                    "X": {"value": 12.5, "unit": "mm"},
                    "Y": {"value": -3.25, "unit": "mm"},
                },
                "updated_at": "2026-01-01T12:00:00+00:00",
            },
            [],
            "Connected",
            "/tmp/dro.sqlite3",
            color=False,
        )
        self.assertIn("X  +12.500 mm", screen)
        self.assertIn("Y  -3.250 mm", screen)
        self.assertIn("[S] Save position", screen)
        self.assertNotIn("\033[", screen)


if __name__ == "__main__":
    unittest.main()
