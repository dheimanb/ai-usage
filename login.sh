#!/usr/bin/env bash
# heiman runs this himself on the box desktop to log into Grok in the dedicated profile.
# It only opens a normal (headed) Chrome window. Nothing here reads cookies or tokens.
# Usage: ./login.sh [url]      (DISPLAY must point at the desktop you are watching, e.g. DISPLAY=:8 ./login.sh)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PROFILE="$HERE/profile-grok"
URL="${1:-https://grok.com/}"
: "${DISPLAY:?set DISPLAY to the box desktop you are viewing, e.g. DISPLAY=:8 ./login.sh}"
mkdir -p "$PROFILE"; chmod 700 "$PROFILE"
echo "Opening Chrome with profile $PROFILE on DISPLAY=$DISPLAY. Log in, open the usage page, note its URL, then CLOSE the window."
exec /opt/google/chrome/chrome --user-data-dir="$PROFILE" --no-first-run --no-default-browser-check "$URL"
