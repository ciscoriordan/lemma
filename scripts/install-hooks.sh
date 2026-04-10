#!/usr/bin/env bash
#
# Install lemma's git hooks into .git/hooks.
#
# Creates a symlink from .git/hooks/pre-commit to scripts/pre-commit so that
# updates to the tracked hook script are picked up automatically. Any existing
# hook is backed up to pre-commit.backup.<timestamp>.
#
# Usage: ./scripts/install-hooks.sh

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

if [ ! -d "$repo_root/.git" ]; then
    echo "install-hooks.sh: $repo_root is not a git repository" >&2
    exit 1
fi

hook_src="$script_dir/pre-commit"
hook_dst="$repo_root/.git/hooks/pre-commit"

if [ ! -f "$hook_src" ]; then
    echo "install-hooks.sh: missing hook source at $hook_src" >&2
    exit 1
fi

chmod +x "$hook_src"

# Back up an existing hook that isn't already our symlink.
if [ -e "$hook_dst" ] || [ -L "$hook_dst" ]; then
    current_target=""
    if [ -L "$hook_dst" ]; then
        current_target="$(readlink "$hook_dst")"
    fi
    if [ "$current_target" != "$hook_src" ] && [ "$current_target" != "../../scripts/pre-commit" ]; then
        backup="$hook_dst.backup.$(date +%Y%m%d%H%M%S)"
        echo "install-hooks.sh: backing up existing hook to $backup"
        mv "$hook_dst" "$backup"
    else
        echo "install-hooks.sh: pre-commit already linked to scripts/pre-commit"
        exit 0
    fi
fi

ln -s "../../scripts/pre-commit" "$hook_dst"
echo "install-hooks.sh: installed pre-commit hook -> scripts/pre-commit"
echo "install-hooks.sh: bypass with \`git commit --no-verify\` when needed"
