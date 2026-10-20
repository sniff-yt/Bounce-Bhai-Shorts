#!/usr/bin/env bash
# Force-push out/live/ to the orphan `live` branch every few seconds (dashboard live view).
# usage: bash scripts/live_push.sh loop &     |   bash scripts/live_push.sh once
set -u
cd "$(dirname "$0")/.."
SRC="$PWD/out/live"
REPO_URL="https://x-access-token:${GITHUB_TOKEN:-}@github.com/${GITHUB_REPOSITORY:-sniff-yt/Bounce-Bhai-Shorts}.git"
W=/tmp/bb-live
push_once() {
  [ -f "$SRC/status.json" ] || return 0
  rm -rf "$W" && mkdir -p "$W" && cp -f "$SRC"/status.json "$W"/ && { cp -f "$SRC"/frame.jpg "$W"/ 2>/dev/null || true; }
  ( cd "$W" && git init -q -b live && git -c user.name=bouncebhai-bot -c user.email=bot@users.noreply.github.com \
      add -A && git -c user.name=bouncebhai-bot -c user.email=bot@users.noreply.github.com commit -qm live \
      && git push -qf "$REPO_URL" live:live ) >/dev/null 2>&1 || echo "live push failed (ignored)"
}
case "${1:-once}" in
  loop) while true; do push_once; sleep "${BB_LIVE_EVERY:-6}"; done ;;
  *) push_once ;;
esac
