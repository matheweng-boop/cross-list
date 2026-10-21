# Semiconductor cost and the price-vs-volume curve (topic: semiconductor_cost)

Purpose: give the BizDev price model (`app/services/price_model.py`, `data/business/price_model.yaml`) complexity
classes (commodity / standard / complex) with the cost drivers behind them. Retrieved 21 Oct 2026. All summaries are
ours. Numbers marked "snippet" come from web-search snippets that were not read in full (conf low).

## References (the six)

| id | Reference | Type | Why |
|----|-----------|------|-----|
| r1 | Feng & Ma, *Chiplet Actuary: A Quantitative Cost Model and Multi-Chiplet Architecture Exploration*, DAC 2022, arXiv:2203.12268v4 | paper | Negative-binomial yield, D0 per node, RE/NRE split, packaging yield, wasted known-good dies |
| r2 | Gielen, Dehaene, Christie, Draxelmayr, Janssens, Maex, Vucurevich, *Analog and digital circuit design in 65 nm CMOS: end of the road?*, DATE 2005, arXiv:0710.4709 | paper | Why analog area and power do not scale (noise, mismatch, supply) |
| r3 | Rivoir (Agilent), *Parallel Test Reduces Cost of Test More Effectively Than Just a Cheap Tester*, IEMT 2004, Advantest reprint | white paper | Full test-cost model with numbers (cents per second, multi-site) |
| r4 | Infineon, *Annual Report 2025* | annual report | Audited gross margin, R&D and SG&A shares, outsourcing policy, distributor price adjustments |
| r5 | TI SLVAFW6A, *Novel Plating Technology for Wettable-Flank QFN and SON Packages* (2024) | app note | Automotive QFN/SON requirements |
| r6 | Baas, UC Davis EEC 116 handout *Cost* (2019) | course | Die-cost equations, 300 mm wafer costs by node, NRE scale |

Also read (not counted in the six): MIT OCW 2.830J lecture 10 on yield models (Poisson, Murphy, Seeds, negative
binomial; CC BY-NC-SA); Skyworks FY25 Q3 prepared remarks (already downloaded by an earlier run, `dl/ad/swks_fy25q3.pdf`).

No standard among the six: the AEC documents (AEC-Q001 part average testing, AEC-Q004 zero defects) were the intended
standard, but www.aecouncil.com could not be reached (DNS failure on http, TLS handshake failure on https).

## Block diagram: cost build-up of a packaged IC

```
[Wafer fab: wafer, masks] -> [Wafer sort: probe, KGD map] -> [Assembly: grind/dice, die attach, wire bond, mold/plate/singulate]
      -> [Final test: tester type, multi-temp/PAT, burn-in] -> [Supplier: COGS + gross margin] -> [Distributor | direct contract]
                         [NRE: design, IP, masks, qualification] ---------amortised over lifetime volume---^
```

All blocks use `fn: external_block` with a label. A multi-die part (isolator, isolated gate driver, RF module) passes
several dies through die attach, so its yields multiply.

## How each cost layer behaves

**Silicon.** Die cost = wafer cost / (gross dies x yield); gross dies = pi(d/2)^2/A - pi d/sqrt(2A) (r6).
Yield (r1, r6, MIT): Poisson exp(-D0 A) assumes uncorrelated point defects; Murphy and Seeds average Poisson over a
distribution of D0; the negative binomial (1 + D0 A/alpha)^-alpha (gamma-distributed D0) is the common industry form,
with alpha about 3 (r6) to 10 (r1). D0: r1 uses 0.08 (14 nm), 0.09 (7 nm), 0.11 (5 nm), 0.2 (early 3 nm), 0.05 for RDL;
r6 quotes 0.5–1/cm2 as "typical", which we read as a conservative, older figure.

Our arithmetic with these models (USD per good die):

| Die | Wafer | D0 | Gross dies | Yield (NB, alpha 3) | Die cost |
|-----|-------|----|-----------:|------:|------:|
| 1 mm2 | 200 mm, USD 750 | 0.1 | 30,972 | 99.9 % | 0.024 |
| 5 mm2 | 200 mm, USD 800 | 0.1 | 6,084 | 99.5 % | 0.13 |
| 30 mm2 | 300 mm, USD 3,000 | 0.1 | 2,235 | 97.1 % | 1.38 |
| 30 mm2 | 300 mm, USD 3,000 | 0.5 | 2,235 | 86.4 % | 1.55 |
| 100 mm2 | 300 mm, USD 3,000 | 0.5 | 640 | 63 % | 7.44 |

