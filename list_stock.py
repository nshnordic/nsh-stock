#!/usr/bin/env python3
"""
Lists what is in the NSH stock folder on the FTPS server - and nothing else.

This is a READ-ONLY diagnostic tool. It logs in, opens the stock folder, and
prints every file it finds with its size and date. It does NOT download,
upload, change, or delete anything.

It reuses the exact same connection logic as fetch_stock.py, so if the real
job can reach the server, so can this - and if this cannot, that tells you the
problem is the connection itself, not the data.

The username and password are read from environment variables, which GitHub
fills in from your encrypted repository Secrets: NSH_FTP_USER and NSH_FTP_PASS.
Nothing sensitive is stored in this file.
"""

import os
import ssl
from ftplib import FTP, FTP_TLS

# ---- Connection details from NSH (safe to keep in the file) ----------------
HOST = "ftps.nshdk.dk"
PORT = 21
# After login NSH drops you into your own area, so "stockfile" is enough.
# A few fall-backs are listed just in case the layout differs.
DIR_CANDIDATES = ["stockfile", "/stockfile", "./stockfile",
                  "/Jukka/stockfile", "Jukka/stockfile", "."]
# ----------------------------------------------------------------------------

USER = os.environ["NSH_FTP_USER"]
PASS = os.environ["NSH_FTP_PASS"]


class ReusedFTP_TLS(FTP_TLS):
    """Reuse the login TLS session on the data connection, wrapping it exactly
    once. NSH's server requires this, otherwise listings fail with
    'TLS session not resumed'."""
    def ntransfercmd(self, cmd, rest=None):
        conn, size = FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn,
                server_hostname=self.host,
                session=self.sock.session,
            )
        return conn, size


def human(size):
    """Turn a byte count into something readable, e.g. 928.4 KB."""
    try:
        size = float(size)
    except (TypeError, ValueError):
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:,.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024


def main():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2

    ftps = ReusedFTP_TLS(context=ctx)
    print(f"Connecting to {HOST}:{PORT} ...")
    ftps.connect(HOST, PORT, timeout=60)
    ftps.login(USER, PASS)
    ftps.prot_p()
    print(f"Logged in as {USER}.\n")

    # Open the folder: first one that works wins.
    opened = None
    for d in DIR_CANDIDATES:
        try:
            ftps.cwd(d)
            opened = d
            break
        except Exception as e:
            print(f"  (could not open '{d}': {e})")
    if opened is None:
        raise SystemExit("ERROR: could not open the stock folder on the server.")

    print(f"Contents of folder: {opened}")
    print("-" * 60)

    # Preferred: MLSD gives name, size and modify-time in a tidy machine format.
    rows = []
    try:
        for name, facts in ftps.mlsd():
            if name in (".", ".."):
                continue
            rows.append((
                facts.get("type", ""),
                name,
                human(facts.get("size")),
                facts.get("modify", ""),   # e.g. 20260723100015
            ))
    except Exception as e:
        print(f"(server does not support the tidy MLSD listing: {e})")
        print("Falling back to a raw directory listing:\n")
        ftps.retrlines("LIST")            # server prints its own raw lines
        ftps.quit()
        return

    if not rows:
        print("(the folder is empty)")
    else:
        for kind, name, size, modify in sorted(rows, key=lambda r: r[1]):
            # Prettify the timestamp 20260723100015 -> 2026-07-23 10:00:15
            when = modify
            if len(modify) >= 14 and modify.isdigit():
                when = (f"{modify[0:4]}-{modify[4:6]}-{modify[6:8]} "
                        f"{modify[8:10]}:{modify[10:12]}:{modify[12:14]}")
            label = "DIR " if kind == "dir" else "file"
            print(f"  {label}  {when:>19}  {size:>10}  {name}")

    print("-" * 60)
    print(f"{len(rows)} item(s) listed. Nothing was downloaded or changed.")
    ftps.quit()


if __name__ == "__main__":
    main()
