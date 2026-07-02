#!/usr/bin/env bash
# Deploy analytics dashboard to GitHub Pages.
# Usage:  bash tools/deploy-analytics.sh
#
# Prerequisites:
#   - npm, uv, git, npx
#   - metrics.db with imported data
#   - GitHub authentication (gh auth status)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/frontend/dist"
DATE=$(date +%Y-%m-%d)

echo "========================================"
echo "  Analytics Dashboard — Deploy to Pages"
echo "========================================"

# Step 1: Build frontend
echo ""
echo "[1/4] Building frontend …"
cd "$ROOT/frontend"
pnpm run build

# Step 2: Save snapshot & export JSON data
echo ""
echo "[2/4] Exporting metrics.db → JSON + snapshot …"
cd "$ROOT"
uv run python tools/export_metrics_json.py \
  --out "$DIST" \
  --save-snapshot "$DATE"

# Step 3: Deploy to gh-pages branch
echo ""
echo "[3/4] Deploying to gh-pages branch …"
cd "$ROOT"
npx gh-pages --dist "$DIST" --branch gh-pages --message "deploy: analytics $DATE"

# Step 4: Done
echo ""
echo "========================================"
echo "  Deploy complete!"
echo "  https://torolex.github.io/ai-video-pipeline/"
echo "========================================"
