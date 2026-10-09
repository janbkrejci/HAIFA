#!/usr/bin/env bash
# Installs HAIFA (the `factory` tool) from this bundle with uv. Bash on macOS/Linux, or Git Bash on native Windows.
set -euo pipefail

WHEEL="@WHEEL@"

if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv is not on PATH." >&2
    echo "Install it: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    echo "(or: brew install uv), then open a new terminal and run ./install.sh again." >&2
    exit 1
fi

cd "$(dirname "$0")"

if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -c SHA256SUMS
elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 -c SHA256SUMS
else
    echo "error: neither sha256sum nor shasum is available to verify SHA256SUMS." >&2
    exit 1
fi

uv tool install --force "$WHEEL" --constraints constraints.txt

echo
echo "HAIFA @VERSION@ installed. Check prerequisites and logins with: factory check"
