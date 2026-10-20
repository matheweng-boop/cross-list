"""Navigation model: task-based sections in a row at the top, the pages of the current section in a second row, a
separate Data management utility section, and in-page tabs for closely related views. Every existing URL keeps
working; this module only decides where a page sits.
"""

# Primary sections (top row): key, label, items (label, href, description); the first item is the section's start page
NAV = (
    ("products", "Products", (
        ("Search & replacements", "/", "Find replacements for a reference part"),
        ("Compare", "/compare", "Parameter table for any list of parts"),
        ("Lifecycle", "/lifecycle", "New, NRND and obsolete parts"),
        ("Radio & audio", "/broadcast", "Broadcast radio tuners and demodulators"),
    )),
    ("systems", "Systems & applications", (
        ("Application library", "/blocks", "Reference architectures and their coverage"),
        ("Application workspace", "/blocks/new", "Build or edit a block diagram"),
        ("Reference designs", "/reference-designs", "Manufacturers' public reference designs and their documents"),
        ("Radio configurations", "/broadcast/configurations", "Saved car-radio tuner configurations"),
    )),
    ("opportunities", "Opportunities", (
        ("Overview", "/business", "Key results and analysis scope"),
        ("Opportunity explorer", "/business/explorer", "Rank missing functions by reach, feasibility, competition"),
        ("RF coverage", "/business/rf-coverage", "RF functions by frequency band and power: covered, at risk, missing"),
        ("Cross-sell", "/business/attach", "What else sits next to a product we sell"),
        ("Markets & customers", "/business/markets", "End markets and the companies that build the systems"),
        ("Business cases", "/business/shortlist", "Candidates from the portfolio pages and new ideas; cases analysed"),
    )),
    ("knowledge", "Engineering knowledge", (
        ("Knowledge search", "/technical", "Search application notes and specification guides together"),
        ("Specification guides", "/engineering", "What each specification means and how to compare it"),
        ("Technology platforms", "/business/capabilities", "Public Skyworks / Qorvo technologies"),
    )),
)  # fmt: skip

UTILITY = ("manage", "Data management", (
    ("Requests & reviews", "/manage/reviews", "Part requests, diagram feedback and data reviews"),
    ("Commercial inputs", "/business/data", "ASPs and volumes behind revenue figures"),
    ("Data quality", "/business/quality", "Checks, review status and the validation queue"),
    ("Methodology", "/business/method", "Definitions, formulas, cross rules"),
))  # fmt: skip

# path prefix -> (section key, nav item href); longest matching prefix wins. "/" only matches itself and /find.
PLACES = {
    "/find": ("products", "/"),
    "/parts/": ("products", "/"),
    "/cross/": ("products", "/"),
    "/overlay/": ("products", "/"),
    "/packages/": ("products", "/"),
    "/pricing/": ("products", "/"),
    "/parts": ("products", "/"),  # Browse products: no longer in the menu, the page still works
    "/compare": ("products", "/compare"),
    "/lifecycle": ("products", "/lifecycle"),
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
    "/business/markets": ("opportunities", "/business/markets"),
    "/business/customers": ("opportunities", "/business/markets"),
    "/business/cases": ("opportunities", "/business/shortlist"),
    "/business/explore": ("opportunities", "/business/shortlist"),
    "/business/shortlist": ("opportunities", "/business/shortlist"),
    "/business/capabilities": ("knowledge", "/business/capabilities"),
    "/business/data": ("manage", "/business/data"),
    "/business/quality": ("manage", "/business/quality"),
    "/business/validation": ("manage", "/business/quality"),
    "/business/method": ("manage", "/business/method"),
    "/business": ("opportunities", "/business"),
    "/rules": ("manage", "/business/method"),
    "/requests": ("manage", "/manage/reviews"),
    "/manage": ("manage", "/manage/reviews"),
    "/technical": ("knowledge", "/technical"),
    "/notes": ("knowledge", "/technical"),
    "/engineering": ("knowledge", "/engineering"),
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
    (("Candidates", "/business/shortlist"), ("New ideas", "/business/explore"), ("Business cases", "/business/cases")),
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


# small line icons for the section row (SVG path data, 24 x 24, stroked)
ICONS = {  # fmt: skip
    "products": '<path d="M7 7h10v10H7z M4 9h3M4 12h3M4 15h3M17 9h3M17 12h3M17 15h3M9 4v3M12 4v3M15 4v3M9 17v3M12 17v3M15 17v3"/>',  # noqa: E501
    "systems": '<path d="M3 5h7v5H3zM14 14h7v5h-7zM14 5h7v5h-7zM10 7.5h4M17.5 10v4"/>',
    "opportunities": '<path d="M4 19V11M10 19V5M16 19v-6M3 19h18"/>',
    "knowledge": '<path d="M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h10"/>',
    "manage": '<path d="M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',  # noqa: E501
}
