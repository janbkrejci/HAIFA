#!/usr/bin/env bash
# Installs GIRO (the `factory` tool) from this bundle with uv. Bash on macOS/Linux, or Git Bash on native Windows.
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

bin="$(uv tool dir --bin)"
existing="$(command -v giro || true)"
if [ -n "$existing" ]; then
    if { [ "$existing" != "$bin/giro" ] && [ "$existing" != "$bin/giro.exe" ]; } || ! uv tool list | grep -Eq '^ *- giro(\.exe)?$'; then
        echo "error: giro already exists on PATH ($existing); resolve the collision before installing." >&2
        exit 1
    fi
fi
uv tool install --force "$WHEEL" --constraints constraints.txt

# The library: clone the default team library (GIRO_LIBRARY_URL overrides it); without
# network a local library from the seed (factory warns). Then every seed item of the library
# is refreshed to this version's seed (giro library seed); items the seed lacks and
# the repos' .factory/ copies (the customizations) stay. A failed refresh only warns.
echo
echo "== Setting up the library"
bin="$(uv tool dir --bin 2>/dev/null || true)"
if [ -n "$bin" ] && command -v cygpath >/dev/null 2>&1; then
    bin="$(cygpath -u "$bin")"
fi
factory=""
for candidate in "$bin/giro" "$bin/giro.exe"; do
    if [ -n "$bin" ] && [ -x "$candidate" ]; then
        factory="$candidate"
        break
    fi
done
library=""
if [ -z "$factory" ]; then
    echo "warning: giro is not in the uv tool directory; set up the library later with:" >&2
    echo "  giro library clone --seed-fallback" >&2
elif status="$("$factory" library status --json 2>/dev/null)"; then
    library="ok"
elif printf '%s' "$status" | grep -q '"library_missing"'; then
    if "$factory" library clone --seed-fallback; then
        library="ok"
    else
        echo "warning: the library is not set up; run: giro library clone --seed-fallback" >&2
    fi
else
    echo "warning: giro library status failed; check the library with: giro check" >&2
fi
if [ -n "$library" ]; then
    echo "Refreshing the library to GIRO @VERSION@"
    if ! "$factory" library seed; then
        echo "warning: the library was not refreshed; run: giro library seed" >&2
    fi
fi

echo
echo "GIRO @VERSION@ installed. Check prerequisites and logins with: giro check"
