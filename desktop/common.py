from __future__ import annotations

import argparse
import os
import platform
from pathlib import Path


APP_DIRECTORY = "Haint"


def application_data_directory(system: str | None = None) -> Path:
    system = system or platform.system()
    if system == "Windows":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif system == "Darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / APP_DIRECTORY


def configure_environment(http_port: int) -> Path:
    database_path = os.environ.get("DATABASE_PATH")
    if database_path:
        database = Path(database_path).expanduser()
        data_directory = database.parent
    else:
        data_directory = application_data_directory()
        database = data_directory / "dro.sqlite3"
    data_directory.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_PATH"] = str(database)
    os.environ.setdefault("BIND_ADDRESS", "127.0.0.1")
    os.environ["PORT"] = str(http_port)
    return data_directory


def bridge_arguments(
    serial_port: str,
    http_port: int,
    *,
    baud: int = 115200,
    unit: str = "mm",
    poll_interval: float = 0.25,
    poll_command: str = "ctrl-b",
    quiet: bool = False,
) -> argparse.Namespace:
    from bridge.dro_bridge import build_parser as build_bridge_parser

    args = build_bridge_parser().parse_args([])
    args.port = serial_port
    args.endpoint = f"http://127.0.0.1:{http_port}/api/live"
    args.baud = baud
    args.unit = unit
    args.poll_interval = poll_interval
    args.poll_command = poll_command
    args.quiet = quiet
    return args
