#!/usr/bin/env python3
"""cdr_stats.py - import Asterisk CDR CSV into SQLite and print call stats.

Reads /var/log/asterisk/cdr-csv/Master.csv (written by cdr_csv) and upserts
into data/calls.db (table calls). Prints totals: calls, answered, total and
average billsec, per-destination breakdown. No phone numbers are involved:
destinations are local extensions only.
"""
import csv
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CDR_CSV = "/var/log/asterisk/cdr-csv/Master.csv"
DB = os.path.join(BASE, "data", "calls.db")

# Master.csv columns (cdr_csv default order):
# accountcode,src,dst,dcontext,clid,channel,dstchannel,lastapp,lastdata,
# start,answer,end,duration,billsec,disposition,amaflags,uniqueid,userfield
COLS = ["accountcode", "src", "dst", "dcontext", "clid", "channel",
        "dstchannel", "lastapp", "lastdata", "start", "answer", "end",
        "duration", "billsec", "disposition", "amaflags", "uniqueid", "userfield"]

def main():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS calls (
        uniqueid TEXT PRIMARY KEY, calldate TEXT, src TEXT, dst TEXT,
        duration INTEGER, billsec INTEGER, disposition TEXT, channel TEXT)""")
    n_new = 0
    if os.path.exists(CDR_CSV):
        with open(CDR_CSV, newline="") as f:
            for row in csv.reader(f):
                if len(row) < len(COLS):
                    row += [""] * (len(COLS) - len(row))
                d = dict(zip(COLS, row))
                try:
                    dur = int(d["duration"] or 0)
                    bill = int(d["billsec"] or 0)
                except ValueError:
                    continue
                cur = con.execute(
                    "INSERT OR IGNORE INTO calls VALUES (?,?,?,?,?,?,?,?)",
                    (d["uniqueid"], d["start"], d["src"], d["dst"], dur, bill,
                     d["disposition"], d["channel"]))
                n_new += cur.rowcount
    con.commit()
    cur = con.execute("SELECT COUNT(*), COALESCE(SUM(billsec),0), "
                      "COALESCE(SUM(duration),0) FROM calls")
    total, billsec, duration = cur.fetchone()
    answered = con.execute("SELECT COUNT(*) FROM calls WHERE disposition='ANSWERED'").fetchone()[0]
    print(f"imported {n_new} new record(s) from {CDR_CSV}")
    print(f"calls total: {total}  answered: {answered}")
    print(f"total duration: {duration}s  total billsec: {billsec}s")
    for dst, c, b in con.execute(
            "SELECT dst, COUNT(*) AS c, COALESCE(SUM(billsec),0) AS b FROM calls "
            "GROUP BY dst ORDER BY c DESC"):
        print(f"  dst {dst}: {c} call(s), {b}s billed")
    con.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
