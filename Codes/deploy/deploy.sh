#!/usr/bin/env bash
# Deploy WASL from this repo to /home/Debz/Host/wasl (same host). Idempotent.
#   Codes/deploy/deploy.sh            code + web + migrations + restart
#   Codes/deploy/deploy.sh --reseed   also wipe + seed + train + score + prewarm
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${DEST:-/home/Debz/Host/wasl}"
mkdir -p "$DEST/backend" "$DEST/web" "$DEST/docs" "$DEST/logs"
[ -f "$DEST/.env" ] || { echo "Create $DEST/.env first (see .env.example)"; exit 1; }

rsync -a --delete --exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude 'artifacts/*' --exclude '.env*' \
  "$REPO/backend/" "$DEST/backend/"
rsync -a "$REPO/docs/" "$DEST/docs/"
install -m 755 "$REPO/deploy/host/run.sh" "$REPO/deploy/host/stop.sh" "$REPO/deploy/host/autostart.sh" "$DEST/"

[ -x "$DEST/backend/.venv/bin/python" ] || python3.11 -m venv "$DEST/backend/.venv"
"$DEST/backend/.venv/bin/pip" install -q -e "$DEST/backend"

(cd "$REPO/frontend" && npm run build --silent)
rsync -a --delete --exclude assets/ "$REPO/frontend/dist/" "$DEST/web/"
# Keep superseded hashed chunks so tabs opened before this deploy still load their pages; prune after 14 days.
rsync -a "$REPO/frontend/dist/assets/" "$DEST/web/assets/"
find "$DEST/web/assets" -type f -mtime +14 -delete

cd "$DEST/backend"
export WASL_ENV_FILE="$DEST/.env"
.venv/bin/alembic upgrade head
if [ "${1:-}" = "--reseed" ]; then
  .venv/bin/python -m app.synth.seed
  .venv/bin/python -m app.ml.train --seed 42
fi
"$DEST/run.sh"
