import json
import os
import subprocess
import sys
import tempfile
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


class DesktopServiceBindingTests(unittest.TestCase):
    def start_service(self, bind_address=None):
        # Use the launcher's configuration before importing the service, just as
        # the packaged applications do. Keep its database and environment isolated.
        with tempfile.TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment.pop("BIND_ADDRESS", None)
            if bind_address is not None:
                environment["BIND_ADDRESS"] = bind_address
            environment["DATABASE_PATH"] = str(Path(directory) / "dro.sqlite3")
            script = """
import faulthandler
import json
import threading
from unittest.mock import patch
from urllib.request import ProxyHandler, build_opener
from desktop.common import bridge_arguments, configure_environment

faulthandler.dump_traceback_later(10)
configure_environment(0)
from app import server

# DNS is irrelevant for binding to an IP. macOS Actions runners can spend
# over 30 seconds resolving the metadata name used by HTTPServer.server_bind.
with patch("socket.getfqdn", side_effect=AssertionError("Service startup must not require reverse DNS")):
    http_server = server.create_server()
thread = threading.Thread(target=http_server.serve_forever, daemon=True)
thread.start()
try:
    address, port = http_server.server_address
    opener = build_opener(ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=5) as response:
        health = json.load(response)
    endpoint = bridge_arguments("COM7", port).endpoint
    with opener.open(endpoint, timeout=5) as response:
        live = json.load(response)
    print(json.dumps({"address": address, "health": health["status"],
                     "bridge_endpoint": endpoint, "axes": live["axes"]}))
finally:
    http_server.shutdown()
    http_server.server_close()
    thread.join(timeout=5)
"""
            try:
                result = subprocess.run(
                    [sys.executable, "-u", "-c", script],
                    cwd=Path(__file__).resolve().parents[1],
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
            except subprocess.TimeoutExpired as error:
                self.fail(f"Service startup timed out. Child output: {error.stdout!r} {error.stderr!r}")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            return json.loads(result.stdout.splitlines()[-1])

    def test_native_service_listens_on_all_interfaces_and_keeps_local_bridge_access(self):
        service = self.start_service()
        self.assertEqual(service["address"], "0.0.0.0")
        self.assertEqual(service["health"], "ok")
        self.assertTrue(service["bridge_endpoint"].startswith("http://127.0.0.1:"))
        self.assertEqual(service["axes"], {})

    def test_explicit_local_only_binding_is_preserved(self):
        service = self.start_service("127.0.0.1")
        self.assertEqual(service["address"], "127.0.0.1")
        self.assertEqual(service["health"], "ok")


if __name__ == "__main__":
    unittest.main()
