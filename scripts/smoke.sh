#!/usr/bin/env bash
# Smoke test a running deploy: the health endpoint and the UI. Add one real API call for the app below.
# Usage: scripts/smoke.sh <base-url>
set -euo pipefail
base=${1:?usage: scripts/smoke.sh <base-url>}
curl -fsS "$base/api/health" | grep -q '"ok":true' || { echo "smoke: /api/health failed" >&2; exit 1; }
curl -fsS "$base/" | grep -q '<div id="root">' || { echo "smoke: UI not served at /" >&2; exit 1; }
echo "smoke: ok ($base)"
