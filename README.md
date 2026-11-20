# nsh-stock
Display of NSH NORDIC stock quantity for any item — https://nshnordic.github.io/nsh-stock/

## Files
| File | What it is | Who changes it |
|---|---|---|
| `index.html`, `light.html`, `dark.html` | The page (light / light / dark theme). `?lang=en/da/fi/sv` picks the language. | You |
| `stock.xml` | Stock feed from NSH's FTPS server | Robot, every 4 hours (`update-stock.yml`) |
| `item_names.csv` | **Curated item names** (DK/SE/FI/UK) — the primary name source | You (from the Perfion export) |
| `item_web.csv` | Picture path + website names for items missing from `item_names.csv` | Robot, daily (`harvest-web.yml`) |
| `name_report.csv` | Items whose website name differs from `item_names.csv`, or that aren't on the website | Robot, daily |

## How names and pictures are chosen
1. Name: `item_names.csv` in the chosen language → website name in that language → English → Danish.
2. Picture: loaded directly from nshnordic.com (`GetImage.ashx`, 100 px, grey E0E0E0 background), using the path saved in `item_web.csv`. Items without a picture simply show none.

The harvest job never edits `item_names.csv`. Use `name_report.csv` to decide what to fix there.
