#!/usr/bin/env bash
# Commit + push only usage.json when it changed. Safe for hourly routine.
# Does NOT touch profile-grok or other local files.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d .git ]]; then
  echo "push_usage: no .git yet — init + remote first" >&2
  exit 1
fi

if [[ ! -f usage.json ]]; then
  echo "push_usage: usage.json missing" >&2
  exit 1
fi

# Validate before any commit
python3 validate_usage.py >/dev/null

# Stage only usage.json
git add -- usage.json

if git diff --cached --quiet -- usage.json; then
  echo "push_usage: no change"
  exit 0
fi

git -c user.email="${GIT_AUTHOR_EMAIL:-heiman@users.noreply.github.com}" \
    -c user.name="${GIT_AUTHOR_NAME:-heiman}" \
    commit -m "chore: update usage.json $(date -Iseconds)"

# Prefer origin/main; fall back to master
branch=$(git rev-parse --abbrev-ref HEAD)
git push -u origin "$branch"
echo "push_usage: pushed usage.json on $branch"
