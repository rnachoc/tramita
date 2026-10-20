#!/usr/bin/env bash
# Usage: run-step.sh "<title>" <command...>
# Runs a CI command, streams its output, and on failure publishes the last lines
# as an error annotation so the cause is visible in the checks summary and API
# without opening the raw job log.
set -uo pipefail
title="$1"; shift
log="$(mktemp)"
"$@" 2>&1 | tee "$log"
status=${PIPESTATUS[0]}
if [[ $status -ne 0 ]]; then
  tail -n "${ANNOTATION_LINES:-120}" "$log" \
    | sed -E 's/\x1b\[[0-9;]*[A-Za-z]//g' \
    | python3 -c 'import sys; t=sys.stdin.read()[-60000:]; print(t.replace("%","%25").replace("\r","").replace("\n","%0A"), end="")' \
    > "$log.tail"
  echo "::error title=${title}::$(cat "$log.tail")"
fi
exit "$status"
