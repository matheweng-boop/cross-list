"""Navigation model: task-based sections in a row at the top, the pages of the current section in a second row, a
separate Data management utility section, and in-page tabs for closely related views. Every existing URL keeps
working; this module only decides where a page sits.
"""

# Primary sections (top row): key, label, items (label, href, description); the first item is the section's start page
NAV = (
    ("products", "Products", (
        ("Search & replacements", "/", "Find replacements for a reference part"),
        ("Browse products", "/parts", "Every part by function, with filters for line, grade and lifecycle"),
        ("Skyworks + Qorvo portfolio", "/portfolio",
         "What each company adds: product categories, RF by band, synergies, which to pick"),
        ("Compare", "/compare", "Parameter table for any list of parts"),
        ("Price estimate", "/pricing/estimate", "Rough price band at volume from a few distributor prices"),
        ("Solution price builder", "/pricing/builder", "Price several parts or a whole radio or block diagram"),
    )),
    ("systems", "Systems & applications", (
        ("Application library", "/blocks", "Reference architectures and their coverage"),
        ("Application workspace", "/blocks/new", "Build or edit a block diagram"),
        ("Cross-sell & gaps", "/blocks/cross-sell", "What to sell more of, the gaps to fill and new technology"),
        ("Reference designs", "/reference-designs", "Manufacturers' public reference designs and their documents"),
        ("Technology reviews", "/reviews", "A part explained: datasheet, problem, concept, key features; request one"),
        ("Radio & audio", "/broadcast", "Broadcast radio tuners and demodulators"),
        ("Radio configurations", "/broadcast/configurations", "Saved car-radio tuner configurations"),
    )),
    ("opportunities", "Opportunities", (
        ("RF coverage", "/business/rf-coverage", "RF functions by frequency band and power: covered, at risk, missing"),
        ("Automotive map", "/business/automotive", "Automotive: what we sell today, what to qualify or build"),
        ("Cross-sell", "/business/attach", "What else sits next to a product we sell"),
        ("Competitive analytics", "/business/competitors", "Competitor profiles: size, products, strengths, overlap"),
    )),
    ("growth", "Future growth", (
        ("Research & ideas", "/business/reports", "Research reports and preliminary product ideas and cases"),
        ("Markets & customers", "/business/markets", "End markets and the companies that build the systems"),
        ("Business cases", "/business/shortlist", "Candidates from the portfolio pages and new ideas; cases analysed"),
    )),
    ("knowledge", "Engineering knowledge", (
        ("Systems library", "/library", "Deep dives per system: diagrams, design rules, trends, links to basics"),
        ("Interactive visuals", "/visuals", "Sliders and live graphs: RF links, noise, filters, CMTI; RF band chart"),
        ("General knowledge", "/knowledge", "RF fundamentals, specification guides, technology platforms and search"),
    )),
)  # fmt: skip

UTILITY = ("manage", "Data management", (
    ("Overview", "/manage/overview", "Review status per data set and what is waiting for you"),
    ("Schedule", "/manage/schedule", "What runs continuously, daily, weekly; what tonight's run picks up"),
    ("Verify next", "/manage/verify", "A small batch to check: crosses, diagrams and data that vouch for the rest"),
    ("Requests & reviews", "/manage/reviews", "Part requests, diagram feedback and data reviews"),
    ("Site feedback", "/manage/feedback", "Daily digest of the Feedback button, with responses"),
    ("Uploads", "/manage/uploads", "Pictures, block diagrams, documents and explanations"),
    ("TAM estimates", "/business/tam", "Market size per product or technology, with sources to review"),
    ("Data quality", "/business/quality", "Checks, review status and the validation queue"),
    ("Methodology", "/business/method", "Definitions, formulas, cross rules"),
))  # fmt: skip

# path prefix -> (section key, nav item href); longest matching prefix wins. "/" only matches itself and /find.
PLACES = {
    "/find": ("products", "/"),
    "/parts/": ("products", "/"),
    "/pricing/estimate": ("products", "/pricing/estimate"),
    "/pricing/builder": ("products", "/pricing/builder"),
    "/cross/": ("products", "/"),
    "/overlay/": ("products", "/"),
    "/packages/": ("products", "/"),
    "/pricing/": ("products", "/"),
    "/parts": ("products", "/parts"),
    "/compare": ("products", "/compare"),
    "/portfolio": ("products", "/portfolio"),
    "/broadcast/configurations": ("systems", "/broadcast/configurations"),
    "/broadcast": ("systems", "/broadcast"),
    "/blocks/feedback": ("manage", "/manage/reviews"),
    "/blocks/area-requests": ("manage", "/manage/reviews"),
    "/blocks/coverage": ("systems", "/blocks"),
    "/blocks/new": ("systems", "/blocks/new"),
    "/blocks/": ("systems", "/blocks/new"),
    "/blocks": ("systems", "/blocks"),
    "/reference-designs": ("systems", "/reference-designs"),
    "/reviews": ("systems", "/reviews"),
    "/business/applications": ("systems", "/blocks"),
    "/blocks/cross-sell": ("systems", "/blocks/cross-sell"),
    "/business/explorer": ("systems", "/blocks/cross-sell"),
    "/business/gaps": ("systems", "/blocks/cross-sell"),
    "/business/technology": ("systems", "/blocks/cross-sell"),
    "/business/evidence": ("systems", "/blocks/cross-sell"),
    "/business/attach": ("opportunities", "/business/attach"),
    "/business/rf-coverage": ("opportunities", "/business/rf-coverage"),
    "/business/automotive": ("opportunities", "/business/automotive"),
    "/business/competitors": ("opportunities", "/business/competitors"),
    "/business/markets": ("growth", "/business/markets"),
    "/business/customers": ("growth", "/business/markets"),
    "/business/reports": ("growth", "/business/reports"),
    "/business/cases": ("growth", "/business/shortlist"),
    "/business/explore": ("growth", "/business/shortlist"),
    "/business/shortlist": ("growth", "/business/shortlist"),
    "/business/capabilities": ("knowledge", "/knowledge"),
    "/business/data": ("manage", "/business/tam"),
    "/business/tam": ("manage", "/business/tam"),
    "/business/quality": ("manage", "/business/quality"),
    "/business/validation": ("manage", "/business/quality"),
    "/business/method": ("manage", "/business/method"),
    "/business": ("opportunities", "/business/rf-coverage"),
    "/rules": ("manage", "/business/method"),
    "/requests": ("manage", "/manage/reviews"),
    "/manage/feedback": ("manage", "/manage/feedback"),
    "/manage/verify": ("manage", "/manage/verify"),
    "/manage/uploads": ("manage", "/manage/uploads"),
    "/manage/overview": ("manage", "/manage/overview"),
    "/manage/schedule": ("manage", "/manage/schedule"),
    "/manage": ("manage", "/manage/reviews"),
    "/library": ("knowledge", "/library"),
    "/visuals": ("knowledge", "/visuals"),
    "/rf-bands": ("knowledge", "/visuals"),
    "/knowledge": ("knowledge", "/knowledge"),
    "/rf-notes": ("knowledge", "/knowledge"),
    "/engineering": ("knowledge", "/knowledge"),
    "/impact": ("knowledge", "/knowledge"),
    "/technical": ("knowledge", "/knowledge"),
    "/notes": ("knowledge", "/knowledge"),
}

