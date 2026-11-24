#!/usr/bin/env python3
"""contacts.py - tiny local contact store (JSON). Local extensions and names
only; this is NOT a phone book of real numbers. No real phone numbers may be
stored here - the dial wrapper refuses them anyway.

Usage:
  contacts.py add <extension> <name>     # e.g. contacts.py add 1002 "Test softphone"
  contacts.py list
  contacts.py del <extension>
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(BASE, "data", "contacts.json")

def load():
    if os.path.exists(PATH):
        with open(PATH) as f:
            return json.load(f)
    return {}

def save(d):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    d = load()
    if cmd == "add" and len(sys.argv) == 4:
        ext, name = sys.argv[2], sys.argv[3]
        if not ext.isdigit() or len(ext) > 4:
            print("refused: only local extensions (up to 4 digits) may be stored")
            return 1
        d[ext] = name
        save(d)
        print(f"added {ext} = {name}")
    elif cmd == "list":
        if not d:
            print("(no contacts)")
        for ext in sorted(d):
            print(f"{ext}\t{d[ext]}")
    elif cmd == "del" and len(sys.argv) == 3:
        d.pop(sys.argv[2], None)
        save(d)
        print(f"deleted {sys.argv[2]}")
    else:
        print(__doc__)
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())
