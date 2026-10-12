#!/usr/bin/env bash
# Uninstalls HAIFA (the `factory` tool). --purge also deletes the HAIFA home (library, logs,
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

# The same rules as aifactory.home.haifa_home.
if [ -n "${HAIFA_HOME:-}" ]; then
    home_dir="$HAIFA_HOME"
elif [ -n "${XDG_CONFIG_HOME:-}" ]; then
    home_dir="$XDG_CONFIG_HOME/haifa"
else
    home_dir="$HOME/.config/haifa"
fi

if [ -z "$purge" ] && [ -d "$home_dir" ]; then
    purge="no"
    if [ -t 0 ]; then
        printf "Delete also the HAIFA data in %s (library with unpushed changes, logs, settings)? [y/N] " "$home_dir"
        read -r answer
        case "$answer" in y|Y|yes|a|ano) purge="yes" ;; esac
    fi
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
    if [ -n "${HAIFA_LIBRARY:-}" ]; then
        echo "The library $HAIFA_LIBRARY (HAIFA_LIBRARY) is outside it and stays."
    fi
elif [ -d "$home_dir" ]; then
    echo "HAIFA data stay in $home_dir"
fi
echo "Dependencies and .factory/ in repositories stay."
