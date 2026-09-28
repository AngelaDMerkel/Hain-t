# Hain’t

> **It Hain’t Working**

Hain’t is a small, open-source position capture service for ACU-RITE/HEIDENHAIN digital readouts. It polls a DRO over USB, shows nearly live X/Y coordinates in a browser, and saves operator-selected positions to a timestamped SQLite database.

![Hain’t showing a live X/Y position and saved measurements](docs/haint.jpg)

## Why this exists

Hain’t began as a practical replacement for **HEIDENHAIN GAGE-CHEK Wedge** in a DRO300 workflow. The name—and the slogan, “It Hain’t Working”—is a restrained nod to the experience of persuading antiquated, opaque tooling to perform a straightforward data-transfer job.

GAGE-CHEK Wedge was a poor fit for this installation: it is a Windows desktop product with a trial-license model, and its workflow focuses on transferring readings into Excel, the cursor, or a text field. Getting reliable data from the connected DRO300 proved far more difficult than it should have been. We needed a transparent tool that could run locally, expose an ordinary HTTP API, keep a durable audit trail, and later feed a separate engineering-validation stack.

Hain’t deliberately does less:

- polls the DRO instead of waiting for an operator to press **Send Position**;
- presents the current coordinates in a browser;
- saves a position only when the operator chooses to;
- persists measurements in an ordinary SQLite database;
- has no proprietary runtime, subscription, trial period, or Python package dependencies;
- separates hardware access from the container so the collector can later move to Windows.

