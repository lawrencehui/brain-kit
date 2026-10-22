#!/bin/sh
# curl -fsSL https://raw.githubusercontent.com/lawrencehui/brain-kit/main/get.sh | sh -s -- [--vault ~/brain] [flags]
# Downloads brain-kit to a temp dir and runs its installer with the same arguments.
set -eu
REPO="${BRAIN_KIT_REPO:-lawrencehui/brain-kit}"
REF="${BRAIN_KIT_REF:-main}"
URL="${BRAIN_KIT_TARBALL:-https://codeload.github.com/$REPO/tar.gz/$REF}"

command -v zsh >/dev/null 2>&1 || { echo "brain-kit needs zsh (macOS has it; on Linux: apt install zsh)." >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "brain-kit needs curl." >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl -fsSL "$URL" | tar -xz -C "$tmp" --strip-components=1
exec zsh "$tmp/install.sh" "$@"
