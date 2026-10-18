"""Load parts from a YAML data file (see data/synthetic/demo.yaml for the format)."""

import copy
from datetime import date
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.matching.rules import load_all_rules
from app.models import LifecycleStatus, Manufacturer, ManufacturerRole, Organization, Package, ParamValue, Part, User


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
    data = yaml.safe_load(Path(path).read_text())
    rules = load_all_rules()

    mfrs = {}
    for m in data.get("manufacturers", []):
        obj = session.scalar(select(Manufacturer).where(Manufacturer.name == m["name"]))
        if obj is None:
            obj = Manufacturer(name=m["name"], role=ManufacturerRole(m["role"]), website=m.get("website"))
            session.add(obj)
        mfrs[m["name"]] = obj

    pkgs = {}
    for p in data.get("packages", []):
        obj = session.scalar(select(Package).where(Package.code == p["code"]))
        if obj is None:
            obj = Package(**p)
            session.add(obj)
        pkgs[p["code"]] = obj
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
        if len(pinout) != pkg.pin_count:
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
        part.params = [ParamValue(key=k, value=v, num=_num(v)) for k, v in params.items()]
        count += 1
    session.flush()
    return count
