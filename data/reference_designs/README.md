# Reference designs from manufacturers' public sites

One file per source (`ti.yaml`, `infineon.yaml`, `renesas.yaml`, `rohm.yaml`, `skyworks.yaml`, `murata.yaml`, `uwb_public.yaml` (UWB diagrams from several publishers); the application lists that fed the block diagrams are in `data/blocks/research/`). Collected from
public pages only (robots.txt respected, one request at a time, at least 1 s apart, no log-in, no forms). Sites that
block automated access (Analog Devices, ST, NXP, onsemi, Microchip, Toshiba, Nexperia, Qorvo) are skipped.
Design files are not downloaded: their public links are recorded.

```yaml
source: {vendor: TI, pages: ["https://www.ti.com/reference-designs/index.html"], collected: 2026-10-19, method: "..."}
designs:
  - id: TIDA-010054                 # the vendor's design number
    title: "..."                    # as published
    url: "https://..."              # the design's page
    vendor: TI
    applications: [EV charging station]   # the vendor's own application / end-equipment names
    markets: [Automotive]           # BizDev end markets where clear: Automotive, Industrial, Motor drives, Power & isolation,
                                    # Appliances & building, Medical, Communications equipment, RF & connectivity,
                                    # Enterprise & data center, Consumer & personal electronics
    summary: "one or two sentences from the page"
    parts: [UCC21750, AMC1311]      # the vendor parts the design uses (as listed on the page)
    functions: [gate_driver, isolated_amplifier]   # BizDev function ids (data/blocks/functions.yaml) the design contains
    documents:                      # public links only; omit what the page does not offer
      design_guide: "https://..."
      schematic: "https://..."
      bom: "https://..."
      layout: "https://..."
      block_diagram: "https://..."  # image or page anchor
      other: ["https://..."]
    isolation: true                 # true when the design crosses an isolation barrier (isolators, isolated gate drivers,
                                    # isolated amplifiers / DC-DC); omitted when not
```

Application block diagrams (`*_applications.yaml`) use the format of `data/blocks/research/ti_block_diagrams.yaml`
(docs, applications with groups / links / features), so they can become library templates.
