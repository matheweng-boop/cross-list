"""Navigation model: task-based sections in a row at the top, the pages of the current section in a second row, a
separate Data management utility section, and in-page tabs for closely related views. Every existing URL keeps
working; this module only decides where a page sits.
"""

# Primary sections (top row): key, label, items (label, href, description); the first item is the section's start page
NAV = (
    ("products", "Products", (
        ("Search & replacements", "/", "Find replacements for a reference part"),
        ("Browse products", "/parts", "Every part by function, with filters for line, grade and lifecycle"),
        ("Part reviews", "/reviews", "A part explained: datasheet, problem, concept, key features; request one"),
        ("Compare", "/compare", "Parameter table for any list of parts"),
        ("Price estimate", "/pricing/estimate", "Rough price band at volume from a few distributor prices"),
        ("Solution price builder", "/pricing/builder", "Price several parts or a whole radio or block diagram"),
    )),
    # owner, 23 Oct 2026: Systems & applications = parts and knowledge we have; Opportunities = gaps and new
    # technology; Future growth = the business side. Systems first, then applications, workspace, designs, cross-sell.
    ("systems", "Systems & applications", (
        ("Systems library", "/library", "Full systems and their sub-systems, with deep dives"),
        ("Application library", "/blocks", "Diagrams grouped by system and sub-system, with their coverage"),
        ("Application workspace", "/blocks/new", "Build or edit a block diagram"),
        ("Reference designs", "/reference-designs", "Manufacturers' public reference designs and their documents"),
        ("Cross-sell", "/blocks/cross-sell",
         "What to sell together: by system, by part, and the Skyworks + Qorvo portfolio side by side"),
        ("RF coverage", "/business/rf-coverage", "RF functions by frequency band and power: covered, at risk, missing"),
        ("Automotive map", "/business/automotive", "Automotive: what we sell today, what to qualify or build"),
    )),
    ("opportunities", "Opportunities", (
        ("Gaps & new technology", "/business/opportunities", "Functions with no part of ours yet: gaps and new tech"),
        ("Competitive analytics", "/business/competitors", "Competitor profiles: size, products, strengths, overlap"),
        ("Risks", "/business/risks", "Competing technologies and products that could endanger our solutions"),
    )),
    ("growth", "Future growth", (
        ("Research & ideas", "/business/reports", "Research reports and preliminary product ideas and cases"),
        ("Markets & customers", "/business/markets", "End markets and the companies that build the systems"),
        ("Shortlist & cases", "/business/shortlist", "Candidates from the portfolio and new ideas; cases analysed"),
        ("TAM estimates", "/business/tam", "Market size per product or technology, with sources to review"),
    )),
    ("knowledge", "Engineering knowledge", (
        ("Interactive visuals", "/visuals", "Sliders and live graphs: RF links, noise, filters, CMTI; RF band chart"),
        ("General knowledge", "/knowledge", "RF fundamentals, specification guides, technology platforms and search"),
    )),
    # owner, 24 Oct 2026: a section for shareable content (public information, ready to share or save as PDF)
    ("shareable", "Shareable", (
        ("Technology overview", "/shareable/technology-overview", "Public, ready to share or save as PDF"),
    )),
)  # fmt: skip

# A section's own landing page, when it has one; the section row links there instead of to the first item
HOMES = {"shareable": "/shareable"}

