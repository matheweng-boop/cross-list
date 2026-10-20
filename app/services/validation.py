"""Full data scan: what can be confirmed automatically, and where a person has to look.

Each area runs checks over the data BizDev holds (parts with parameters, the manufacturer catalogues, the block
diagrams, the radio data, the function mapping, the business evidence, commercial inputs). A check either passes
(confirmed automatically, with the rule used), is resolved by a stated rule, or produces items for human validation.
Human items carry a priority from their impact on results (what changes if the item is wrong), the reason a script
cannot decide it, and the page where it is resolved. The scan never changes data.
"""

import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.matching.rules import load_all_rules
from app.models import BusinessInput, Part, PartMapping
from app.services import blocks, broadcast, lifecycle, products, quality
from app.services import opportunity as op

PRIORITY = {"high": 3, "medium": 2, "low": 1}


def _check(name: str, total: int, passed: int, rule: str) -> dict:
    return {"name": name, "total": total, "passed": passed, "rule": rule}


def _item(priority: str, area: str, title: str, why: str, impact: str, link: str, count: int = 1, examples=()) -> dict:
    return {
        "priority": priority,
        "area": area,
        "title": title,
        "why": why,
        "impact": impact,
        "link": link,
        "count": count,
        "examples": list(examples)[:6],
    }


_PART_CHECKS: dict = {}


def _part_checks(session: Session) -> tuple[dict, list]:
    """The checks over parts and catalogues depend only on the part data: worked out once per data version (they
    read every part with its parameters, about a second for 4,000 parts)."""
    v = blocks._data_version(session)
    if v not in _PART_CHECKS:
        _PART_CHECKS.clear()
        _PART_CHECKS[v] = _part_checks_uncached(session)
    return _PART_CHECKS[v]


