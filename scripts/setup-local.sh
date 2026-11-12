#!/bin/sh
# Per-machine setup: git hooks, local config files, and each agent's
# Claude Code auto-memory pointed at its own memory/ directory.
# (autoMemoryDirectory is ignored in checked-in settings, so it goes in
#  .claude/settings.local.json, which is gitignored.)
set -e
cd "$(dirname "$0")/.."
root=$(pwd)
sh scripts/install-hooks.sh
[ -f .env ] || { cp .env.example .env; echo "created .env: fill in your tokens"; }
[ -f config.json ] || { cp config.example.json config.json; echo "created config.json: set owner_id"; }
[ -f .private-patterns ] || cat > .private-patterns <<'PAT'
# One regex per line. Commits that ADD a matching line are refused.
# Put the things that must never leave your machine here, for example:
# 123 Main St
# Room 4[0-9]{2}
# \+1 ?555[ -]?123[ -]?4567
PAT
for d in agents/*/; do
  a=$(basename "$d")
  mkdir -p "agents/$a/.claude"
  printf '{\n  "autoMemoryDirectory": "%s/agents/%s/memory"\n}\n' "$root" "$a" > "agents/$a/.claude/settings.local.json"
done
echo "local settings written for: $(ls agents | tr '\n' ' ')"
