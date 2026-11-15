#!/usr/bin/env bash
# Uninstalls HAIFA (the `factory` tool). --purge also deletes the GIRO home (library, logs,
# env), --keep-data keeps it; without either the script asks on a terminal and keeps the data
# otherwise. Dependencies and the repositories' .factory/ stay. Bash on macOS and Linux.
set -euo pipefail

purge=""
for arg in "$@"; do
    case "$arg" in
        --purge) purge="yes" ;;
        --keep-data) purge="no" ;;
        *) echo "error: unknown argument $arg (use --purge or --keep-data)" >&2; exit 2 ;;
    esac
done

if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv is not on PATH; factory was installed with uv: uv tool uninstall aifactory" >&2
    exit 1
fi

# Resolve with this installation's shared rules before removing its executable.
bin="$(uv tool dir --bin)"
launcher="$bin/giro"
if [ ! -x "$launcher" ]; then launcher="$bin/giro.exe"; fi
if [ -x "$launcher" ]; then
    home_dir="$("$launcher" --data-home)"
else
    home_dir="${GIRO_HOME:-${HAIFA_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/giro}}"
    if [ -z "${GIRO_HOME:-${HAIFA_HOME:-}}" ] && [ -e "${XDG_CONFIG_HOME:-$HOME/.config}/haifa" ]; then
        echo "error: legacy home exists; inspect and set GIRO_HOME explicitly before uninstalling." >&2
        exit 1
    fi
fi
case "$home_dir" in
    "~") home_dir="$HOME" ;;
    "~/"*) home_dir="$HOME/${home_dir#\~/}" ;;
    "~"*) echo "error: cannot safely resolve this home without the installed GIRO launcher." >&2; exit 1 ;;
esac
if [ -n "${GIRO_HOME:-}" ] && [ -n "${HAIFA_HOME:-}" ] && [ "$GIRO_HOME" != "$HAIFA_HOME" ]; then
    echo "warning: GIRO_HOME conflicts with HAIFA_HOME; GIRO_HOME wins." >&2
fi

if [ -z "$purge" ] && [ -d "$home_dir" ]; then
    purge="no"
    if [ -t 0 ]; then
        printf "Delete also the GIRO data in %s (library with unpushed changes, logs, settings)? [y/N] " "$home_dir"
        read -r answer
        case "$answer" in y|Y|yes|a|ano) purge="yes" ;; esac
    fi
fi

if [ "$purge" = "yes" ] && [ -e "$home_dir/giro-migration.json" ]; then
    echo "error: migration data are protected; use --keep-data and follow the rollback instructions." >&2
    exit 1
fi

if uv tool list | grep -q '^aifactory '; then
    uv tool uninstall aifactory
    echo "factory uninstalled."
else
    echo "factory is not installed."
fi

if [ "$purge" = "yes" ] && [ -d "$home_dir" ]; then
    rm -rf "$home_dir"
    echo "Deleted $home_dir"
    library="${GIRO_LIBRARY:-${HAIFA_LIBRARY:-}}"
    if [ -n "$library" ]; then
        echo "The external library $library stays."
    fi
elif [ -d "$home_dir" ]; then
    echo "GIRO data stay in $home_dir"
fi
echo "Dependencies and .factory/ in repositories stay."
