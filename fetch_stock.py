#!/usr/bin/env python3
"""
Downloads the newest NSH inventory file from the NSH FTPS server and saves it
as stock.xml (which the web page reads).

The username and password are NOT stored here. They are read at runtime from
environment variables, which GitHub fills in from your encrypted repository
Secrets:  NSH_FTP_USER  and  NSH_FTP_PASS.

No extra installation is needed - this uses only Python's standard library.
"""

import os
import ssl
from ftplib import FTP_TLS

# ---- Connection details from NSH (safe to keep in the file) ----------------
HOST = "ftps.nshdk.dk"
PORT = 21
# The directory NSH gave was "//Jukka/stockfile". The exact form the server
# expects can vary, so we try a few sensible options and use the first that works.
DIR_CANDIDATES = ["/Jukka/stockfile", "Jukka/stockfile", "stockfile", "/"]
FILE_PREFIX = "INVENTORY_NSH_FULL_"   # matched case-insensitively
# ----------------------------------------------------------------------------

USER = os.environ["NSH_FTP_USER"]
PASS = os.environ["NSH_FTP_PASS"]


class ReusedFTP_TLS(FTP_TLS):
    """Reuse the login TLS session on the data connection.
    Many strict FTPS servers require this, otherwise downloads hang or fail."""
    def ntransfercmd(self, cmd, rest=None):
        conn, size = super().ntransfercmd(cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn, server_hostname=self.host, session=self.sock.session
            )
        return conn, size


def main():
    # NSH's certificate may not validate cleanly. The connection is still
    # encrypted. Once everything works you can tighten this by deleting the
    # two "ctx." lines below (which turns full certificate checking back on).
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    ftps = ReusedFTP_TLS(context=ctx)
    print(f"Connecting to {HOST}:{PORT} ...")
    ftps.connect(HOST, PORT, timeout=60)
    ftps.login(USER, PASS)
    ftps.prot_p()  # encrypt the data connection too
    print("Logged in.")

    listing = None
    for d in DIR_CANDIDATES:
        try:
            ftps.cwd(d)
            listing = ftps.nlst()
            print(f"Opened directory: {d}")
            break
        except Exception as e:
            print(f"  (could not open '{d}': {e})")
    if listing is None:
        raise SystemExit("ERROR: could not open the stock directory on the server.")

    files = [
        n for n in listing
        if os.path.basename(n).upper().startswith(FILE_PREFIX)
        and n.upper().endswith(".XML")
    ]
    if not files:
        raise SystemExit(f"ERROR: no {FILE_PREFIX}*.XML file found. Saw: {listing}")

    # Filenames end in a timestamp, so the last one alphabetically is the newest.
    newest = sorted(files, key=lambda n: os.path.basename(n))[-1]
    print(f"Newest file on server: {newest}")

    with open("stock.xml", "wb") as f:
        ftps.retrbinary("RETR " + newest, f.write)
    ftps.quit()

    size = os.path.getsize("stock.xml")
    print(f"Saved stock.xml ({size:,} bytes).")


if __name__ == "__main__":
    main()
