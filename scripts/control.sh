#!/bin/bash
# control.sh - human takeover / hangup / list for the AI phone system.
# All control is local (asterisk CLI socket). No remote access.
# Usage:
#   control.sh list                        # show active channels
#   control.sh hangup <channel>            # hang up one channel, e.g. PJSIP/1002-00000001
#   control.sh hangup-all                  # hang up every active channel
#   control.sh takeover <channel>          # redirect a channel to the human softphone (1002)
#   control.sh takeover-ai <channel>       # redirect a channel back to the AI (1001)
#   control.sh spy <channel>               # listen to a channel (ChanSpy, whispers off)
#   control.sh status                      # PBX + endpoint status
set -euo pipefail

case "${1:-}" in
  list)
    asterisk -rx "core show channels"
    ;;
  hangup)
    [ -n "${2:-}" ] || { echo "usage: $0 hangup <channel>"; exit 2; }
    asterisk -rx "channel request hangup $2"
    ;;
  hangup-all)
    asterisk -rx "core show channels concise" | awk -F'!' '{print $1}' | while read -r ch; do
      [ -n "$ch" ] && asterisk -rx "channel request hangup $ch" || true
    done
    echo "hangup-all done"
    ;;
  takeover)
    [ -n "${2:-}" ] || { echo "usage: $0 takeover <channel>"; exit 2; }
    echo "Redirecting $2 to human softphone (1002)..."
    asterisk -rx "channel redirect $2 internal,1002,1"
    ;;
  takeover-ai)
    [ -n "${2:-}" ] || { echo "usage: $0 takeover-ai <channel>"; exit 2; }
    echo "Redirecting $2 back to the AI assistant (1001)..."
    asterisk -rx "channel redirect $2 internal,1001,1"
    ;;
  spy)
    [ -n "${2:-}" ] || { echo "usage: $0 spy <channel>"; exit 2; }
    echo "Spying on $2 from the human softphone: answer the call on 1002 when it rings."
    asterisk -rx "channel originate PJSIP/1002 application ChanSpy $2,q"
    ;;
  status)
    asterisk -rx "core show version"
    asterisk -rx "pjsip show endpoints"
    asterisk -rx "core show channels"
    ;;
  *)
    echo "usage: $0 {list|hangup <channel>|hangup-all|takeover <channel>|takeover-ai <channel>|spy <channel>|status}"
    exit 2
    ;;
esac
