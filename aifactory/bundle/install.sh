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

# The library: clone the default team library (HAIFA_LIBRARY_URL overrides it); without
# network a local library from the seed (factory warns). An existing library is left alone.
echo
echo "== Setting up the library"
bin="$(uv tool dir --bin 2>/dev/null || true)"
if [ -n "$bin" ] && command -v cygpath >/dev/null 2>&1; then
    bin="$(cygpath -u "$bin")"
fi
factory=""
for candidate in "$bin/factory" "$bin/factory.exe"; do
    if [ -n "$bin" ] && [ -x "$candidate" ]; then
        factory="$candidate"
        break
    fi
done
if [ -z "$factory" ]; then
    echo "warning: factory is not in the uv tool directory; set up the library later with:" >&2
    echo "  factory library clone --seed-fallback" >&2
elif status="$("$factory" library status --json 2>/dev/null)"; then
    echo "The library exists; it is left unchanged."
elif printf '%s' "$status" | grep -q '"library_missing"'; then
    if ! "$factory" library clone --seed-fallback; then
        echo "warning: the library is not set up; run: factory library clone --seed-fallback" >&2
    fi
else
    echo "warning: factory library status failed; check the library with: factory check" >&2
fi

echo
echo "HAIFA @VERSION@ installed. Check prerequisites and logins with: factory check"
