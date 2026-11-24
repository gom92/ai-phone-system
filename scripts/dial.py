#!/usr/bin/env python3
"""dial.py - guarded dial wrapper. NOTHING is dialled without confirmation,
and PSTN numbers are ALWAYS refused: this PBX has no trunk (budget $0).

Usage:
  dial.py --to 1001 [--confirm]   # local extension: originate a test call
  dial.py --to +8613800000000     # refused: no PSTN trunk, cost unknown

Local extensions (1000 echo, 1001 AI, 1002 softphone) are the only dialable
destinations. Anything else prints the refusal + the $0-budget note and exits 1.
--confirm is required even for local extensions.
"""
import argparse
import subprocess
import sys

LOCAL = {"1000": "Echo test", "1001": "AI assistant", "1002": "Test softphone"}

def main():
    ap = argparse.ArgumentParser(description="Guarded dial wrapper (local extensions only)")
    ap.add_argument("--to", required=True, help="destination (local extension 1000/1001/1002)")
    ap.add_argument("--confirm", action="store_true", help="confirm this dial")
    ap.add_argument("--from-ext", default="1002", help="originating local extension")
    args = ap.parse_args()

    if args.to not in LOCAL:
        print(f"REFUSED: {args.to} is not a local extension.")
        print("This PBX has no PSTN trunk. No provider is configured, so the")
        print("cost of calling a real phone number is UNKNOWN and the call is")
        print("blocked. Budget is strictly $0: no number purchase, no top-up,")
        print("no paid plan. See README 'What is still missing'.")
        return 1
    if not args.confirm:
        print(f"Target: {args.to} ({LOCAL[args.to]}), from {args.from_ext}.")
        print("This will originate a local SIP test call. Re-run with --confirm.")
        return 2
    cmd = ["asterisk", "-rx",
           f"channel originate PJSIP/{args.from_ext} extension {args.to}@internal"]
    print(f"Originating: {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    print(r.stdout)
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    return r.returncode

if __name__ == "__main__":
    sys.exit(main())