def _part_checks_uncached(session: Session) -> tuple[dict, list]:
    areas: dict[str, dict] = {}
    items: list[dict] = []

    # ---- parts with full parameters (datasheets) ------------------------------------------------------------
    parts = list(session.scalars(select(Part)).unique())
    rules = load_all_rules()
    checks = []
    suffixed = [p for p in parts if p.manufacturer.name == "Skyworks" and re.search(r"-[AI][A-Z0-9]{1,2}\d?$", p.mpn)]
    ok = [
        p
        for p in suffixed
        if p.param_map().get("qualification")
        == ("automotive" if re.search(r"-A[A-Z0-9]{1,2}\d?$", p.mpn) else "industrial")
    ]
    checks.append(
        _check(
            "Skyworks grade suffix (-A… automotive, -I… industrial) matches the qualification",
            len(suffixed),
            len(ok),
            "ordering-code suffix",
        )
    )
    q1 = [p for p in parts if "Q1" in p.mpn.upper()]
    checks.append(
        _check(
            "Parts named …-Q1 are AEC-Q100",
            len(q1),
            sum(p.param_map().get("qualification") == "automotive" for p in q1),
            "TI / competitor -Q1 suffix",
        )
    )
    pinned = [p for p in parts if p.pinout and p.package and p.package.pin_count]
    checks.append(
        _check(
            "Pinout length equals the package pin count",
            len(pinned),
            sum(len(p.pinout) == p.package.pin_count for p in pinned),
            "package pin count",
        )
    )
    checks.append(
        _check("Datasheet link present", len(parts), sum(bool(p.datasheet_url) for p in parts), "source link")
    )
    missing = Counter()
    miss_ex: dict[tuple, list] = {}
    for p in parts:
        r = rules.get(p.family)
        if not r:
            continue
        pm = p.param_map()
        for prm in r.params:
            if prm.priority == 1 and pm.get(prm.key) in (None, ""):
                missing[(p.family, prm.key)] += 1
                miss_ex.setdefault((p.family, prm.key), []).append(p.mpn)
    n_p1 = sum(1 for p in parts if p.family in rules) * 1
    checks.append(
        _check(
            "Priority 1 parameters present",
            n_p1,
            n_p1 - len({m for ex in miss_ex.values() for m in ex}),
            "rules/<family>.yaml priority 1",
        )
    )
    for (fam, key), n in missing.most_common():
        items.append(
            _item(
                "high" if n >= 10 else "medium",
                "Parts",
                f"{n} {rules[fam].title} parts miss priority 1 '{key}'",
                "The value is in the datasheet table or footnotes in formats a parser cannot read reliably.",
                "Unknown priority 1 values count as deviations: crosses can be missed or downgraded.",
                f"/parts?family={fam}",
                n,
                miss_ex[(fam, key)],
            )
        )
    unknown_life = [p.mpn for p in parts if p.lifecycle_status.value == "unknown"]
    if unknown_life:
        items.append(
            _item(
                "medium",
                "Parts",
                f"{len(unknown_life)} parts with unknown lifecycle",
                "Lifecycle comes from manufacturer pages that did not list these parts.",
                "NRND / obsolete parts are listed last; an unknown one may be recommended.",
                "/parts",
                len(unknown_life),
                unknown_life,
            )
        )
    no_pin = [p.mpn for p in parts if not p.pinout]
    if no_pin:
        items.append(
            _item(
                "low",
                "Parts",
                f"{len(no_pin)} parts without a pinout",
                "Pinouts come from datasheet pin tables; these were not extracted.",
                "Pin-to-pin compatibility cannot be confirmed for them.",
                "/parts?cap=detailed",
                len(no_pin),
                no_pin,
            )
        )
    areas["Parts with full parameters"] = {"records": len(parts), "checks": checks}

    # ---- catalogue vs BizDev ----------------------------------------------------------------------------
    cat = products._catalogue_index()
    checks = []
    both, qconf, lconf = 0, [], []
    for p in parts:
        e = cat.get((p.manufacturer.name, blocks._norm_mpn(p.mpn)))
        if not e:
            continue
        both += 1
        q = p.param_map().get("qualification")
        if (e["qualification"] == "automotive" and q == "industrial") or (
            e["qualification"] == "not_automotive" and q == "automotive"
        ):
            qconf.append(p.mpn)
        pl = lifecycle.status_class(p.lifecycle_status.value)
        if pl != "unknown" and e["lifecycle"] != "unknown" and pl != e["lifecycle"]:
            lconf.append(f"{p.mpn} ({pl} vs catalogue {e['lifecycle']})")
    checks.append(
        _check(
            "Catalogue and datasheet agree on qualification",
            both,
            both - len(qconf),
            "per-part datasheet value wins; catalogue flag is often per series",
        )
    )
    checks.append(_check("Catalogue and datasheet agree on lifecycle", both, both - len(lconf), "comparison"))
    if qconf:
        items.append(
            _item(
                "low",
                "Catalogue",
                f"{len(qconf)} parts: catalogue says automotive, datasheet ordering code says industrial",
                "Resolved by rule (the per-part datasheet value is used); a spot check of a few confirms the rule.",
                "Wrong rule would mis-state the automotive grade in Browse products.",
                "/parts?cat=isolation",
                len(qconf),
                qconf,
            )
        )
    if lconf:
        items.append(
            _item(
                "medium",
                "Catalogue",
                f"{len(lconf)} parts with conflicting lifecycle",
                "Two public sources disagree; only a current product page or PCN decides.",
                "A part may be shown as active although it is NRND, or the reverse.",
                "/parts",
                len(lconf),
                lconf,
            )
        )
    rows = list(cat.values())
    unq = Counter(r["manufacturer"] for r in rows if r["qualification"] == "unknown")
    checks.append(
        _check(
            "Catalogue records with a stated automotive grade",
            len(rows),
            len(rows) - sum(unq.values()),
            "catalogue field",
        )
    )
    uncl = [r["mpn"] for r in rows if r["category"] == "unclassified"]
    checks.append(
        _check(
            "Catalogue records mapped to a functional category", len(rows), len(rows) - len(uncl), "data/taxonomy.yaml"
        )
    )
    if uncl:
        items.append(
            _item(
                "low",
                "Catalogue",
                f"{len(uncl)} catalogue records without a functional category",
                "Their source category is too generic ('Other') to map by rule.",
                "They only appear under Unclassified in Browse products.",
                "/parts?cat=unclassified",
                len(uncl),
                uncl,
            )
        )
    areas["Manufacturer catalogues"] = {"records": len(rows), "checks": checks}
    return areas, items


