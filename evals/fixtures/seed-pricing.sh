#!/usr/bin/env bash
# Seeds the eval workspace (the current directory) with the pricing fixture as a
# git repo on `main`, one initial commit, and a local bare `origin` so the
# gauntlet's `git fetch origin` works offline. Called from each case's scaffold.sh.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/pricing"
[ -f "$src/pricing.py" ] || { echo "fixture not found at $src" >&2; exit 1; }
cp -R "$src/." .
git init -q -b main
git config user.name "Eval Bot"
git config user.email "eval@example.invalid"
git config commit.gpgsign false
git add -A
git commit -q -m "chore: seed pricing fixture"
# Bare remote lives inside .git so it never shows up in `git status`.
git clone -q --bare . .git/eval-origin.git
git remote add origin "$PWD/.git/eval-origin.git"
git fetch -q origin
git branch -q --set-upstream-to=origin/main main
