from __future__ import annotations

import argparse
import os
import queue
import shutil
import sys
import threading
import time
import webbrowser
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from desktop.common import bridge_arguments, configure_environment


RESET = "\033[0m"
MUTED = "\033[38;5;245m"
ACCENT = "\033[38;5;109m"
BRIGHT = "\033[38;5;255m"
GOOD = "\033[38;5;108m"
WARN = "\033[38;5;179m"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Hain’t in a terminal")
    parser.add_argument("--serial-port", default=os.environ.get("HAINT_SERIAL_PORT", "auto"))
    parser.add_argument("--http-port", type=int, default=int(os.environ.get("HAINT_PORT", "8080")))
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--unit", choices=("mm", "in"), default="mm")
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument(
        "--poll-command",
        choices=("ctrl-b", "actual-position"),
        default="ctrl-b",
    )
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--check", action="store_true", help="Validate the packaged TUI and exit")
    return parser


def paint(text: str, color: str, enabled: bool) -> str:
    return f"{color}{text}{RESET}" if enabled else text


def clip(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width < 2:
        return text[:width]
    return f"{text[: width - 1]}…"


def format_axis(measurement: dict[str, Any] | None) -> str:
    if not measurement:
        return "—"
    return f"{float(measurement['value']):+,.3f} {measurement.get('unit', 'mm')}"


def grouped_positions(measurements: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for measurement in measurements:
        stored_at = str(measurement["stored_at"])
        position = grouped.setdefault(stored_at, {"stored_at": stored_at, "axes": {}})
        position["axes"][str(measurement["axis"])] = measurement
    return list(grouped.values())


def live_state(snapshot: dict[str, Any], now: datetime | None = None) -> tuple[str, bool]:
    updated_at = snapshot.get("updated_at")
    if not isinstance(updated_at, str):
        return "Waiting for DRO", False
    current = now or datetime.now(timezone.utc)
    age = (current - datetime.fromisoformat(updated_at)).total_seconds()
    if age >= 2:
        return f"Stale · {age:.0f}s ago", False
    return "Live", True


def time_label(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value


def render_screen(
    snapshot: dict[str, Any],
    measurements: list[dict[str, Any]],
    status: str,
    database_path: str,
    *,
    width: int = 80,
    height: int = 24,
    color: bool = True,
) -> str:
    width = max(48, width)
    axes = snapshot.get("axes", {})
    state, is_live = live_state(snapshot)
    divider = "─" * width
    title = "HAIN’T"
    slogan = "It Hain’t Working"
    x_value = format_axis(axes.get("X") if isinstance(axes, dict) else None)
    y_value = format_axis(axes.get("Y") if isinstance(axes, dict) else None)
    column = max(20, (width - 3) // 2)

    lines = [
        f"{paint(title, BRIGHT, color)}  {paint(slogan, MUTED, color)}",
        paint(divider, MUTED, color),
        f"CURRENT POSITION{' ' * max(1, width - 24 - len(state))}{paint(state, GOOD if is_live else WARN, color)}",
        "",
        f"{paint('X', ACCENT, color)}  {x_value:<{column - 3}}   {paint('Y', ACCENT, color)}  {y_value}",
        "",
        f"{paint('[S]', ACCENT, color)} Save position   {paint('[B]', ACCENT, color)} Open browser   {paint('[Q]', ACCENT, color)} Quit",
        paint(divider, MUTED, color),
        "SAVED POSITIONS",
    ]

    available_rows = max(1, height - 14)
    positions = grouped_positions(measurements)[:available_rows]
    if not positions:
        lines.append(paint("No saved positions", MUTED, color))
    for position in positions:
        saved_axes = position["axes"]
        label = time_label(position["stored_at"])
        x_saved = format_axis(saved_axes.get("X"))
        y_saved = format_axis(saved_axes.get("Y"))
        lines.append(clip(f"{label}   X {x_saved}   Y {y_saved}", width))

    while len(lines) < height - 3:
        lines.append("")
    lines.extend(
        [
            paint(divider, MUTED, color),
            clip(status, width),
            paint(clip(f"Database: {database_path}", width), MUTED, color),
        ]
    )
    return "\n".join(lines[:height])


class TerminalSession:
    def __init__(self) -> None:
        self.fd: int | None = None
        self.original_settings: object | None = None

    def __enter__(self) -> TerminalSession:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise RuntimeError("Hain’t TUI requires an interactive terminal")
        if os.name == "nt":
            self._enable_windows_vt()
        else:
            import termios
            import tty

            self.fd = sys.stdin.fileno()
            self.original_settings = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
            settings = termios.tcgetattr(self.fd)
            settings[3] &= ~termios.ECHO
            termios.tcsetattr(self.fd, termios.TCSANOW, settings)
        sys.stdout.write("\033[?1049h\033[?25l")
        sys.stdout.flush()
        return self

    def __exit__(self, _kind: object, _value: object, _traceback: object) -> None:
        if self.fd is not None and self.original_settings is not None:
            import termios

            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.original_settings)
        sys.stdout.write("\033[?25h\033[?1049l")
        sys.stdout.flush()

    @staticmethod
    def _enable_windows_vt() -> None:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)

    @staticmethod
    def read_key(timeout: float) -> str | None:
        if os.name == "nt":
            import msvcrt

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if msvcrt.kbhit():
                    key = msvcrt.getwch()
                    if key in ("\x00", "\xe0"):
                        msvcrt.getwch()
                        return None
                    return key
                time.sleep(0.01)
            return None

        import select

        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        return sys.stdin.read(1) if ready else None

    @staticmethod
    def draw(screen: str) -> None:
        sys.stdout.write(f"\033[H\033[2J{screen}")
        sys.stdout.flush()


class TerminalApplication:
    def __init__(self, args: argparse.Namespace) -> None:
        configure_environment(args.http_port)
        from app import server
        from bridge import dro_bridge

        self.server = server
        self.stop_event = threading.Event()
        self.status_messages: queue.SimpleQueue[str] = queue.SimpleQueue()
        self.status = "Starting local service…"
        self.database_path = os.environ["DATABASE_PATH"]
        self.http_server = server.create_server()
        self.url = f"http://127.0.0.1:{args.http_port}"
        self.color = not args.no_color and "NO_COLOR" not in os.environ
        self.recent: list[dict[str, Any]] = []
        self.next_database_refresh = 0.0
        self.last_screen: str | None = None

        threading.Thread(target=self.http_server.serve_forever, daemon=True, name="haint-http").start()
        serial_args = bridge_arguments(
            args.serial_port,
            args.http_port,
            baud=args.baud,
            unit=args.unit,
            poll_interval=args.poll_interval,
            poll_command=args.poll_command,
            quiet=True,
        )
        threading.Thread(
            target=dro_bridge.stream,
            args=(serial_args, self.stop_event, self.status_messages.put),
            daemon=True,
            name="haint-serial",
        ).start()

    def save_position(self) -> None:
        try:
            saved = self.server.save_live_position()
            self.status = f"Saved X/Y position at {time_label(saved[0]['stored_at'])}"
            self.next_database_refresh = 0.0
        except self.server.LivePositionUnavailable as exc:
            self.status = str(exc)

    def refresh_database(self) -> None:
        now = time.monotonic()
        if now >= self.next_database_refresh:
            self.recent = self.server.store.recent(20)
            self.next_database_refresh = now + 0.5

    def run(self) -> None:
        try:
            with TerminalSession() as terminal:
                while not self.stop_event.is_set():
                    frame_started = time.monotonic()
                    while not self.status_messages.empty():
                        self.status = self.status_messages.get()
                    self.refresh_database()
                    size = shutil.get_terminal_size((80, 24))
                    screen = render_screen(
                        self.server.get_live_position(),
                        self.recent,
                        self.status,
                        self.database_path,
                        width=size.columns,
                        height=size.lines,
                        color=self.color,
                    )
                    if screen != self.last_screen:
                        terminal.draw(screen)
                        self.last_screen = screen
                    key = terminal.read_key(0.1)
                    if key in ("q", "Q", "\x03"):
                        break
                    if key in ("s", "S"):
                        self.save_position()
                    elif key in ("b", "B"):
                        webbrowser.open(self.url)
                        self.status = f"Opened {self.url}"
                    time.sleep(max(0.0, 0.1 - (time.monotonic() - frame_started)))
        finally:
            self.stop_event.set()
            self.http_server.shutdown()
            self.http_server.server_close()


def package_check(http_port: int) -> int:
    data_directory = configure_environment(http_port)
    from app import server
    from bridge import dro_bridge

    dro_bridge.available_ports()
    screen = render_screen(
        server.get_live_position(),
        [],
        "Package check",
        os.environ["DATABASE_PATH"],
        color=False,
    )
    if "CURRENT POSITION" not in screen:
        print("TUI render check failed", file=sys.stderr)
        return 1
    print(f"Hain’t TUI package check passed; data directory: {data_directory}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.check:
        return package_check(args.http_port)
    if os.name == "nt" and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    application = TerminalApplication(args)
    try:
        application.run()
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
