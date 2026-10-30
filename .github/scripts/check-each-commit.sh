#!/usr/bin/env bash
# Usage: check-each-commit.sh <base> <head>
# Run a copy of this script from outside the work tree: it checks out older
# commits, in which this file may not exist.
# Builds every commit in base..head on its own, so the history stays bisectable:
# each commit must compile the Java core and byte-compile and lint the Python
# packages. Full test suites run on the head commit in the other CI jobs.
set -euo pipefail
base="$1"
head="$2"

if [[ "$base" =~ ^0+$ ]] || ! git cat-file -e "$base^{commit}" 2>/dev/null; then
  # New branch: check what it adds on top of main.
  base="$(git merge-base origin/main "$head")"
fi

# The ruff version locked at the head; older commits are linted with the same rules engine.
RUFF_VERSION="$(grep -A1 '^name = "ruff"' uv.lock | sed -n 's/^version = "\(.*\)"/\1/p')"

commits=$(git rev-list --reverse "$base..$head")
if [[ -z "$commits" ]]; then
  echo "No new commits to check."
  exit 0
fi

# Resolve Maven dependencies once, at the head, so per-commit builds are fast.
(cd services/core && mvn -B -q -DskipTests dependency:go-offline > /dev/null 2>&1 || true)

failed=0
report=""
for commit in $commits; do
  subject="$(git log -1 --format=%s "$commit")"
  git checkout -q "$commit"
  if [[ -f services/core/pom.xml ]] && ! (cd services/core && mvn -B -q -o -DskipTests -Dspotless.check.skip=true compile > /tmp/build.log 2>&1); then
    echo "FAIL ${commit:0:7} $subject (java)"; tail -20 /tmp/build.log
    report+="FAIL ${commit:0:7} $subject (java)"$'\n'; failed=1; continue
  fi
  if ! (python3 -m compileall -q services data > /dev/null && uvx "ruff@$RUFF_VERSION" check -q . > /tmp/ruff.log 2>&1); then
    echo "FAIL ${commit:0:7} $subject (python)"; cat /tmp/ruff.log
    report+="FAIL ${commit:0:7} $subject (python)"$'\n'; failed=1; continue
  fi
  echo "ok   ${commit:0:7} $subject"
  report+="ok ${commit:0:7} $subject"$'\n'
done
git checkout -q "$head"
encoded="$(printf '%s' "$report" | python3 -c 'import sys; t=sys.stdin.read(); print(t.replace("%","%25").replace("\n","%0A"), end="")')"
echo "::notice title=history tests::$encoded"
exit "$failed"