Why yield falls faster than area grows: each die collects defects in proportion to its area, so the share of clean
dies falls roughly exponentially with D0 x A while the number of dies falls only linearly; cost per good die therefore
rises faster than area once D0 x A nears 1 (r6 even writes die cost ~ f(area^4) for the high-D0 1994 examples). For our
small analog/RF dies D0 x A is about 0.001–0.005, so die cost is linear in area and parametric yield/test matter more.

Wafer cost by process (only r6 read): 300 mm 130 nm USD 2,000, 22 nm USD 4,500, 14 nm USD 7,000 (2019). Not found in a
readable source: 200 mm BCD, RF-SOI, SiGe, 150 mm GaAs. Snippets (2007 trade press): 200 mm 0.13 um foundry about
USD 1,000; 150 mm GaAs up to USD 2,500 (claimed by a CMOS-PA start-up), IDM in-house about USD 800.

**Analog/RF scaling (r2).** Key analog transistor area is set by kT/C noise and mismatch, which bound dynamic range or
accuracy; speed x accuracy^2 / power is a technology constant, and with mismatch only slightly better per node and a
lower supply (smaller signal swing, no cascodes), power at fixed speed and accuracy stays flat or rises. Pelgrom's law
(offset sigma ~ A_VT/sqrt(WL), so area ~ 1/sigma^2 for a given accuracy) is the textbook form; we did not read Pelgrom's
paper itself. Passives (inductors, capacitors) do not shrink either (general knowledge, not from a reference). r2 says
analog takes "only a small fraction of the total area" of SoCs but dominates design time, test cost and reruns; no
numeric analog-area share was found. Result: mixed-signal and RF parts stay on mature nodes, where wafers and masks
are cheap.

**NRE.** r6: fixed cost per design = design effort, masks, CAD, company overhead; ITRS 2009 put a modern ASIC around
USD 50 M and 18–24 months. r1: NRE has an area-dependent part (module design, verification) and a fixed part (IP
licences, full mask set); at low quantity NRE dominates, at large quantity it is negligible. Mask sets (snippets only):
180 nm USD 100–300k, 130 nm about USD 750k (early 2000s), 65 nm USD 0.5–1 M, 28 nm USD 1–3 M, 7 nm above USD 10 M.
Worked example (ours): USD 10 M NRE over 5 M lifetime units = USD 2 per unit; over 500k units = USD 20 per unit. This
is what bends the price curve down with volume for complex parts sold directly.

