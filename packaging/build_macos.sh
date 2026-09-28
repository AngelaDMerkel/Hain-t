#!/usr/bin/env bash
set -euo pipefail

python -m PyInstaller \
  --clean \
  --noconfirm \
  --windowed \
  --name Haint \
  --icon packaging/Haint.icns \
  --paths . \
  --add-data "app/static:app/static" \
  --add-data "LICENSE:." \
  --add-data "THIRD_PARTY_NOTICES.md:." \
  desktop/launcher.py

python -m PyInstaller \
  --clean \
  --noconfirm \
  --onefile \
  --name haint-tui \
  --icon packaging/Haint.icns \
  --paths . \
  --add-data "app/static:app/static" \
  --add-data "LICENSE:." \
  --add-data "THIRD_PARTY_NOTICES.md:." \
  desktop/tui.py
