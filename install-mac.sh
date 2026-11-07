#!/bin/bash
# Install (or update) GeoLab on a Mac with one command:
#
#   curl -fsSL https://raw.githubusercontent.com/ArghoAdhikary/GeoLab/main/install-mac.sh | bash
#
# - picks the Apple Silicon (M1/M2/M3/M4) or Intel build for this Mac
# - downloads the latest release from GitHub and puts GeoLab.app in /Applications
#   (or ~/Applications when /Applications cannot be written)
# - clears the download quarantine and signs the app for this Mac, so macOS opens it
#   (GeoLab is not signed with a paid Apple developer certificate)
set -euo pipefail

REPO="ArghoAdhikary/GeoLab"
TAG="${GEOLAB_TAG:-latest}"
case "$(uname -m)" in
  arm64) ASSET="GeoLab-macos-apple-silicon.zip"; KIND="Apple Silicon" ;;
  x86_64)
    if [ "$(sysctl -n sysctl.proc_translated 2>/dev/null || echo 0)" = "1" ]; then
      ASSET="GeoLab-macos-apple-silicon.zip"; KIND="Apple Silicon"
    else
      ASSET="GeoLab-macos-intel.zip"; KIND="Intel"
    fi ;;
  *) echo "Unsupported Mac: $(uname -m)"; exit 1 ;;
esac
if [ "$TAG" = "latest" ]; then
  URL="https://github.com/$REPO/releases/latest/download/$ASSET"
else
  URL="https://github.com/$REPO/releases/download/$TAG/$ASSET"
fi

DEST="/Applications"
if [ ! -w "$DEST" ]; then DEST="$HOME/Applications"; mkdir -p "$DEST"; fi
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "GeoLab for $KIND Macs"
echo "Downloading $URL"
curl -fL --progress-bar -o "$TMP/geolab.zip" "$URL"
ditto -x -k "$TMP/geolab.zip" "$TMP"
if [ ! -d "$TMP/GeoLab.app" ]; then echo "The download did not contain GeoLab.app"; exit 1; fi

osascript -e 'tell application "GeoLab" to quit' >/dev/null 2>&1 || true
rm -rf "$DEST/GeoLab.app"
ditto "$TMP/GeoLab.app" "$DEST/GeoLab.app"
xattr -dr com.apple.quarantine "$DEST/GeoLab.app" 2>/dev/null || true
codesign --force --deep --sign - "$DEST/GeoLab.app" >/dev/null 2>&1 || true

echo "Installed: $DEST/GeoLab.app"
if [ -z "${GEOLAB_NO_OPEN:-}" ]; then open "$DEST/GeoLab.app"; fi
