#!/usr/bin/env bash
set -euo pipefail

version="${1:-$(tr -d '[:space:]' < VERSION)}"
architecture="$(dpkg --print-architecture)"

python -m PyInstaller \
  --clean \
  --noconfirm \
  --onefile \
  --name haint \
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
  --paths . \
  --add-data "app/static:app/static" \
  --add-data "LICENSE:." \
  --add-data "THIRD_PARTY_NOTICES.md:." \
  desktop/tui.py

package_root="$(mktemp -d)"
trap 'rm -rf "${package_root}"' EXIT

install -D -m 0755 dist/haint "${package_root}/usr/bin/haint"
install -D -m 0755 dist/haint-tui "${package_root}/usr/bin/haint-tui"
install -D -m 0644 packaging/haint.desktop \
  "${package_root}/usr/share/applications/haint.desktop"
install -D -m 0644 app/static/haint-mark.png \
  "${package_root}/usr/share/pixmaps/haint.png"
install -D -m 0644 LICENSE "${package_root}/usr/share/doc/haint/LICENSE"
install -D -m 0644 THIRD_PARTY_NOTICES.md \
  "${package_root}/usr/share/doc/haint/THIRD_PARTY_NOTICES.md"

mkdir -p "${package_root}/DEBIAN"
sed \
  -e "s/@VERSION@/${version}/" \
  -e "s/@ARCHITECTURE@/${architecture}/" \
  packaging/debian-control \
  > "${package_root}/DEBIAN/control"

mkdir -p dist
dpkg-deb --build --root-owner-group \
  "${package_root}" "dist/haint_${version}_${architecture}.deb"
