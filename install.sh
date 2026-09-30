#!/usr/bin/env bash
# Symlink these skills, agents and tools into ~/.claude and ~/.local/bin.
# Existing non-symlink targets are moved to ~/.claude/.skills-install-backup/ first
# (not <name>.bak beside them: a .bak dir in ~/.claude/skills would load as a skill).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
link() { # link <src> <dest>
  mkdir -p "$(dirname "$2")"
  if [ -e "$2" ] && [ ! -L "$2" ]; then
    bk=~/.claude/.skills-install-backup/$(date +%Y%m%d%H%M%S); mkdir -p "$bk"
    mv "$2" "$bk/"; echo "backed up $2 -> $bk/"
  fi
  ln -sfn "$1" "$2"; echo "linked $2"
}
for s in "$here"/skills/*/;  do link "${s%/}" ~/.claude/skills/"$(basename "$s")"; done
for a in "$here"/agents/*.md; do link "$a" ~/.claude/agents/"$(basename "$a")"; done
for l in "$here"/lib/*.py;    do link "$l" ~/.claude/lib/"$(basename "$l")"; done
for b in "$here"/bin/*;       do link "$b" ~/.local/bin/"$(basename "$b")"; done