UTILITY = ("manage", "Data management", (
    ("Overview", "/manage/overview", "Everything at a glance: raw data, today's feedback, what waits for you"),
    ("Schedule", "/manage/schedule", "What runs continuously, daily, weekly; what tonight's run picks up"),
    # owner, 23 Oct 2026: Verify next, requests, site feedback and guest input as one item with tabs
    ("Site data", "/manage/verify", "Verify next, review queue, requests, site feedback and guest input"),
    ("Uploads", "/manage/uploads", "Pictures, block diagrams, documents and explanations"),
    ("Data quality", "/business/quality", "Checks, review status and the validation queue"),
    ("People & invites", "/manage/people", "Invite guests, see their passkeys, remove someone"),
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
    "/portfolio": ("systems", "/blocks/cross-sell"),  # owner, 25 Oct 2026: the portfolio is a Cross-sell tab
    "/broadcast": ("systems", "/blocks"),  # owner, 23 Oct 2026: Radio & audio is the Car radio application
    "/blocks/feedback": ("manage", "/manage/verify"),
    "/blocks/area-requests": ("manage", "/manage/verify"),
    "/blocks/coverage": ("systems", "/blocks"),
    "/blocks/new": ("systems", "/blocks/new"),
    "/blocks/": ("systems", "/blocks/new"),
    "/blocks": ("systems", "/blocks"),
    "/reference-designs": ("systems", "/reference-designs"),
    "/reviews": ("products", "/reviews"),  # owner, 23 Oct 2026: reviews belong to parts
    "/business/applications": ("systems", "/blocks"),
    "/blocks/cross-sell": ("systems", "/blocks/cross-sell"),
    "/business/opportunities": ("opportunities", "/business/opportunities"),
    "/business/explorer": ("opportunities", "/business/opportunities"),
    "/business/gaps": ("opportunities", "/business/opportunities"),
    "/business/technology": ("opportunities", "/business/opportunities"),
    "/business/evidence": ("opportunities", "/business/opportunities"),
    "/business/attach": ("systems", "/blocks/cross-sell"),  # owner, 23 Oct 2026: parts we have
    "/business/rf-coverage": ("systems", "/business/rf-coverage"),
    "/business/risks": ("opportunities", "/business/risks"),
    "/business/automotive": ("systems", "/business/automotive"),
    "/business/competitors": ("opportunities", "/business/competitors"),
    "/business/markets": ("growth", "/business/markets"),
    "/business/customers": ("growth", "/business/markets"),
    "/business/reports": ("growth", "/business/reports"),
    "/business/cases": ("growth", "/business/shortlist"),
    "/business/explore": ("growth", "/business/shortlist"),
    "/business/shortlist": ("growth", "/business/shortlist"),
    "/business/capabilities": ("knowledge", "/knowledge"),
    "/business/data": ("growth", "/business/tam"),
    "/business/tam": ("growth", "/business/tam"),  # owner, 23 Oct 2026: the business side
    "/business/quality": ("manage", "/business/quality"),
    "/business/validation": ("manage", "/business/quality"),
    "/business/method": ("manage", "/business/method"),
    "/business": ("opportunities", "/business/opportunities"),
    "/rules": ("manage", "/business/method"),
    "/requests": ("manage", "/manage/verify"),
    "/manage/feedback": ("manage", "/manage/verify"),
    "/manage/verify": ("manage", "/manage/verify"),
    "/manage/site-data": ("manage", "/manage/verify"),
    "/manage/requests": ("manage", "/manage/verify"),
    "/manage/reviews": ("manage", "/manage/verify"),
    "/manage/uploads": ("manage", "/manage/uploads"),
    "/manage/overview": ("manage", "/manage/overview"),
    "/manage/guest-input": ("manage", "/manage/verify"),
    "/manage/people": ("manage", "/manage/people"),
    "/owner": ("manage", "/manage/people"),
    "/manage/schedule": ("manage", "/manage/schedule"),
    "/manage": ("manage", "/manage/overview"),
    "/library": ("systems", "/library"),  # owner, 23 Oct 2026: part of Systems & applications
    "/visuals": ("knowledge", "/visuals"),
    "/rf-bands": ("knowledge", "/visuals"),
    "/knowledge": ("knowledge", "/knowledge"),
    "/rf-notes": ("knowledge", "/knowledge"),
    "/engineering": ("knowledge", "/knowledge"),
    "/impact": ("knowledge", "/knowledge"),
    "/technical": ("knowledge", "/knowledge"),
    "/notes": ("knowledge", "/knowledge"),
    "/shareable/technology-overview": ("shareable", "/shareable/technology-overview"),
    "/shareable": ("shareable", "/shareable"),
}

# In-page tabs for views of the same thing (label, href); shown on every page of the group
TABS = (
    (
        ("Library", "/blocks"),
        ("Technical coverage", "/blocks/coverage"),
        ("Portfolio coverage", "/business/applications"),
    ),
    (("Markets", "/business/markets"), ("Customers", "/business/customers")),
    # owner, 25 Oct 2026: the Skyworks + Qorvo portfolio moved from Products to Cross-sell (cross-sell = how the two
    # lines go together); the selected system carries over between these tabs (TAB_CARRY)
    (("By system", "/blocks/cross-sell"), ("By part", "/business/attach"),
     ("Skyworks + Qorvo portfolio", "/portfolio")),
    (("Gaps & new technology", "/business/opportunities"), ("Detailed table", "/business/explorer/table")),
    (("Shortlist", "/business/shortlist"), ("New ideas", "/business/explore"), ("Business cases", "/business/cases")),
    # owner, 24 Oct 2026: part requests, diagram feedback and area requests as one Requests tab
    (("Verify next", "/manage/verify"), ("Review queue", "/manage/reviews"), ("Requests", "/manage/requests"),
     ("Site feedback", "/manage/feedback"), ("Guest input", "/manage/guest-input")),
    (("Data quality", "/business/quality"), ("Human validation", "/business/validation")),
    (("Opportunity methodology", "/business/method"), ("Cross rules", "/rules")),
    (("All visuals", "/visuals"), ("RF bands", "/rf-bands")),
    (("Tuners & demodulators", "/broadcast"), ("Radio configurations", "/broadcast/configurations")),
    (
        ("Overview", "/knowledge"),
        ("RF fundamentals", "/rf-notes"),
        ("Specification guides", "/engineering"),
        ("Technology platforms", "/business/capabilities"),
        ("Knowledge search", "/technical"),
    ),
)

# Query parameters a tab link keeps when you switch tabs inside a group (first tab href -> parameter names)
TAB_CARRY = {"/blocks/cross-sell": ("system", "sub")}


def tab_href(tabs, href: str, params) -> str:
    """A tab's link, keeping the selection (?system=…&sub=… on the Cross-sell tabs) when its group carries it."""
    from urllib.parse import urlencode

    given = dict(params)
    if given.get("sel"):  # the system picker on By system sends "system" or "system:sub"
        given["system"], _, given["sub"] = given["sel"].partition(":")
    keep = [(k, given[k]) for k in TAB_CARRY.get(tabs[0][1] if tabs else "", ()) if given.get(k)]
    return f"{href}?{urlencode(keep)}" if keep else href


def _sections():
    return (*NAV, UTILITY)


def owner_page(href: str) -> bool:
    """A menu entry only the owner may open (e.g. TAM estimates under Future growth): hidden from guests."""
    from app.auth.access import owner_only

    return owner_only(href.split("?")[0], "GET")


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
    active_tab = max((h for _, h in (tabs or ()) if _tab_match(path, h)), key=len, default=None)  # most specific
    return {"section": key, "item": href, "crumbs": crumbs, "tabs": tabs, "active_tab": active_tab}


def page_label(path: str) -> str:
    """The page's own name as the menus show it: the in-page tab (the first tab of a group is the menu item), else the
    menu item."""
    st = state(path)
    section = next(s for s in _sections() if s[0] == st["section"])
    if HOMES.get(section[0]) == st["item"]:  # a section's landing page is named after the section
        return section[1]
    item = next((i for i in section[2] if i[1] == st["item"]), section[2][0])
    if st["tabs"] and st["active_tab"] and st["active_tab"] != st["tabs"][0][1]:
        return next(lbl for lbl, h in st["tabs"] if h == st["active_tab"])
    return item[0]


def page_title(path: str, detail: str = "") -> str:
    """<title>: '[detail – ]page – section – BizDev', from the same names as the menus."""
    st = state(path)
    section = next(s for s in _sections() if s[0] == st["section"])
    label = page_label(path)
    return " – ".join(x for x in (detail, "" if label == section[1] else label, section[1], "BizDev") if x)


# small line icons for the section row (SVG path data, 24 x 24, stroked)
ICONS = {  # fmt: skip
    "products": '<path d="M7 7h10v10H7z M4 9h3M4 12h3M4 15h3M17 9h3M17 12h3M17 15h3M9 4v3M12 4v3M15 4v3M9 17v3M12 17v3M15 17v3"/>',  # noqa: E501
    "systems": '<path d="M3 5h7v5H3zM14 14h7v5h-7zM14 5h7v5h-7zM10 7.5h4M17.5 10v4"/>',
    "opportunities": '<path d="M4 19V11M10 19V5M16 19v-6M3 19h18"/>',
    "growth": '<path d="M3 17l6-6 4 4 8-8M15 7h6v6"/>',
    "knowledge": '<path d="M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h10"/>',
    "shareable": '<path d="M12 15V4M8 8l4-4 4 4M7 11H5v9h14v-9h-2"/>',
    "manage": '<path d="M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',  # noqa: E501
}


def guest_blocked(request, href: str) -> bool:
    """A guest is viewing and href is an owner-only page (app/auth/access.py): hide what that page holds, e.g. the TAM
    numbers from TAM estimates (owner, 24 Oct 2026)."""
    from app.auth.session import principal

    p = principal(request)
    return bool(p and p.is_guest and owner_page(href))
