#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import serial
from serial.tools import list_ports


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


def available_ports() -> list[object]:
    return sorted(list_ports.comports(), key=lambda port: port.device)


def is_dro_port(port: object) -> bool:
    details = " ".join(
        str(getattr(port, attribute, "") or "")
        for attribute in ("description", "manufacturer", "product", "hwid")
    ).lower()
    return "heidenhain" in details or "acu-rite" in details or "dro" in details


def find_port(requested: str, ports: list[object] | None = None) -> str:
    if requested != "auto":
        return requested
    candidates = ports if ports is not None else available_ports()
    preferred = [port for port in candidates if is_dro_port(port)]
    matches = preferred or candidates
    if not matches:
        raise FileNotFoundError("No serial ports found; connect the DRO or specify --port")
    if len(matches) > 1:
        names = ", ".join(str(port.device) for port in matches)
        raise RuntimeError(f"Multiple serial ports found; specify one explicitly: {names}")
    return str(matches[0].device)


def open_port(port: str, baud: int) -> serial.Serial:
    return serial.Serial(
        port=port,
        baudrate=baud,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.1,
        write_timeout=1.0,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )


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


def should_run(stop_event: threading.Event | None = None) -> bool:
    return RUNNING and (stop_event is None or not stop_event.is_set())


def report_status(callback: object | None, message: str) -> None:
    if callable(callback):
        callback(message)


def stream(
    args: argparse.Namespace,
    stop_event: threading.Event | None = None,
    status_callback: object | None = None,
) -> None:
    poll_command = POLL_COMMANDS[args.poll_command]
    while should_run(stop_event):
        connection: serial.Serial | None = None
        try:
            port = find_port(args.port)
            connection = open_port(port, args.baud)
            buffer = b""
            mode = f"polling every {args.poll_interval:g}s" if args.poll_interval > 0 else "manual send mode"
            message = f"Connected to {port} at {args.baud} baud; {mode}"
            print(message, flush=True)
            report_status(status_callback, message)
            next_poll = time.monotonic()
            while should_run(stop_event):
                if args.poll_interval > 0:
                    now = time.monotonic()
                    if now >= next_poll:
                        connection.write(poll_command)
                        next_poll = now + args.poll_interval
                waiting = connection.in_waiting
                chunk = connection.read(min(max(waiting, 1), 4096))
                if not chunk:
                    continue
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
            message = f"Serial bridge error: {exc}; retrying in {args.retry_seconds:g}s"
            print(message, file=sys.stderr, flush=True)
            report_status(status_callback, message)
            if stop_event is not None:
                stop_event.wait(args.retry_seconds)
            else:
                time.sleep(args.retry_seconds)
        finally:
            if connection is not None:
                connection.close()


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
