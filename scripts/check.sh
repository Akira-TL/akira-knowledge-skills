#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

uv run python -m unittest discover -s skills/knowledge/akira-knowledge/tests
git diff --check
