# Qorvo product data: what is reachable (checked 2026-10-19)

Question: can Cross List get public data for Qorvo PMICs, PAC motor controllers, SiC FETs and RF switches,
to show them next to Skyworks parts in block diagrams?

**Short answer:** yes for PMICs, bucks, PAC motor controllers and RF switches, through Qorvo's own store
(store.qorvo.com, run by RFMW). qorvo.com itself is behind a bot checkpoint. SiC FETs are no longer Qorvo
parts: onsemi bought the UnitedSiC business in January 2025.

Result: `qorvo_parts.yaml` lists 82 parts, each with its source URL.

| Function | Parts | Notes |
|---|---|---|
| pmic | 19 | ACT88xxx / ACT8xxx. 6 Standard, 1 No-new-designs, 12 Discontinued |
| power_loss_protection | 3 | ACT4910, ACT4921, ACT85610 (eFuse + storage-cap PMIC) |
| wide_vin_buck | 7 | ACT41000, ACT4751/4752, ACT4529/4530/4533, ACT43850 (45-150 V) |
| buck_boost | 2 | ACT5101, ACT5102 |
| cc_regulator | 1 | ACT43950 (180-400 V) |
| motor_controller | 29 | PAC52xx / PAC55xx: MCU + 3-phase gate drivers + supply regulator. Supply up to 160 V (PAC5232/PAC5532) and 600 V (PAC525x/PAC5556) |
| rf_pa_bias | 1 | ACT43750 (GaN/GaAs drain switch / gate bias) |
| rf_switch | 20 | QPC SPST through SP6T, DPDT/DP4T, 50 and 75 ohm |
| sic_fet | 0 | Now onsemi (see below) |
| gate_driver (standalone) | 0 | None in the catalogue; gate drivers are built into the PAC parts |
| ldo (standalone) | 0 | None in the catalogue; LDOs appear only inside PMICs |

## Access log

All requests used `curl -sS -A "Mozilla/5.0"` with no other headers. Nothing was bypassed.

| Site | HTTP | What came back |
|---|---|---|
| www.qorvo.com/products/power-solutions | 429 | "Vercel Security Checkpoint" JS challenge page (34 KB, no product data) |
| www.qorvo.com/products/p/ACT88760, /p/PAC5532, /p/UJ4C075018K4S, /p/QPC6324 | 429 | Same checkpoint |
| www.qorvo.com/products/power-solutions/power-management, /api/products/parametric, /sitemap.xml, /robots.txt | 429 | Same checkpoint (even robots.txt) |
| cn.qorvo.com/products/p/ACT88760 | 429 | Same checkpoint |
| **store.qorvo.com/products/detail/...** | **200** | Server-rendered HTML with a parametric "Specifications" table, description, lifecycle status, and Key Features for PAC parts |
| store.qorvo.com/sitemap.xml | 200 | 6,744 URLs, last updated 2024-11-09. Used to find the part pages. `/search/` is disallowed by robots.txt and was not used |
| store.qorvo.com category pages (e.g. /products/control-products/modular-power-pmic) | 200 | Paginated parametric listings (25 per page). Example: 36 PMICs in total |
| store.qorvo.com/products/power-solutions/sic-fet | 302 | Redirects to /search (the category is gone) |
| store.qorvo.com UnitedSiC part pages (UJ4C/UJ4SC/UF3C/UF3SC/UF4/UG4) | 404 | 67 pages. Removed after the onsemi sale |
| store.qorvo.com at ~1 req/s | 403 (intermittent) | Azure Application Gateway rate limit. One retry at 1 req/3 s cleared 21 of 28. The other 7 (QPC1022 and six SiC) were left alone |
| rfmw.com/products/detail/... | 200 | Same data as the store (checked ACT88760-101, PAC5532AQX, QPC6044) |
| mouser.com (product pages and the ACT88760 datasheet PDF) | 200 with "Access Denied" | Akamai block page |
| digikey.com | 403 | Cloudflare "Just a moment" challenge |
| everythingrf.com | 403 | Cloudflare challenge |
| onsemi.com (UJ4C075018K4S) | 403 | "Access Denied" |
| WebSearch | ok | Useful for discovery. Its summaries were **not** used as data |

## Caveats

- **This is distributor data, not datasheet data.** It gives counts and ratings (number of bucks and LDOs,
  Vin range, gate-driver voltage and current, MCU, IL and isolation). It does not give per-rail currents for
  PMICs or full switch power handling. Some pages have only a description (`key_specs: {}`).
- **The sitemap is from November 2024.** Newer Qorvo parts will be missing.
- **Many legacy ACT8xxx PMICs are Discontinued.** The status is recorded for each part, so the app can filter.
- **No automotive (-Q1 / AEC-Q100) ACT88xxx PMIC** turned up in the store catalogue. The brief mentioned an
  "automotive ACT88xxx" line, but it is either not listed there or newer than the sitemap.
- **One page contradicts itself.** QPC8014Q: the description says SP6T, the spec table says SP4T.
- **SiC FETs are now onsemi parts.** Qorvo's SiC JFET business (United Silicon Carbide: UJ3/UJ4/UF3/UF4/UG4)
  went to onsemi, and the sale closed in January 2025
  (https://investor.onsemi.com/news-releases/news-release-details/onsemi-completes-acquisition-qorvos-silicon-carbide-jfet).
  If they are shown, they should be labelled onsemi (EliteSiC), not Qorvo. onsemi.com blocks curl.

## Realistic options

1. **Use the store.qorvo.com pages (works today, no keys).** Discover parts via the sitemap or the category
   pages, read the spec tables, and fetch slowly (1 request per 3 s or slower). Good enough to place Qorvo
   PMIC, buck, PAC and RF-switch blocks, each with an MPN, a one-line summary, the headline specs and the
   lifecycle status. The import is a one-off; a refresh means re-running it.
2. **The user supplies a selector export or datasheets.** For datasheet-grade specs and the newest or
   automotive parts, the user saves the parametric tables from qorvo.com in a normal browser (whether the selector
   has a CSV export could not be checked, because the site is blocked here) or downloads the datasheet PDFs. Cross List then imports those files.
3. **Distributor APIs with keys (DigiKey Product Information API v4, Mouser Search API).** These are the
   most complete and are kept up to date, including the onsemi SiC parts. They need the user to register for
   keys, and none were used here.
4. **For SiC FETs**, use onsemi data through option 2 or 3, not Qorvo.