This project is independent of HEIDENHAIN and is not an official replacement or supported HEIDENHAIN product. ACU-RITE, HEIDENHAIN, DRO300, and GAGE-CHEK are trademarks of their respective owners. See the [official GAGE-CHEK Wedge product page](https://www.heidenhain.us/products/gage-chek-wedge/) and the [DRO203/DRO300 operating instructions](https://old.acu-rite.com/pdf/1221048-24_DRO_203_300_OI_en.pdf) for vendor documentation.

## Current scope

The current release is a macOS proof of operation for a USB-connected DRO300. It includes:

- automatic `/dev/cu.usbmodem*` discovery;
- 115200-baud USB serial communication;
- active position requests at 4 Hz by default;
- live X/Y display with connection freshness detection;
- explicit, synchronized X/Y snapshots;
- UTC timestamps and SQLite persistence;
- a dependency-free Python HTTP service;
- Docker packaging and a persistent data volume;
- a small JSON API intended for future integrations.

Label scanning, tolerance checks, engineering-data lookup, authentication, and the INNERGY utilities integration are intentionally outside this repository.

## Compatibility

| Component | Status |
| --- | --- |
| ACU-RITE/HEIDENHAIN DRO300 | Tested over USB |
| DRO203 | Expected to use the same external-operation protocol; not yet tested here |
| macOS host collector | Supported |
| Docker Desktop for macOS | Supported |
| Windows host collector | Planned; the HTTP service is already portable |
| Linux host collector | Not tested |

The bridge uses the documented `Ctrl+B` current-position request. It can alternatively send `ESC A0200 CR`, which the DRO operating instructions describe as **Send actual position**.

## Requirements

- an ACU-RITE/HEIDENHAIN DRO with USB device support;
- a data-capable USB cable;
- macOS with Python 3.11 or newer;
- Docker Desktop with Docker Compose;
- `make` for the convenience commands, or the equivalent commands shown below.

No `pip install` step is required. Both Python components use only the standard library.

## Install and run

Clone the repository and enter it:

```bash
git clone <repository-url> haint
cd haint
```

Connect the powered DRO to the Mac. Confirm that macOS created a serial device:

```bash
ls /dev/cu.usbmodem*
```

Start the containerized web service and database:

```bash
make up
```

Start the USB bridge in a second terminal and leave it running:

```bash
make bridge
```

Open [http://localhost:8080](http://localhost:8080). The status should change to **Live**, and moving an axis should update the displayed coordinates within roughly half a second.

Use **Save position** to persist the displayed X/Y pair. Live polling itself does not write to SQLite, so leaving Hain’t open does not create an unbounded stream of database rows.

Stop the service with:

```bash
make down
```

The Docker volume is retained by `make down`. To remove it deliberately, run `docker compose down --volumes`.

### Without Make

```bash
docker compose up --build -d
python3 bridge/dro_bridge.py --port auto --poll-interval 0.25
```

## Bridge options

```text
--port PATH                 Serial path or "auto" (default: auto)
--baud RATE                 Serial baud rate (default: 115200)
--unit {mm,in}              Unit when the DRO output has no unit marker
--endpoint URL              Live-update endpoint
--poll-interval SECONDS     Request interval; 0 enables manual-send mode
--poll-command COMMAND      ctrl-b or actual-position
--retry-seconds SECONDS     Delay after disconnects or errors
--verbose                   Print every accepted axis update
```

Examples:

```bash
# Select a specific device when more than one USB modem is connected
python3 bridge/dro_bridge.py --port /dev/cu.usbmodem12101

# Poll twice per second
python3 bridge/dro_bridge.py --poll-interval 0.5

# Try the alternate documented position command
python3 bridge/dro_bridge.py --poll-command actual-position

# Receive only readings sent from the DRO controls
python3 bridge/dro_bridge.py --poll-interval 0
```

Do not run GAGE-CHEK Wedge, a serial terminal, or another collector against the same port at the same time. Serial devices normally permit only one active owner.

## Architecture

```text
┌────────────────────────────┐
│ DRO300 USB serial device   │
│ /dev/cu.usbmodem* @ 115200 │
└──────────────┬─────────────┘
               │ Ctrl+B every 250 ms
               ▼
┌────────────────────────────┐       HTTP/JSON       ┌──────────────────────────┐
│ macOS host bridge          │ ────────────────────▶ │ Dockerized Python service│
│ bridge/dro_bridge.py       │     POST /api/live    │ app/server.py            │
└────────────────────────────┘                       └─────────────┬────────────┘
                                                                 │
                                                    ┌────────────┴─────────────┐
                                                    ▼                          ▼
                                             Browser UI                 SQLite volume
                                             localhost:8080             /data/dro.sqlite3
```

Docker Desktop on macOS does not pass host `/dev/cu.*` devices directly into Linux containers. The small host bridge owns the serial connection; the portable service owns the UI, API, and database. This boundary is intentional: a future Windows collector can submit the same JSON without changing the service.

## Data behavior

The bridge receives lines such as:

```text
X =+  2087.65 R
Y =+   456.35 R
```

Each live axis update is normalized to:

```json
{
  "axis": "X",
  "value": 2087.65,
  "unit": "mm",
  "raw": "X =+  2087.65 R",
  "received_at": "2026-09-28T13:51:45.583492+00:00"
}
```

Live coordinates are held in memory. Pressing **Save position** writes the current X and Y values in one SQLite transaction; both rows receive the same `stored_at` timestamp and are displayed as one saved position.

## HTTP API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Container health check |
| `GET` | `/api/live` | Latest in-memory axis values |
| `POST` | `/api/live` | Update one live axis value |
| `POST` | `/api/positions` | Persist the current live X/Y snapshot |
| `GET` | `/api/measurements?limit=100` | Read saved axis records, newest first |
| `POST` | `/api/measurements` | Persist one axis record directly |
| `GET` | `/api/status` | Saved-record count and latest record |

Save the current live position:

```bash
curl -X POST -H 'Content-Type: application/json' -d '{}' \
  http://localhost:8080/api/positions
```

Read recent saved records:

```bash
curl 'http://localhost:8080/api/measurements?limit=20'
```

The API currently has no authentication. Docker Compose binds it to `127.0.0.1` by default. Do not expose it to an untrusted network. For a controlled LAN deployment, change the port mapping in `compose.yaml` from `127.0.0.1:8080:8080` to `8080:8080` and add appropriate network controls.

## SQLite data and backup

The database lives at `/data/dro.sqlite3` in the `dro-data` Docker volume. Records contain:

```text
id, axis, value, unit, raw, received_at, stored_at
```

Inspect recent records:

```bash
docker compose exec dro-utility python -c \
  "import sqlite3; c=sqlite3.connect('/data/dro.sqlite3'); print(c.execute('select * from measurements order by id desc limit 10').fetchall())"
```

Create a consistent SQLite backup:

```bash
docker compose exec dro-utility python -c \
  "import sqlite3; src=sqlite3.connect('/data/dro.sqlite3'); dst=sqlite3.connect('/data/backup.sqlite3'); src.backup(dst)"

docker compose cp dro-utility:/data/backup.sqlite3 ./backup.sqlite3
```

## Troubleshooting

### The DRO powers on, but no serial device appears

Power alone does not prove that the cable carries data. Try another data-capable USB cable and port, then check:

```bash
system_profiler SPUSBDataType
ls /dev/cu.usbmodem*
```

The tested DRO appeared as `HEIDENHAIN DRO` and `/dev/cu.usbmodem12101`.

### Hain’t says “Waiting for DRO”

- confirm the bridge terminal is still running;
- make sure another program does not own the serial port;
- run the bridge with `--verbose` to inspect accepted readings;
- try `--poll-command actual-position` for different firmware;
- verify that the service responds at `http://localhost:8080/api/health`.

### Multiple `/dev/cu.usbmodem*` devices are connected

Automatic detection intentionally stops rather than guessing. Pass the intended path explicitly with `--port`.

### The container is healthy but the DRO is unavailable

That is expected if only `docker compose up` is running. The macOS bridge is a separate host process because Docker Desktop cannot directly open the Mac serial device.

### Port 8080 is already in use

Change both the published port in `compose.yaml` and the bridge `--endpoint`, or stop the process already using the port.

## Development

Run the test suite:

```bash
make test
```

The tests cover captured DRO line parsing, invalid input, timestamped storage, snapshot consistency, ordering, and result limits.

Project layout:

```text
app/                    HTTP service, UI, and SQLite storage
bridge/dro_bridge.py    macOS USB serial collector
docs/                   Documentation images
tests/                  Standard-library unit tests
compose.yaml            Local container topology and persistent volume
Dockerfile              Unprivileged production image
Makefile                Common development and operation commands
```

Contributions should keep the host bridge and container service loosely coupled. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

- Windows serial collector and deployment documentation;
- configurable device identity instead of first-port discovery;
- schema-level saved-position records rather than paired axis rows;
- CSV export and database retention controls;
- authenticated, network-safe deployment mode;
- integration contract for label scanning and engineering tolerance checks.

## License

[MIT](LICENSE)
