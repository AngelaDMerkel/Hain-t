$ErrorActionPreference = "Stop"

python -m PyInstaller `
  --clean `
  --noconfirm `
  --onefile `
  --windowed `
  --name Haint `
  --icon packaging/Haint.ico `
  --paths . `
  --add-data "app/static:app/static" `
  --add-data "LICENSE:." `
  --add-data "THIRD_PARTY_NOTICES.md:." `
  desktop/launcher.py

python -m PyInstaller `
  --clean `
  --noconfirm `
  --onefile `
  --name haint-tui `
  --icon packaging/Haint.ico `
  --paths . `
  --add-data "app/static:app/static" `
  --add-data "LICENSE:." `
  --add-data "THIRD_PARTY_NOTICES.md:." `
  desktop/tui.py
