#!/usr/bin/env bash
# Link the bundled HomeBox CLI into ~/.local/bin so it can be called as
# `homebox` (or "$HOME/.local/bin/homebox" when ~/.local/bin is not on PATH).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${HOME}/.local/bin"
SCRIPT="${HERE}/homebox.py"

if [ ! -f "${SCRIPT}" ]; then
  echo "error: ${SCRIPT} not found" >&2
  exit 1
fi

mkdir -p "${TARGET}"
chmod +x "${SCRIPT}"
ln -sf "${SCRIPT}" "${TARGET}/homebox"
echo "linked ${TARGET}/homebox -> ${SCRIPT}"
case ":${PATH}:" in
  *":${TARGET}:"*) ;;
  *) echo "note: ${TARGET} is not on PATH; call ${TARGET}/homebox or add it to PATH" ;;
esac