**Packaging.** r5 (TI) for automotive QFN/SON: plain sawn QFN leaves bare copper flanks that oxidise and do not wet, so
automotive needs wettable flanks (step-cut, dimple lead frame, or TI's immersion-Sn flank plating); the target is a
solder fillet of about 100 um at Cpk 1.67 for AOI; board-level cycling -40/+125 C, 1000 cycles; lead frame 0.1–0.2 mm.
Not covered by a read source: copper wire, high-CTI mold for isolation creepage, MSL1 (these are price_model.yaml
judgements). Package cost per pin: no public number; one trade-press example says a fine-pitch BGA has about 40 % higher
material cost and 13x the assembly cost of a 7x7 mm QFN; QFN is cheaper than BGA/LGA below roughly 100 pins (patent
background, snippet); WLCSP is generally cheapest (snippets). Multi-die (r1): overall yield = wafer x die x packaging x
test; a packaging failure scraps every known-good die in the package; packaging was 30 % of cost in r1's AMD 16-core case.

**Test (r3).** Cost per device = (capital rate + operating rate) x time on cell / sites + probe card + packaging of
bad parts. Example: USD 1 M test cell (USD 400k ATE + USD 300k prober + channels), 65 % utilisation, 5-year
depreciation gives 0.98 cents/s; operating USD 35/h = 0.97 cents/s. Single site: 4.7 s on the cell (0.4 s stepping),
9 cents per device, 80 % yield. Seven sites save almost 50 %; each extra site added about 10 % sequential time in the
example; fully parallel test pushes the optimum to 12 sites; reduced pin-count test plus cheaper per-site resources
reached 1.6 cents at 25 sites. Per-site resource cost from USD 10k to 200k moves the optimum only from 8 to 4 sites.
RF ports cost USD 100–500k each (2007 SWTW slides, snippet), which is why RF parts run fewer sites. Automotive zero-defect
flows (multi-temperature test, PAT, burn-in) could not be read (AEC unreachable); the 1.5–3x multiple is our judgement.

**Commercial.** r4 Infineon FY2025: revenue EUR 14,662 M, gross margin 39.2 % (FY2024 41.8 %), R&D 15.2 % and SG&A
10.8 % of revenue; external foundries used for low-differentiation front-end steps, OSATs for standard packages;
distributors can claim price adjustments, ship-and-debit credit notes, limited returns and scrap allowances. Skyworks
FY25 Q3: gross margin 47.1 %; Broad Markets (incl. automotive) has margins above the corporate average; Woburn fab to
close and consolidate into Newbury Park to raise utilisation. Snippets: TI about 58 % (2024), ADI 61.5 % GAAP / 69.3 %
adjusted (FY2025), Arrow global components gross margin 11.7 % (2024).

Why distributor curves of expensive, complex parts are flatter (our reasoning, conf low): catalogue distributors carry a
fixed handling cost per order line (picking, cut tape, small-quantity service). On a USD 0.30 switch that fixed cost is
a large share at 1–100 pieces and vanishes at reel quantity, giving a steep curve; on a USD 10 tuner it is a small
share, so the curve is flat. Complex parts also have few second sources, design-in lock-in and long automotive supply
agreements, so the supplier gives less volume discount; ship-and-debit means large customers' real price is negotiated
off-curve. Not found: HD Radio royalty per chip; learning-curve slope for analog/RF prices.

## Design rules (summary; full list in the YAML)

1. Die cost = wafer cost / (gross dies x yield); use the negative binomial with alpha 3–10.
2. Ignore random-defect yield below about 5 mm2; include it for complex dies of 20 mm2 and more.
3. Analog/RF area does not scale with node; keep mixed-signal on mature nodes.
4. Amortise NRE over lifetime volume; it is what makes price fall with volume.
5. Multi-die: multiply yields; count wasted known-good dies.
6. Test: about 2 cents/s single-site, roughly halved by 4–8 sites; count index time.
7. Automotive QFN needs wettable flanks.
8. Gross-margin floor about 40 % (Infineon 39 %, opex 26 % of revenue).

## Considerations and pitfalls for the price model

- The model's `defects_per_cm2` 0.1–0.15 matches r1's production values; r6's 0.5–1 would overstate cost only for big dies.
- The model's `test_usd_per_s` 0.02 equals r3's single-site rate; with multi-site the effective rate per device is
  about 0.003–0.01 USD/s, so 0.02 is conservative for commodity parts and closer to right for RF/precision parts.
- `margin.floor` 0.40 agrees with Infineon's 39–42 % gross margin; `typical` 0.45–0.65 spans Skyworks to TI/ADI.
- For the complex class (am_fm_tuner, rf_frontend modules) the cost floor needs an NRE/volume term and module yield
  stacking; die area alone underestimates them.
- r3 dates from 2004; tester prices have not fallen as fast as logic, but treat its cents as order of magnitude.

## Where Skyworks parts sit

- Commodity: rf_switch (SKY5A2108, SKY59608-711LF), digital_isolator (SI8600 / SI8610): small dies, package and test dominate.
- Standard: gate_driver (SI8230, SI82390), isolated_amplifier (SI8921): two dies, trim/hipot test, automotive screening.
- Complex: am_fm_tuner (Si47962), rf_frontend modules (SKY5A2205, SKY5A2206): large non-shrinking mixed-signal/RF die
  or multi-die laminate modules, high NRE, long RF test, few suppliers: flat price curves.

## Research trends

- Analog/power move to 300 mm (Infineon thin-wafer power, GaN on 300 mm) (r4).
- Multi-die/chiplets: cost hinges on packaging yield and KGD (r1).
- Analog stays on mature nodes; design productivity, not density, is the limit (r2).
- Wettable-flank leadless packages standard in automotive (r5).
- Parallel test beats cheaper testers (r3).
- NRE escalation at advanced nodes (snippets) keeps medium-volume parts on mature nodes.

## Open questions

See the YAML: automotive test multiple (AEC unreadable), current RF-SOI/BCD/GaAs wafer prices, package cost per pin,
HD Radio royalty, learning-curve slope, RF test times.

## Sources tried but blocked or skipped

- www.aecouncil.com: http DNS failure, https TLS handshake failure (AEC-Q001/Q004/Q100 not read).
- api.github.com: 403 (session-bound), host stopped; raw.githubusercontent.com: Chiplet Actuary repo README 404 (repo
  parameters for wafer/NRE costs not read).
- api.openalex.org, www.sec.gov, s*.q4cdn.com, investors.skyworksinc.com: stopped earlier in the session (not retried).
- SemiAnalysis, IC Knowledge, Yole, TechSearch: paywalled or not attempted.
- First Infineon URL returned a 301 to /assets/...; the target was fetched after checking the same host's robots.txt.
