"""Load parts from a YAML data file (see data/synthetic/demo.yaml for the format)."""

import copy
from datetime import date
from pathlib import Path

from sqlalchemy import select
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


def load_file(session: Session, path: Path, synthetic: bool = False) -> int:
    data = yamlio.load(Path(path).read_text())
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
