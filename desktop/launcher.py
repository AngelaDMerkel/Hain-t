from __future__ import annotations

import argparse
import os
import queue
import sys
import threading
import webbrowser

from desktop.common import application_data_directory, bridge_arguments, configure_environment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the Hain’t desktop application")
    parser.add_argument("--serial-port", default=os.environ.get("HAINT_SERIAL_PORT", "auto"))
    parser.add_argument("--http-port", type=int, default=int(os.environ.get("HAINT_PORT", "8080")))
    parser.add_argument("--no-browser", action="store_true", help="Do not open the interface automatically")
    parser.add_argument("--check", action="store_true", help="Validate the packaged application and exit")
    return parser


def package_check(http_port: int) -> int:
    data_directory = configure_environment(http_port)
    try:
        import tkinter  # noqa: F401
    except ImportError as exc:
        print(f"Tkinter is unavailable in this package: {exc}", file=sys.stderr)
        return 1
    from app import server
    from bridge import dro_bridge

    dro_bridge.available_ports()

    required = (
        server.STATIC_ROOT / "index.html",
        server.STATIC_ROOT / "haint-lockup.png",
        server.STATIC_ROOT / "haint-lockup.gif",
        server.STATIC_ROOT / "haint-mark.png",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        print(f"Missing packaged assets: {', '.join(missing)}", file=sys.stderr)
        return 1
    print(f"Hain’t package check passed; data directory: {data_directory}")
    return 0


class DesktopApplication:
    def __init__(self, serial_port: str, http_port: int, open_browser: bool) -> None:
        import tkinter as tk
        from tkinter import ttk

        configure_environment(http_port)
        from app import server
        from bridge import dro_bridge

        self.server_module = server
        self.bridge_module = dro_bridge
        self.http_port = http_port
        self.url = f"http://127.0.0.1:{http_port}"
        self.stop_event = threading.Event()
        self.status_messages: queue.SimpleQueue[str] = queue.SimpleQueue()
        self.http_server = server.create_server()

        self.root = tk.Tk()
        self.root.title("Hain’t")
        self.root.minsize(500, 280)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        frame = ttk.Frame(self.root, padding=32)
        frame.pack(fill="both", expand=True)

        self.logo = tk.PhotoImage(file=server.STATIC_ROOT / "haint-lockup.gif").subsample(2)
        ttk.Label(frame, image=self.logo).pack(anchor="w")

        self.status = tk.StringVar(value="Starting local service…")
        ttk.Label(frame, textvariable=self.status, wraplength=430).pack(anchor="w", pady=(26, 18))

        controls = ttk.Frame(frame)
        controls.pack(fill="x", side="bottom")
        ttk.Button(controls, text="Open Hain’t", command=self.open_interface).pack(side="left")
        ttk.Button(controls, text="Quit", command=self.close).pack(side="right")

        threading.Thread(target=self.http_server.serve_forever, daemon=True, name="haint-http").start()
        bridge_args = bridge_arguments(serial_port, http_port)
        threading.Thread(
            target=dro_bridge.stream,
            args=(bridge_args, self.stop_event, self.status_messages.put),
            daemon=True,
            name="haint-serial",
        ).start()
        self.root.after(200, self.update_status)
        if open_browser:
            self.root.after(600, self.open_interface)

    def open_interface(self) -> None:
        webbrowser.open(self.url)

    def update_status(self) -> None:
        while not self.status_messages.empty():
            self.status.set(self.status_messages.get())
        if not self.stop_event.is_set():
            self.root.after(200, self.update_status)

    def close(self) -> None:
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        self.http_server.shutdown()
        self.http_server.server_close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    args = build_parser().parse_args()
    if args.check:
        return package_check(args.http_port)
    application = DesktopApplication(args.serial_port, args.http_port, not args.no_browser)
    application.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
