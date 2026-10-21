"""Navigation model: task-based sections in a row at the top, the pages of the current section in a second row, a
separate Data management utility section, and in-page tabs for closely related views. Every existing URL keeps
working; this module only decides where a page sits.
"""

# Primary sections (top row): key, label, items (label, href, description); the first item is the section's start page
NAV = (
    ("products", "Products", (
        ("Search & replacements", "/", "Find replacements for a reference part"),
        ("Browse products", "/parts", "Every part by function, with filters for line, grade and lifecycle"),
        ("Skyworks + Qorvo", "/portfolio", "The two lines side by side: strengths, which to pick, cross-selling"),
        ("Compare", "/compare", "Parameter table for any list of parts"),
        ("Price estimate", "/pricing/estimate", "Rough price band at volume from a few distributor prices"),
        ("Radio & audio", "/broadcast", "Broadcast radio tuners and demodulators"),
    )),
    ("systems", "Systems & applications", (
        ("Application library", "/blocks", "Reference architectures and their coverage"),
        ("Application workspace", "/blocks/new", "Build or edit a block diagram"),
        ("Reference designs", "/reference-designs", "Manufacturers' public reference designs and their documents"),
        ("Radio configurations", "/broadcast/configurations", "Saved car-radio tuner configurations"),
    )),
    ("opportunities", "Opportunities", (
        ("Opportunity explorer", "/business/explorer", "Rank missing functions by reach, feasibility, competition"),
        ("RF coverage", "/business/rf-coverage", "RF functions by frequency band and power: covered, at risk, missing"),
        ("Automotive map", "/business/automotive", "Automotive: what we sell today, what to qualify or build"),
        ("Cross-sell", "/business/attach", "What else sits next to a product we sell"),
    )),
    ("growth", "Future growth", (
        ("Research & ideas", "/business/reports", "Research reports and preliminary product ideas and cases"),
        ("Markets & customers", "/business/markets", "End markets and the companies that build the systems"),
        ("Business cases", "/business/shortlist", "Candidates from the portfolio pages and new ideas; cases analysed"),
    )),
    ("knowledge", "Engineering knowledge", (
        ("Knowledge search", "/technical", "Search application notes and specification guides together"),
        ("Specification guides", "/engineering", "What each specification means and how to compare it"),
        ("Technical library", "/library", "Deep dives: block diagrams, design rules, research trends, references"),
        ("RF fundamentals", "/rf-notes", "RF specifications, components, architectures and technologies explained"),
        ("RF bands", "/rf-bands", "Cellular, GNSS, Wi-Fi, satcom and radar bands, with the parts that cover each"),
        ("Interactive visuals", "/visuals", "Sliders, live graphs and equations: RF links, noise, filters, CMTI"),
        ("Technology platforms", "/business/capabilities", "Public Skyworks / Qorvo technologies"),
    )),
)  # fmt: skip

UTILITY = ("manage", "Data management", (
    ("Verify next", "/manage/verify", "A small batch to check: crosses, diagrams and data that vouch for the rest"),
    ("Requests & reviews", "/manage/reviews", "Part requests, diagram feedback and data reviews"),
    ("Site feedback", "/manage/feedback", "Daily digest of the Feedback button, with responses"),
    ("Uploads", "/manage/uploads", "Pictures, block diagrams, documents and explanations"),
    ("Commercial inputs", "/business/data", "ASPs and volumes behind revenue figures"),
    ("Data quality", "/business/quality", "Checks, review status and the validation queue"),
    ("Methodology", "/business/method", "Definitions, formulas, cross rules"),
))  # fmt: skip

# path prefix -> (section key, nav item href); longest matching prefix wins. "/" only matches itself and /find.
PLACES = {
    "/find": ("products", "/"),
    "/parts/": ("products", "/"),
    "/pricing/estimate": ("products", "/pricing/estimate"),
    "/cross/": ("products", "/"),
    "/overlay/": ("products", "/"),
    "/packages/": ("products", "/"),
    "/pricing/": ("products", "/"),
    "/parts": ("products", "/parts"),
    "/compare": ("products", "/compare"),
    "/portfolio": ("products", "/portfolio"),
    "/broadcast/configurations": ("systems", "/broadcast/configurations"),
    "/broadcast": ("products", "/broadcast"),
    "/blocks/feedback": ("manage", "/manage/reviews"),
    "/blocks/coverage": ("systems", "/blocks"),
    "/blocks/new": ("systems", "/blocks/new"),
    "/blocks/": ("systems", "/blocks/new"),
    "/blocks": ("systems", "/blocks"),
    "/reference-designs": ("systems", "/reference-designs"),
    "/business/applications": ("systems", "/blocks"),
    "/business/explorer": ("opportunities", "/business/explorer"),
    "/business/gaps": ("opportunities", "/business/explorer"),
    "/business/technology": ("opportunities", "/business/explorer"),
    "/business/evidence": ("opportunities", "/business/explorer"),
    "/business/attach": ("opportunities", "/business/attach"),
    "/business/rf-coverage": ("opportunities", "/business/rf-coverage"),
    "/business/automotive": ("opportunities", "/business/automotive"),
    "/business/markets": ("growth", "/business/markets"),
    "/business/customers": ("growth", "/business/markets"),
    "/business/reports": ("growth", "/business/reports"),
    "/business/cases": ("growth", "/business/shortlist"),
    "/business/explore": ("growth", "/business/shortlist"),
    "/business/shortlist": ("growth", "/business/shortlist"),
    "/business/capabilities": ("knowledge", "/business/capabilities"),
    "/business/data": ("manage", "/business/data"),
    "/business/quality": ("manage", "/business/quality"),
    "/business/validation": ("manage", "/business/quality"),
    "/business/method": ("manage", "/business/method"),
    "/business": ("opportunities", "/business/explorer"),
    "/rules": ("manage", "/business/method"),
    "/requests": ("manage", "/manage/reviews"),
    "/manage/feedback": ("manage", "/manage/feedback"),
    "/manage/verify": ("manage", "/manage/verify"),
    "/manage/uploads": ("manage", "/manage/uploads"),
    "/manage": ("manage", "/manage/reviews"),
    "/technical": ("knowledge", "/technical"),
    "/notes": ("knowledge", "/technical"),
    "/engineering": ("knowledge", "/engineering"),
    "/rf-notes": ("knowledge", "/rf-notes"),
    "/library": ("knowledge", "/library"),
    "/rf-bands": ("knowledge", "/rf-bands"),
    "/visuals": ("knowledge", "/visuals"),
    "/impact": ("knowledge", "/engineering"),
}

# In-page tabs for views of the same thing (label, href); shown on every page of the group
TABS = (
    (
        ("Library", "/blocks"),
        ("Technical coverage", "/blocks/coverage"),
        ("Portfolio coverage", "/business/applications"),
    ),
    (("Markets", "/business/markets"), ("Customers", "/business/customers")),
    (("Shortlist", "/business/shortlist"), ("New ideas", "/business/explore"), ("Business cases", "/business/cases")),
    (("Review queue", "/manage/reviews"), ("Part requests", "/requests"), ("Diagram feedback", "/blocks/feedback")),
    (("Data quality", "/business/quality"), ("Human validation", "/business/validation")),
    (("Opportunity methodology", "/business/method"), ("Cross rules", "/rules")),
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
