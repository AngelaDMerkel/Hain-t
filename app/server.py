from __future__ import annotations

import json
import mimetypes
import os
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .storage import MeasurementStore, utc_now


ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "static"
DATABASE_PATH = os.environ.get("DATABASE_PATH", str(ROOT.parent / "dro.sqlite3"))
PORT = int(os.environ.get("PORT", "8080"))
BIND_ADDRESS = os.environ.get("BIND_ADDRESS", "0.0.0.0")
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")

store = MeasurementStore(DATABASE_PATH)
live_lock = threading.Lock()
live_axes: dict[str, dict[str, object]] = {}
live_updated_at: str | None = None


def update_live_position(payload: dict[str, object]) -> dict[str, object]:
    global live_updated_at
    axis = str(payload.get("axis", "")).strip().upper()
    unit = str(payload.get("unit", "mm")).strip().lower()
    if not axis:
        raise ValueError("Axis is required")
    if not unit:
        raise ValueError("Unit is required")
    if "value" not in payload:
        raise ValueError("Value is required")

    measurement: dict[str, object] = {
        "axis": axis,
        "value": float(payload["value"]),
        "unit": unit,
        "raw": str(payload["raw"]) if payload.get("raw") is not None else None,
        "received_at": str(payload.get("received_at") or utc_now()),
    }
    with live_lock:
        live_axes[axis] = measurement
        live_updated_at = utc_now()
    return measurement


def get_live_position() -> dict[str, object]:
    with live_lock:
        return {
            "axes": {axis: dict(measurement) for axis, measurement in live_axes.items()},
            "updated_at": live_updated_at,
        }


class Handler(BaseHTTPRequestHandler):
    server_version = "DROUtility/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def _send_json(self, payload: object, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, object]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            value = json.loads(raw or b"{}")
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Request body must be valid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("Request body must be a JSON object")
        return value

    def _serve_static(self, relative: str) -> None:
        relative = relative or "index.html"
        candidate = (STATIC_ROOT / relative).resolve()
        if STATIC_ROOT not in candidate.parents and candidate != STATIC_ROOT:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = candidate.read_bytes()
        content_type, _ = mimetypes.guess_type(candidate.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self._send_json({}, HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        try:
            if path == "/api/health":
                self._send_json({"status": "ok", "database": DATABASE_PATH})
            elif path == "/api/status":
                self._send_json(store.summary())
            elif path == "/api/live":
                self._send_json(get_live_position())
            elif path == "/api/measurements":
                query = urlparse(self.path).query
                values = dict(item.split("=", 1) for item in query.split("&") if "=" in item)
                limit = int(values.get("limit", "100"))
                self._send_json({"measurements": store.recent(limit), "limit": limit})
            elif path == "/":
                self._serve_static("index.html")
            elif path.startswith("/static/"):
                self._serve_static(path.removeprefix("/static/"))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:
        path = unquote(urlparse(self.path).path)
        try:
            payload = self._read_json()
            if path == "/api/live":
                self._send_json(update_live_position(payload), HTTPStatus.OK)
            elif path == "/api/positions":
                snapshot = get_live_position()
                axes = snapshot["axes"]
                updated_at = snapshot["updated_at"]
                fresh = False
                if isinstance(updated_at, str):
                    fresh = (datetime.now(timezone.utc) - datetime.fromisoformat(updated_at)).total_seconds() < 2
                if not fresh or not isinstance(axes, dict) or "X" not in axes or "Y" not in axes:
                    self._send_json(
                        {"error": "A current X and Y position is required before saving"},
                        HTTPStatus.CONFLICT,
                    )
                    return
                saved = store.add_snapshot([axes["X"], axes["Y"]])
                self._send_json({"measurements": saved}, HTTPStatus.CREATED)
            elif path == "/api/measurements":
                result = store.add(
                    axis=str(payload.get("axis", "")),
                    value=float(payload["value"]),
                    unit=str(payload.get("unit", "mm")),
                    raw=str(payload["raw"]) if payload.get("raw") is not None else None,
                    received_at=str(payload["received_at"]) if payload.get("received_at") else None,
                )
                self._send_json(result, HTTPStatus.CREATED)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except KeyError as exc:
            self._send_json({"error": f"Missing field: {str(exc).strip(chr(39))}"}, HTTPStatus.BAD_REQUEST)
        except (TypeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)


def create_server() -> ThreadingHTTPServer:
    return ThreadingHTTPServer((BIND_ADDRESS, PORT), Handler)


def main() -> None:
    server = create_server()
    print(f"DRO utility listening on http://{BIND_ADDRESS}:{PORT}", flush=True)
    print(f"SQLite database: {DATABASE_PATH}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
