#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import select
import signal
import sys
import termios
import time
import tty
import urllib.error
import urllib.request
from datetime import datetime, timezone


LINE_PATTERN = re.compile(
    r"^\s*(?P<axis>[A-Za-z])\s*=\s*(?P<value>[+-]?\s*\d+(?:\.\d+)?)\s*(?P<suffix>.*)$"
)
RUNNING = True
POLL_COMMANDS = {
    "ctrl-b": b"\x02",
    "actual-position": b"\x1bA0200\r",
}


def parse_dro_line(line: str, default_unit: str = "mm") -> dict[str, object] | None:
    match = LINE_PATTERN.match(line)
    if not match:
        return None
    value_text = match.group("value").replace(" ", "")
    suffix = match.group("suffix").strip()
    unit = "in" if '"' in suffix else default_unit
    return {
        "axis": match.group("axis").upper(),
        "value": float(value_text),
        "unit": unit,
        "raw": line,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


def find_port(requested: str) -> str:
    if requested != "auto":
        return requested
    matches = sorted(glob.glob("/dev/cu.usbmodem*"))
    if not matches:
        raise FileNotFoundError("No /dev/cu.usbmodem* DRO serial port found")
    if len(matches) > 1:
        raise RuntimeError(f"Multiple USB modem ports found; specify one explicitly: {', '.join(matches)}")
    return matches[0]


def configure_port(fd: int, baud: int) -> None:
    speed = getattr(termios, f"B{baud}", None)
    if speed is None:
        raise ValueError(f"Unsupported baud rate: {baud}")
    tty.setraw(fd)
    attrs = termios.tcgetattr(fd)
    attrs[4] = speed
    attrs[5] = speed
    attrs[2] |= termios.CLOCAL | termios.CREAD
    attrs[2] &= ~(termios.PARENB | termios.CSTOPB)
    if hasattr(termios, "CRTSCTS"):
        attrs[2] &= ~termios.CRTSCTS
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def post_json(endpoint: str, payload: dict[str, object], timeout: float = 5.0) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API returned HTTP {exc.code}: {detail}") from exc


def stop(_signum: int, _frame: object) -> None:
    global RUNNING
    RUNNING = False


def stream(args: argparse.Namespace) -> None:
    buffer = b""
    poll_command = POLL_COMMANDS[args.poll_command]
    while RUNNING:
        fd = -1
        try:
            port = find_port(args.port)
            fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            configure_port(fd, args.baud)
            mode = f"polling every {args.poll_interval:g}s" if args.poll_interval > 0 else "manual send mode"
            print(f"Connected to {port} at {args.baud} baud; {mode}", flush=True)
            next_poll = time.monotonic()
            while RUNNING:
                timeout = 1.0
                if args.poll_interval > 0:
                    now = time.monotonic()
                    if now >= next_poll:
                        os.write(fd, poll_command)
                        next_poll = now + args.poll_interval
                    timeout = min(timeout, max(0.0, next_poll - time.monotonic()))

                readable, _, _ = select.select([fd], [], [], timeout)
                if not readable:
                    continue
                chunk = os.read(fd, 4096)
                if not chunk:
                    raise OSError("DRO serial port closed")
                buffer += chunk
                while b"\n" in buffer:
                    raw_line, buffer = buffer.split(b"\n", 1)
                    line = raw_line.rstrip(b"\r").decode("ascii", errors="replace")
                    measurement = parse_dro_line(line, args.unit)
                    if measurement is None:
                        print(f"Ignored unrecognized line: {line!r}", file=sys.stderr, flush=True)
                        continue
                    try:
                        result = post_json(args.endpoint, measurement)
                        if args.verbose:
                            print(
                                f"{measurement['axis']}={measurement['value']} {measurement['unit']} "
                                f"-> live update accepted",
                                flush=True,
                            )
                    except Exception as exc:
                        print(f"Could not forward measurement: {exc}", file=sys.stderr, flush=True)
        except Exception as exc:
            print(f"Serial bridge error: {exc}; retrying in {args.retry_seconds:g}s", file=sys.stderr, flush=True)
            time.sleep(args.retry_seconds)
        finally:
            if fd >= 0:
                os.close(fd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Forward HEIDENHAIN DRO readings to the inspection API")
    parser.add_argument("--port", default="auto", help="Serial path or 'auto' (default: auto)")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate (default: 115200)")
    parser.add_argument("--unit", choices=("mm", "in"), default="mm", help="Unit when the DRO line has no unit marker")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8080/api/live")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.25,
        help="Seconds between position requests; use 0 for manual send mode (default: 0.25)",
    )
    parser.add_argument(
        "--poll-command",
        choices=tuple(POLL_COMMANDS),
        default="ctrl-b",
        help="DRO position request command (default: ctrl-b)",
    )
    parser.add_argument("--retry-seconds", type=float, default=2.0)
    parser.add_argument("--verbose", action="store_true", help="Print every live axis update")
    return parser


def main() -> None:
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    stream(build_parser().parse_args())


if __name__ == "__main__":
    main()
