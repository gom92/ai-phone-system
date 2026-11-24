#!/bin/bash
# run-pjsua.sh - launch a pjsua test endpoint detached from any shell.
# Usage: run-pjsua.sh <config-name>   (config file data/pjsua-<name>.cfg)
# e.g. run-pjsua.sh a | run-pjsua.sh b | run-pjsua.sh a-ai
# pjsua quits when its stdin hits EOF, so stdin is fed from a long sleep
# through a pipe (kept open 1800s). stdout/stderr go to logs/pjsua-<name>.log.
# RTP uses UDP via the LD_PRELOAD shim (lib/udp_connect_shim.so).
set -u
BASE=/home/hatch/workspace/ai-phone-system
ID="${1:-}"
[ -n "$ID" ] && [ -f "$BASE/data/pjsua-$ID.cfg" ] || { echo "usage: $0 <config-name> (data/pjsua-<name>.cfg must exist)"; exit 2; }
cd "$BASE"
setsid nohup env LD_PRELOAD="$BASE/lib/libudp_connect_shim.so" \
  "$BASE/src/pjproject/pjsip-apps/bin/pjsua-x86_64-unknown-linux-gnu" \
  --config-file "$BASE/data/pjsua-$ID.cfg" \
  < <(sleep 1800) > "$BASE/logs/pjsua-$ID.log" 2>&1 &
echo "pjsua-$ID launched pid $!"
