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
from ftplib import FTP, FTP_TLS

# ---- Connection details from NSH (safe to keep in the file) ----------------
HOST = "ftps.nshdk.dk"
PORT = 21
# After login, NSH drops you straight into your own area, so the folder is
# simply "stockfile". A few fall-backs are listed just in case.
DIR_CANDIDATES = ["stockfile", "/stockfile", "./stockfile",
                  "/Jukka/stockfile", "Jukka/stockfile", "."]
FILE_PREFIX = "INVENTORY_NSH_FULL_"   # matched case-insensitively
# ----------------------------------------------------------------------------

USER = os.environ["NSH_FTP_USER"]
PASS = os.environ["NSH_FTP_PASS"]


class ReusedFTP_TLS(FTP_TLS):
    """Reuse the login TLS session on the data connection, wrapping it exactly
    once. NSH's server requires this, otherwise listings and downloads fail
    with 'TLS session not resumed'."""
    def ntransfercmd(self, cmd, rest=None):
        # Call the PLAIN FTP version to get an un-encrypted data socket,
        # then wrap it a single time while reusing the control session.
        conn, size = FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn,
                server_hostname=self.host,
                session=self.sock.session,
            )
        return conn, size


def main():
    ctx = ssl.create_default_context()
    # NSH's certificate may not validate cleanly. The connection is still
    # encrypted. (You can tighten this later by removing the next two lines.)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    # Pin TLS 1.2: NSH's server needs the data connection to reuse the login
    # session, which is reliable on 1.2. This is the key fix for the
    # "TLS session of data connection not resumed" error.
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2

    ftps = ReusedFTP_TLS(context=ctx)
    print(f"Connecting to {HOST}:{PORT} ...")
    ftps.connect(HOST, PORT, timeout=60)
    ftps.login(USER, PASS)
    ftps.prot_p()  # encrypt the data connection too
    print("Logged in.")

    # Find the folder: the first one we can open wins.
    opened = None
    for d in DIR_CANDIDATES:
        try:
            ftps.cwd(d)
            opened = d
            print(f"Opened directory: {d}")
            break
        except Exception as e:
            print(f"  (could not open '{d}': {e})")
    if opened is None:
        raise SystemExit("ERROR: could not open the stock directory on the server.")

    # List the files in that folder.
    listing = ftps.nlst()

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
