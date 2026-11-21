#!/usr/bin/env bash
set -euo pipefail
# Scrub before any command against a disposable fixture repository.
while IFS= read -r name; do unset "$name"; done < <(git rev-parse --local-env-vars)
git init "$1"
