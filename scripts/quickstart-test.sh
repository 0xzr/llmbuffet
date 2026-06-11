#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${FREELLMPOOL_QUICKSTART_WORKDIR:-}"
KEEP_WORKDIR="${FREELLMPOOL_QUICKSTART_KEEP:-0}"
INSTALL_TARGET="${FREELLMPOOL_QUICKSTART_PACKAGE:-freellmpool}"
MAX_SECONDS="${FREELLMPOOL_QUICKSTART_MAX_SECONDS:-30}"
ASK_TIMEOUT_SECONDS="${FREELLMPOOL_QUICKSTART_ASK_TIMEOUT:-25}"
PROMPT='Reply with one short sentence: freellmpool is ready.'

if [[ "$INSTALL_TARGET" == "." ]]; then
    INSTALL_TARGET="$ROOT"
fi

if [[ -z "$WORKDIR" ]]; then
    WORKDIR="$(mktemp -d)"
    if [[ "$KEEP_WORKDIR" != "1" ]]; then
        trap 'rm -rf "$WORKDIR"' EXIT
    fi
else
    mkdir -p "$WORKDIR"
fi

cd "$WORKDIR"
SECONDS=0

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "$INSTALL_TARGET"

mkdir -p home
ASK_ENV=(
    env -i
    "PATH=$WORKDIR/.venv/bin:/usr/bin:/bin"
    "HOME=$WORKDIR/home"
    "TERM=${TERM:-dumb}"
    "FREELLMPOOL_CONFIG_FILE=$WORKDIR/config.toml"
    "FREELLMPOOL_CONFIG=$WORKDIR/providers.toml"
    "FREELLMPOOL_QUOTA_PATH=$WORKDIR/quota.json"
    "FREELLMPOOL_CACHE_PATH=$WORKDIR/cache.db"
    "FREELLMPOOL_EXTERNAL_CATALOG_PATH=$WORKDIR/external.json"
)

if command -v timeout >/dev/null 2>&1; then
    "${ASK_ENV[@]}" timeout "$ASK_TIMEOUT_SECONDS" freellmpool ask --max-tokens 32 "$PROMPT" | tee reply.txt
else
    "${ASK_ENV[@]}" freellmpool ask --max-tokens 32 "$PROMPT" | tee reply.txt
fi

if [[ ! -s reply.txt ]]; then
    echo "quickstart-test: freellmpool produced no reply" >&2
    exit 1
fi

elapsed="$SECONDS"
echo "quickstart-test: first reply in ${elapsed}s"
if (( elapsed > MAX_SECONDS )); then
    echo "quickstart-test: expected <= ${MAX_SECONDS}s" >&2
    exit 1
fi
