#!/usr/bin/env bash
# Usage: run-step.sh "<title>" <command...>
# Runs a CI command and streams its output. Then:
# - on failure, publishes the last lines as an error annotation, so the cause is
#   visible in the checks summary and through the API without the raw job log.
#   GitHub truncates annotation messages at about 4 KB, so only the end of the
#   output (where errors usually are) is kept;
# - always, publishes the test-runner summaries it finds (Maven Surefire and
#   pytest) as a notice, so the number of tests that really ran is visible.
set -uo pipefail
title="$1"; shift
log="$(mktemp)"
"$@" 2>&1 | tee "$log"
status=${PIPESTATUS[0]}

encode() {
  sed -E 's/\x1b\[[0-9;]*[A-Za-z]//g' \
    | python3 -c 'import sys; t=sys.stdin.read()[-3800:]; print(t.replace("%","%25").replace("\r","").replace("\n","%0A"), end="")'
}

# Per-class and total Surefire lines, and pytest's final line.
summary="$(grep -E 'Tests run: [0-9]+, Failures: [0-9]+, Errors: [0-9]+, Skipped: [0-9]+(, Time elapsed: .* -- in .*)?$|[0-9]+ (passed|failed)' "$log" \
  | sed -E 's/, Time elapsed: [^-]*-- in dev\.tramita\.core\./ in /' | encode)"
if [[ -n "$summary" ]]; then
  echo "::notice title=${title} tests::${summary}"
fi
if [[ $status -ne 0 ]]; then
  echo "::error title=${title}::$(tail -n "${ANNOTATION_LINES:-120}" "$log" | encode)"
fi
exit "$status"