def scan(session: Session) -> dict:
    pa, pi = _part_checks(session)
    areas: dict[str, dict] = dict(pa)
    items: list[dict] = [dict(i) for i in pi]

    # ---- function mapping and qualification for the business analysis -----------------------------------------
    mine = op.COMPANIES["combined"][1]
    mk = op.makers(session)
    apps = op.with_status(op.applications(), mk, mine)
    fit = op.technology_fit(apps)
    rank = {e["fn"]: i for i, e in enumerate(fit, 1)}
    checks = []
    paths = op.evidence("path")
    decided = {(m.fn, m.mpn.upper()) for m in session.scalars(select(PartMapping))}
    exists = [fn for fn, e in paths.items() if e.get("path") == "exists"]
    for fn in exists:
        sugg = [r["mpn"] for r in quality.possible_existing(session, fn) if (fn, r["mpn"].upper()) not in decided]
        if sugg:
            items.append(
                _item(
                    "high",
                    "Function mapping",
                    f"Do these parts fill '{blocks.catalogue()['functions'][fn]['label']}'?",
                    "Matching a part to a system function needs an engineer's judgement of the datasheet.",
                    f"Confirming turns the gap into a portfolio function (rank {rank.get(fn, '–')} in the explorer).",
                    f"/business/evidence/{fn}#existing",
                    len(sugg),
                    sugg,
                )
            )
    checks.append(
        _check(
            "Functions whose path says 'already sold' with all suggested parts decided",
            len(exists),
            sum(
                1
                for fn in exists
                if not [r for r in quality.possible_existing(session, fn) if (fn, r["mpn"].upper()) not in decided]
            ),
            "part-mapping decisions",
        )
    )
    m = op.markets(session, apps, mine)
    unk = [e for e in m["rows"] if e["qual_unknown"]]
    for e in unk[:12]:
        items.append(
            _item(
                "medium",
                "Qualification",
                f"{e['label']}: automotive needs it, our parts state no grade",
                "The catalogue does not state AEC-Q100 for these parts; only a datasheet or the product team can.",
                "Decides whether it is an existing automotive part or a qualification opportunity (Markets).",
                "/business/markets?view=qual_unknown",
                e["unknown_parts"],
            )
        )
    checks.append(
        _check(
            "Automotive-needed functions with a stated grade",
            sum(1 for e in m["rows"] if e["by_market"].get("Automotive")),
            sum(1 for e in m["rows"] if e["by_market"].get("Automotive") and not e["qual_unknown"]),
            "three-state qualification",
        )
    )
    radio = broadcast.catalog()
    no_aec = [d["mpn"] for d in radio if d.get("aec_q100") is None]
    checks.append(
        _check("Radio parts with a stated AEC-Q100 grade", len(radio), len(radio) - len(no_aec), "radio data")
    )
    if no_aec:
        items.append(
            _item(
                "medium",
                "Qualification",
                f"{len(no_aec)} radio parts without an AEC-Q100 statement",
                "Their data sheets in the radio data do not state the grade.",
                "Car-radio configurations may propose a part without a confirmed automotive grade.",
                "/broadcast",
                len(no_aec),
                no_aec,
            )
        )
    areas["Function mapping and qualification"] = {"records": len(m["rows"]), "checks": checks}

    # ---- block diagrams ----------------------------------------------------------------------------------------
    fns = blocks.catalogue()["functions"]
    tpls = [*blocks.templates(), *blocks.background_templates()]
    checks = []
    unknown_fns = sorted({fn for t in tpls for fn in blocks.template_functions(t) if fn not in fns})
    checks.append(
        _check(
            "Every block uses a known function",
            len(tpls),
            len(tpls) - sum(1 for t in tpls if any(fn not in fns for fn in blocks.template_functions(t))),
            "functions.yaml",
        )
    )
    nosrc = [blocks.display_name(t) for t in blocks.templates() if not t.get("sources")]
    checks.append(
        _check(
            "Library architectures with a cited source",
            len(blocks.templates()),
            len(blocks.templates()) - len(nosrc),
            "sources field",
        )
    )
    if unknown_fns:
        items.append(
            _item(
                "medium",
                "Block diagrams",
                f"{len(unknown_fns)} block functions not in the catalogue",
                "A new chip type needs a decision: map it to an existing function or add one.",
                "Their sockets count as 'unknown' and are left out of coverage.",
                "/blocks",
                len(unknown_fns),
                unknown_fns,
            )
        )
    groups = blocks.variant_groups()
    if groups:
        items.append(
            _item(
                "medium",
                "Block diagrams",
                f"{len(groups)} groups of possible architecture variants",
                "Whether two reference designs describe one application is a judgement, not a rule.",
                "Until decided, counts are reference architectures, not unique applications.",
                "/blocks?variants=true",
                sum(len(v) for v in groups.values()),
                list(groups),
            )
        )
    if nosrc:
        items.append(
            _item(
                "low",
                "Block diagrams",
                f"{len(nosrc)} library architectures without a cited source",
                "Drawn from experience before sources were recorded.",
                "Their blocks cannot be traced to a document.",
                "/blocks",
                len(nosrc),
                nosrc,
            )
        )
    areas["Block diagrams"] = {"records": len(tpls), "checks": checks}

    # ---- business evidence -------------------------------------------------------------------------------------
    checks = []
    rev = quality.summary(session)
    top = {e["fn"] for e in fit[:25]}
    for name, (label, data) in quality.datasets().items():
        entries = {k: e for k, e in data.items() if isinstance(e, dict)}
        if not entries:
            continue
        st = Counter((e.get("check") or {}).get("status") for e in entries.values())
        human = Counter(quality.state(rev.get((name, k))) for k in entries)
        checks.append(
            _check(
                f"{label}: source-checked (confirmed or corrected)",
                len(entries),
                st["confirmed"] + st["corrected"],
                "opened public sources",
            )
        )
        unconf = [k for k, e in entries.items() if (e.get("check") or {}).get("status") == "unconfirmed"]
        unchecked = [k for k, e in entries.items() if not e.get("check")]
        hot = [k for k in unconf + unchecked if k in top]
        if hot:
            items.append(
                _item(
                    "high" if name in ("path", "technology", "competition", "trends") else "medium",
                    "Evidence",
                    f"{label}: {len(hot)} top-ranked functions without a confirming source",
                    "No public source confirmed it automatically (blocked site, nothing found, or not checked yet).",
                    "These feed the top of the Opportunity explorer."
                    if name in ("path", "technology", "competition", "trends")
                    else "Shown as evidence for top-ranked functions.",
                    "/business/quality",
                    len(hot),
                    hot,
                )
            )
        rest = [k for k in unconf + unchecked if k not in top]
        if rest:
            items.append(
                _item(
                    "low",
                    "Evidence",
                    f"{label}: {len(rest)} further items without a confirming source",
                    "Same reason; lower impact.",
                    "Ranked lower or not scored.",
                    "/business/quality",
                    len(rest),
                    rest,
                )
            )
        if human["disputed"]:
            items.append(
                _item(
                    "high",
                    "Evidence",
                    f"{label}: {human['disputed']} items disputed by reviewers",
                    "People marked them wrong; the data file must be corrected.",
                    "Results still use the disputed value.",
                    "/business/quality/todo.txt",
                    human["disputed"],
                )
            )
    areas["Business evidence"] = {"records": sum(len(d) for _, d in quality.datasets().values()), "checks": checks}

    # ---- commercial inputs -------------------------------------------------------------------------------------
    rows_ci = list(session.scalars(select(BusinessInput)))
    asp_n = sum(r.kind == "asp" for r in rows_ci)
    needed = len({p.fn for a in apps for p in a.positions if p.status in op.IN_SCOPE})
    areas["Commercial inputs"] = {
        "records": len(rows_ci),
        "checks": [_check("Functions with an ASP", needed, asp_n, "your inputs")],
    }
    if asp_n < needed:
        items.append(
            _item(
                "medium",
                "Commercial inputs",
                f"{needed - asp_n} functions without an ASP",
                "Prices are commercial knowledge; nothing is estimated automatically.",
                "Revenue and TAM cover only priced functions.",
                "/business/data?show=unknown",
                needed - asp_n,
            )
        )

    items.sort(key=lambda i: (-PRIORITY[i["priority"]], -i["count"]))
    totals = Counter(i["priority"] for i in items)
    n_checks = [c for a in areas.values() for c in a["checks"]]
    return {
        "areas": areas,
        "items": items,
        "totals": totals,
        "checked": sum(c["total"] for c in n_checks),
        "passed": sum(c["passed"] for c in n_checks),
    }
