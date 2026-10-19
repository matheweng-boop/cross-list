"""Navigation model: task-based sections in a row at the top, the pages of the current section in a second row, a
separate Data management utility section, and in-page tabs for closely related views. Every existing URL keeps
working; this module only decides where a page sits.
"""

# Primary sections (top row): key, label, items (label, href, description); the first item is the section's start page
NAV = (
    ("products", "Products", (
        ("Search & replacements", "/", "Find replacements for a reference part"),
        ("Browse products", "/parts", "Browse by product family and company"),
        ("Compare", "/compare", "Parameter table for any list of parts"),
        ("Lifecycle", "/lifecycle", "New, NRND and obsolete parts"),
        ("Radio & audio", "/broadcast", "Broadcast radio tuners and demodulators"),
    )),
    ("systems", "Systems & applications", (
        ("Application library", "/blocks", "Reference architectures and their coverage"),
        ("Application workspace", "/blocks/new", "Build or edit a block diagram"),
        ("Radio configurations", "/broadcast/configurations", "Saved car-radio tuner configurations"),
    )),
    ("opportunities", "Opportunities", (
        ("Overview", "/business", "Key results and analysis scope"),
        ("Opportunity explorer", "/business/explorer", "Rank missing functions by reach, feasibility, competition"),
        ("Cross-sell", "/business/attach", "What else sits next to a product we sell"),
        ("Markets & customers", "/business/markets", "End markets and the companies that build the systems"),
        ("Business cases", "/business/cases", "Ideas and case analyses"),
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
    "/parts": ("products", "/parts"),
    "/compare": ("products", "/compare"),
    "/lifecycle": ("products", "/lifecycle"),
    "/broadcast/configurations": ("systems", "/broadcast/configurations"),
    "/broadcast": ("products", "/broadcast"),
    "/blocks/feedback": ("manage", "/manage/reviews"),
    "/blocks/coverage": ("systems", "/blocks"),
    "/blocks/new": ("systems", "/blocks/new"),
    "/blocks/": ("systems", "/blocks/new"),
    "/blocks": ("systems", "/blocks"),
    "/business/applications": ("systems", "/blocks"),
    "/business/explorer": ("opportunities", "/business/explorer"),
    "/business/gaps": ("opportunities", "/business/explorer"),
    "/business/technology": ("opportunities", "/business/explorer"),
    "/business/evidence": ("opportunities", "/business/explorer"),
    "/business/attach": ("opportunities", "/business/attach"),
    "/business/markets": ("opportunities", "/business/markets"),
    "/business/customers": ("opportunities", "/business/markets"),
    "/business/cases": ("opportunities", "/business/cases"),
    "/business/explore": ("opportunities", "/business/cases"),
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
    (("Ideas", "/business/explore"), ("Business cases", "/business/cases")),
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
