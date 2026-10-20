"""Load parts from a YAML data file (see data/synthetic/demo.yaml for the format)."""

import copy
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import yamlio
from app.matching.rules import load_all_rules
from app.models import (
    Datasheet,
    LifecycleStatus,
    Manufacturer,
    ManufacturerRole,
    Organization,
    Package,
    ParamValue,
    Part,
    User,
)


def ensure_local_user(session: Session) -> User:
    """Single local user until passkey authentication is added."""
    user = session.scalar(select(User).where(User.email == "local@crosslist.invalid"))
    if user is None:
        org = Organization(name="Local")
        session.add(org)
        session.flush()
        user = User(email="local@crosslist.invalid", display_name="Local user", organization_id=org.id)
        session.add(user)
        session.flush()
    return user


def _to_date(v) -> date | None:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


def _num(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


# Values read from unofficial copies of a manufacturer's datasheet (distributor or datasheet-site mirrors) live in a
# separate overlay, data/real/unofficial/<same file name>, and are merged on load only while the setting
# use_unofficial_data is on. Their sources and the overlay's package names carry this mark, so the pages flag them and
# a load without the overlay replaces every one of them with the base file's value (or none).
UNOFFICIAL = "[unofficial copy] "
UNOFFICIAL_DIR = "unofficial"
UNOFFICIAL_TITLE = "From an unofficial copy of the datasheet"


def is_unofficial(text: str | None) -> bool:
    return bool(text) and text.startswith(UNOFFICIAL)


def unofficial_path(path: Path) -> Path:
    return Path(path).parent / UNOFFICIAL_DIR / Path(path).name


def unofficial_keys(part: Part) -> set[str]:
    """Parameter keys (plus "pinout" and "package") of a part whose value came from an unofficial copy."""
    keys = {pv.key for pv in part.params if is_unofficial(pv.source)}
    if is_unofficial(part.pinout_source):
        keys.add("pinout")
    if part.package is not None and is_unofficial(part.package.name):
        keys.add("package")
    return keys


def merge_unofficial(data: dict, overlay: dict) -> dict:
    """The data file with its unofficial overlay merged in: overlay params, pinout and package replace the part's,
    every source is marked, and the part's notes name the copy (host, URL, sha256, fetch date)."""
    data = copy.deepcopy(data)
    codes = {p["code"] for p in data.get("packages", [])}
    data.setdefault("packages", []).extend(
        {**p, "name": f"{UNOFFICIAL}{p['name']}"} for p in overlay.get("packages", []) if p["code"] not in codes
    )
    parts = {p["mpn"]: p for p in data.get("parts", [])}
    for o in overlay.get("parts", []):
        if o["mpn"] not in parts:
            raise ValueError(f"unofficial overlay: {o['mpn']} is not in the data file")
        part, prov = parts[o["mpn"]], o["provenance"]
        given = o.get("param_sources", {})
        sources = part.setdefault("param_sources", {})
        part["params"] = {**part.get("params", {}), **o.get("params", {})}
        filled = list(o.get("params", {}))
        for key in ("pinout", "package"):
            if o.get(key):
                part[key] = o[key]
                filled.append(key)
        for key in filled:
            sources[key] = f"{UNOFFICIAL}{prov['host']}: {given.get(key, '')}"[:300]
        note = (
            f"{UNOFFICIAL}{', '.join(filled)} from {prov['url']} (sha256 {prov['sha256'][:16]}, fetched "
            f"{prov['fetched']}): {prov.get('note', 'unofficial copy of the datasheet')}"
        )
        part["notes"] = "; ".join(x for x in (part.get("notes"), note) if x)
    return data


def load_file(session: Session, path: Path, synthetic: bool = False, unofficial: bool | None = None) -> int:
    """Load one data file. Its unofficial overlay (if any) is merged when ``unofficial`` is true, which defaults to
    the use_unofficial_data setting."""
    data = yamlio.load(Path(path).read_text())
    if unofficial is None:
        from app.config import get_settings

        unofficial = get_settings().use_unofficial_data
    overlay = unofficial_path(path)
    if unofficial and overlay.is_file():
        data = merge_unofficial(data, yamlio.load(overlay.read_text()))
    rules = load_all_rules()

    # Manufacturers and packages are updated from the file on every load, so a corrected dimension, name or role
    # reaches a database that already holds the row (the server's database persists across deploys).
    mfrs = {}
    for m in data.get("manufacturers", []):
        obj = session.scalar(select(Manufacturer).where(Manufacturer.name == m["name"]))
        if obj is None:
            obj = Manufacturer(name=m["name"])
            session.add(obj)
        obj.role, obj.website = ManufacturerRole(m["role"]), m.get("website", obj.website)
        mfrs[m["name"]] = obj

    pkgs = {}
    for p in data.get("packages", []):
        obj = session.scalar(select(Package).where(Package.code == p["code"]))
        if obj is None:
            obj = Package(code=p["code"])
            session.add(obj)
        for key in ("name", "pin_count", "pitch_mm", "body_length_mm", "body_width_mm", "span_mm"):
            setattr(obj, key, p[key])
        for key in ("height_mm", "positions_total", "pin_positions"):
            setattr(obj, key, p.get(key))
        obj.exposed_pad = bool(p.get("exposed_pad", False))
        pkgs[p["code"]] = obj
    session.flush()

    sheets = {}
    for d in data.get("datasheets", []):
        obj = session.scalar(select(Datasheet).where(Datasheet.sha256 == d["sha256"]))
        if obj is None:
            obj = Datasheet(sha256=d["sha256"], filename=d["file"])
            session.add(obj)
        obj.source_url, obj.revision, obj.revision_date = (
            d.get("url"),
            d.get("revision"),
            _to_date(d.get("revision_date")),
        )
        sheets[d["file"]] = obj
    session.flush()

    pinouts = data.get("pinouts", {})
    resolved: dict[str, dict] = {}
    count = 0
    for raw in data.get("parts", []):
        spec = {}
        if "like" in raw:
            spec = copy.deepcopy(resolved[raw["like"]])
            spec.pop("lifecycle", None)
            spec.pop("package_locked", None)
            spec.pop("package_lock_reason", None)
        params = {**spec.get("params", {}), **raw.get("params", {})}
        spec.update({k: v for k, v in raw.items() if k not in ("like", "params")})
        spec["params"] = params
        resolved[spec["mpn"]] = spec

        family = spec["family"]
        if family not in rules:
            raise ValueError(f"{spec['mpn']}: no rules for family {family!r}")
        unknown = set(params) - {p.key for p in rules[family].params}
        if unknown:
            raise ValueError(f"{spec['mpn']}: unknown parameters {sorted(unknown)}")

        mfr = mfrs.get(spec["manufacturer"]) or session.scalar(
            select(Manufacturer).where(Manufacturer.name == spec["manufacturer"])
        )
        pkg = pkgs.get(spec["package"]) or session.scalar(select(Package).where(Package.code == spec["package"]))
        pinout = spec["pinout"]
        pinout = pinouts[pinout] if isinstance(pinout, str) else pinout
        if pinout and len(pinout) != pkg.pin_count:
            raise ValueError(f"{spec['mpn']}: pinout has {len(pinout)} pins, package {pkg.code} has {pkg.pin_count}")

        life = spec.get("lifecycle", {})
        part = session.scalar(select(Part).where(Part.manufacturer_id == mfr.id, Part.mpn == spec["mpn"]))
        if part is None:
            part = Part(mpn=spec["mpn"], manufacturer=mfr)
            session.add(part)
        part.family = family
        part.description = spec.get("description", "")
        part.package = pkg
        part.pinout = list(pinout)
        part.package_locked = bool(spec.get("package_locked", False))
        part.package_lock_reason = spec.get("package_lock_reason")
        part.lifecycle_status = LifecycleStatus(life.get("status", "unknown"))
        part.release_date = _to_date(life.get("release_date"))
        part.datasheet_revision = str(life["revision"]) if life.get("revision") is not None else None
        part.datasheet_date = _to_date(life.get("revision_date"))
        part.lifecycle_source = "synthetic demo data" if synthetic else life.get("source")
        part.is_synthetic = synthetic
        part.datasheet_url = spec.get("datasheet_url")
        part.product_url = spec.get("product_url")
        part.notes = spec.get("notes")
        part.pinout_source = spec.get("param_sources", {}).get("pinout")
        sheet = sheets.get(spec.get("datasheet"))
        if sheet is not None and sheet not in part.datasheets:
            part.datasheets.append(sheet)
        sources = spec.get("param_sources", {})
        if part.params:  # reload: remove the old values before inserting new ones (unique part/key)
            part.params.clear()
            session.flush()
        part.params = [
            ParamValue(key=k, value=v, num=_num(v), source=sources.get(k), datasheet_id=sheet.id if sheet else None)
            for k, v in params.items()
        ]
        count += 1
    session.flush()
    return count


def unofficial_counts(session: Session) -> dict[str, int]:
    """How much of the loaded data came from unofficial datasheet copies: parameter values, pinouts, packages, parts."""
    values = set(session.scalars(select(ParamValue.part_id).where(ParamValue.source.startswith(UNOFFICIAL))))
    pinouts = set(session.scalars(select(Part.id).where(Part.pinout_source.startswith(UNOFFICIAL))))
    packages = set(session.scalars(select(Part.id).join(Package).where(Package.name.startswith(UNOFFICIAL))))
    n_values = session.scalar(select(func.count(ParamValue.id)).where(ParamValue.source.startswith(UNOFFICIAL)))
    return {"params": n_values or 0, "pinouts": len(pinouts), "packages": len(packages),
            "parts": len(values | pinouts | packages)}  # fmt: skip
