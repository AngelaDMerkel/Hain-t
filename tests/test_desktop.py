import os
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop.launcher import application_data_directory, bridge_arguments


class ApplicationDataDirectoryTests(unittest.TestCase):
    def test_uses_local_app_data_on_windows(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": "C:/Users/operator/AppData/Local"}, clear=False):
            self.assertEqual(
                application_data_directory("Windows"),
                Path("C:/Users/operator/AppData/Local/Haint"),
            )

    def test_uses_application_support_on_macos(self):
        with patch("desktop.common.Path.home", return_value=Path("/Users/operator")):
            self.assertEqual(
                application_data_directory("Darwin"),
                Path("/Users/operator/Library/Application Support/Haint"),
            )

    def test_uses_xdg_data_home_on_linux(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": "/home/operator/.data"}, clear=False):
            self.assertEqual(application_data_directory("Linux"), Path("/home/operator/.data/Haint"))


class DesktopBridgeArgumentsTests(unittest.TestCase):
    def test_points_bridge_at_embedded_service(self):
        args = bridge_arguments("COM7", 8123)
        self.assertEqual(args.port, "COM7")
        self.assertEqual(args.endpoint, "http://127.0.0.1:8123/api/live")
        self.assertEqual(args.poll_interval, 0.25)


if __name__ == "__main__":
    unittest.main()
