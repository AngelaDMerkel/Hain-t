# Contributing

Contributions that make Hain’t easier to operate, diagnose, or port are welcome.

## Before opening a change

1. Open an issue for protocol changes or new platform support so the hardware assumptions are explicit.
2. Keep the serial collector separate from the HTTP service. The service must not depend on a macOS device path.
3. Avoid adding runtime packages when the Python standard library provides a clear solution.
4. Preserve the distinction between live readings and operator-saved positions.

## Development workflow

```bash
git clone <your-fork-url> haint
cd haint
python3 -m unittest discover -s tests -v
docker compose up --build -d
```

When hardware is available, also run the bridge with `--verbose` and confirm that:

- X and Y update while an axis moves;
- the status changes when the USB cable is disconnected;
- polling does not increase the saved-record count;
- **Save position** adds one synchronized X/Y snapshot.

Use Conventional Commit subjects such as `feat:`, `fix:`, `docs:`, `test:`, and `chore:`. Include tests for parser, storage, or API behavior when practical.

## Pull requests

Describe the hardware and operating system used for testing. For serial-protocol changes, include a redacted sample of the raw device output. Do not include proprietary engineering data, production measurements, credentials, or database files.