# In-page tabs for views of the same thing (label, href); shown on every page of the group
TABS = (
    (
        ("Library", "/blocks"),
        ("Technical coverage", "/blocks/coverage"),
        ("Portfolio coverage", "/business/applications"),
    ),
    (("Markets", "/business/markets"), ("Customers", "/business/customers")),
    (("Cross-sell & gaps", "/blocks/cross-sell"), ("Detailed table", "/business/explorer/table")),
    (("Shortlist", "/business/shortlist"), ("New ideas", "/business/explore"), ("Business cases", "/business/cases")),
    (("Review queue", "/manage/reviews"), ("Part requests", "/requests"), ("Diagram feedback", "/blocks/feedback"),
     ("Area requests", "/blocks/area-requests")),
    (("Data quality", "/business/quality"), ("Human validation", "/business/validation")),
    (("Opportunity methodology", "/business/method"), ("Cross rules", "/rules")),
    (("All visuals", "/visuals"), ("RF bands", "/rf-bands")),
    (
        ("Overview", "/knowledge"),
        ("RF fundamentals", "/rf-notes"),
        ("Specification guides", "/engineering"),
        ("Technology platforms", "/business/capabilities"),
        ("Knowledge search", "/technical"),
    ),
)


def _sections():
    return (*NAV, UTILITY)


def place(path: str) -> tuple[str, str]:
    if path in ("/", "/find"):
        return "products", "/"
    best = max((p for p in PLACES if p != "/" and path.startswith(p)), key=len, default=None)
    return PLACES[best] if best else ("products", "/")


def _tab_match(path: str, href: str) -> bool:
    return path == href or (href != "/blocks" and path.startswith(href + "/"))


def state(path: str) -> dict:
    """Everything the layout needs: active section and item, breadcrumbs, in-page tabs."""
    key, href = place(path)
    section = next(s for s in _sections() if s[0] == key)
    item = next((i for i in section[2] if i[1] == href), section[2][0])
    crumbs = [(section[1], section[2][0][1]), (item[0], item[1])]
    tabs = next((g for g in TABS if any(_tab_match(path, h) for _, h in g)), None)
    active_tab = next((h for _, h in (tabs or ()) if _tab_match(path, h)), None)
    return {"section": key, "item": href, "crumbs": crumbs, "tabs": tabs, "active_tab": active_tab}


def page_label(path: str) -> str:
    """The page's own name as the menus show it: the in-page tab (the first tab of a group is the menu item), else the
    menu item."""
    st = state(path)
    section = next(s for s in _sections() if s[0] == st["section"])
    item = next((i for i in section[2] if i[1] == st["item"]), section[2][0])
    if st["tabs"] and st["active_tab"] and st["active_tab"] != st["tabs"][0][1]:
        return next(lbl for lbl, h in st["tabs"] if h == st["active_tab"])
    return item[0]


def page_title(path: str, detail: str = "") -> str:
    """<title>: '[detail – ]page – section – BizDev', from the same names as the menus."""
    st = state(path)
    section = next(s for s in _sections() if s[0] == st["section"])
    return " – ".join(x for x in (detail, page_label(path), section[1], "BizDev") if x)


# small line icons for the section row (SVG path data, 24 x 24, stroked)
ICONS = {  # fmt: skip
    "products": '<path d="M7 7h10v10H7z M4 9h3M4 12h3M4 15h3M17 9h3M17 12h3M17 15h3M9 4v3M12 4v3M15 4v3M9 17v3M12 17v3M15 17v3"/>',  # noqa: E501
    "systems": '<path d="M3 5h7v5H3zM14 14h7v5h-7zM14 5h7v5h-7zM10 7.5h4M17.5 10v4"/>',
    "opportunities": '<path d="M4 19V11M10 19V5M16 19v-6M3 19h18"/>',
    "growth": '<path d="M3 17l6-6 4 4 8-8M15 7h6v6"/>',
    "knowledge": '<path d="M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h10"/>',
    "manage": '<path d="M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',  # noqa: E501
}
