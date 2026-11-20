#!/usr/bin/env python3
"""
NSH Stock Lookup - website harvest (runs in GitHub Actions, never in the browser).

What it does
  * For every item in stock.xml it looks the item up on www.nshnordic.com and
    records the product picture path (used for the thumbnail) and the name the
    website shows.
  * The curated item_names.csv is NEVER changed. It stays the primary name source.
    Website names are stored separately in item_web.csv and are only shown on the
    page when item_names.csv has no name for that item (gap filling).
  * Where the website name differs from the curated Danish name, the item is
    listed in name_report.csv so somebody can review it.

Files written
  item_web.csv     NSH Varenr.;Image;Web DK;Web SE;Web FI;Web UK;Checked
  name_report.csv  NSH Varenr.;Issue;Curated DK;Web DK

Settings (can be changed in the workflow file or with the "Run workflow" form)
  MAX_ITEMS     how many items to check in one run          (default 600)
  REFRESH_DAYS  re-check an item after this many days        (default 14)
"""
import csv, html, os, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

SITE = "https://www.nshnordic.com"
LANGS = [("da", "danish"), ("sv", "swedish"), ("fi", "finnish"), ("en", "english")]
MAX_ITEMS = int(os.environ.get("MAX_ITEMS") or 600)
REFRESH_DAYS = int(os.environ.get("REFRESH_DAYS") or 14)
WORKERS = 4
TODAY = date.today().isoformat()
UA = "NSH-Stock-Lookup-harvest/1.0 (+https://nshnordic.github.io/nsh-stock/)"

WEB_HDR = ["NSH Varenr.", "Image", "Web DK", "Web SE", "Web FI", "Web UK", "Checked"]
REP_HDR = ["NSH Varenr.", "Issue", "Curated DK", "Web DK"]


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f, delimiter=";"))
    return rows[1:]


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        w.writerow(header)
        w.writerows(rows)


def stock_items():
    items, seen = [], set()
    for line in ET.parse("stock.xml").getroot().iter("Lines"):
        it = (line.findtext("ProductBarcode") or "").strip()
        if it and it.upper() not in seen:
            seen.add(it.upper())
            items.append(it)
    return items


def curated_names():
    out = {}
    for r in read_csv("item_names.csv"):
        if len(r) >= 7 and r[1].strip():
            out[r[1].strip().upper()] = {"da": r[3].strip(), "sv": r[4].strip(),
                                         "fi": r[5].strip(), "en": r[6].strip()}
    return out


def clean(s):
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


SKU_RE = re.compile(r'class="[^"]*item_swift_productnumber[^"]*"[^>]*>(.*?)</', re.S)
HEAD_RE = re.compile(r'class="[^"]*item_swift_productheader[^"]*"[^>]*>(.*?)</h\d', re.S)
IMG_RE = re.compile(r'<img[^>]+src="([^"]*GetImage\.ashx[^"]*)"', re.S)


def lookup(item, langword):
    """Return (name, image_path) for the card whose product number equals item.
    (None, None) = not on the website. Raises on network errors."""
    url = f"{SITE}/{langword}/product-search-result-page?q={urllib.parse.quote(item)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        page = r.read().decode("utf-8", "replace")
    for card in page.split("<article")[1:]:
        m = SKU_RE.search(card)
        if not m or clean(m.group(1)).upper() != item.upper():
            continue
        h = HEAD_RE.search(card)
        im = IMG_RE.search(card)
        img = ""
        if im:
            q = urllib.parse.urlparse(html.unescape(im.group(1))).query
            img = (urllib.parse.parse_qs(q).get("image") or [""])[0]
        return (clean(h.group(1)) if h else ""), img
    return None, None


def fetch(item, langword):
    for attempt in range(3):
        try:
            return lookup(item, langword)
        except Exception as e:  # network hiccup - try again
            err = e
            time.sleep(3 * (attempt + 1))
    raise err


def main():
    items = stock_items()
    curated = curated_names()
    web = {}
    for r in read_csv("item_web.csv"):
        if len(r) >= 7 and r[0].strip():
            web[r[0].strip().upper()] = r[:7]

    def age(it):
        row = web.get(it.upper())
        if not row or not row[6]:
            return 10 ** 6  # never checked -> first
        try:
            return (date.today() - datetime.strptime(row[6], "%Y-%m-%d").date()).days
        except ValueError:
            return 10 ** 6

    due = [it for it in items if age(it) >= REFRESH_DAYS]
    due.sort(key=age, reverse=True)
    todo = due[:MAX_ITEMS]
    print(f"Stock items: {len(items)} | known on web file: {len(web)} | due: {len(due)} | checking now: {len(todo)}")

    def work(it):
        cur = curated.get(it.upper(), {})
        old = web.get(it.upper(), [it, "", "", "", "", "", ""])
        try:
            da_name, img = fetch(it, "danish")
        except Exception as e:
            print(f"  ! {it}: {e} (kept previous data)")
            return it, old, False
        if da_name is None:
            return it, [it, "", "", "", "", "", TODAY], True
        row = [it, img or "", da_name, old[3], old[4], old[5], TODAY]
        # Gap filling: fetch the other languages only where the curated file has no name
        for col, (code, word) in ((3, LANGS[1]), (4, LANGS[2]), (5, LANGS[3])):
            if not cur.get(code):
                try:
                    n, _ = fetch(it, word)
                    row[col] = n or ""
                except Exception:
                    pass
            else:
                row[col] = ""  # curated name exists - no need to keep a web copy
        return it, row, True

    found = missing = failed = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for it, row, ok in ex.map(work, todo):
            web[it.upper()] = row
            if not ok:
                failed += 1
            elif row[2] or row[1]:
                found += 1
            else:
                missing += 1

    # keep only items still in stock.xml, in item order
    stock_set = {i.upper() for i in items}
    rows = sorted((r for k, r in web.items() if k in stock_set), key=lambda r: r[0].upper())
    write_csv("item_web.csv", WEB_HDR, rows)

    # Review report: curated vs website (Danish), and items not on the website
    def norm(s):
        return re.sub(r"\s+", " ", s or "").strip().casefold()
    report = []
    for r in rows:
        if not r[6]:
            continue
        cur = curated.get(r[0].upper(), {})
        if not r[1] and not r[2]:
            report.append([r[0], "not found on website", cur.get("da", ""), ""])
        elif cur.get("da") and r[2] and norm(cur["da"]) != norm(r[2]):
            report.append([r[0], "name differs", cur["da"], r[2]])
        elif not cur.get("da") and r[2]:
            report.append([r[0], "no curated name - website name used", "", r[2]])
    write_csv("name_report.csv", REP_HDR, report)

    with_img = sum(1 for r in rows if r[1])
    print(f"Checked {len(todo)}: found {found}, not on website {missing}, failed {failed}")
    print(f"item_web.csv: {len(rows)} items, {with_img} with picture")
    print(f"name_report.csv: {len(report)} lines")
    if todo and failed == len(todo):
        sys.exit("Every lookup failed - is www.nshnordic.com reachable?")


if __name__ == "__main__":
    main()
