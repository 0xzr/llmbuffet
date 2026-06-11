#!/usr/bin/env bash
# Scripted terminal demo for the README (recorded with termtosvg).
set -e
PS1_FAKE="\033[36m$\033[0m "
say() { printf "%b%s\n" "$PS1_FAKE" "$1"; sleep 0.7; }

say "pip install freellmpool"
sleep 0.4

say "freellmpool ask \"Explain the CAP theorem in one sentence.\""
freellmpool ask --max-tokens 70 "Explain the CAP theorem in one sentence." 2>/dev/null || true
sleep 1.2

say "freellmpool providers   # works with zero API keys"
freellmpool providers 2>/dev/null | head -7
sleep 1.5

say "freellmpool proxy   # drop-in OpenAI endpoint for any tool"
summary="$(freellmpool providers 2>/dev/null | head -1 | sed 's/^freellmpool catalog: //')"
printf "freellmpool proxy on http://127.0.0.1:8080/v1  (%s)\n" "${summary:-provider pool ready}"
sleep 2.0
