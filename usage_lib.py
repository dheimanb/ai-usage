"""Shared helpers: atomic merge of usage.json + stdlib validator.

usage.json only ever holds percentages and timestamps. No cookies, tokens, or page content.
"""
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone

HKT = timezone(timedelta(hours=8))
ALLOWED_ROW_KEYS = {"service", "name", "used_pct", "reset_at", "updated_at", "source"}
REQUIRED_ROW_KEYS = {"service", "used_pct", "reset_at", "updated_at", "source"}
ALLOWED_TOP_KEYS = {"schema_version", "demo", "rows"}
SOURCES = {"script", "ai-self"}
SERVICE_RE = re.compile(r"^[a-z0-9-]{1,32}$")
# ISO 8601 with explicit offset (Z or +hh:mm); naive times are rejected.
ISO_TZ_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$")

DEFAULT_ROWS = [
    {"service": "grok", "name": "Grok 共用池", "used_pct": None, "reset_at": None, "updated_at": None, "source": "script"},
    # Placeholder: bibi writes this row from their own machine.
    {"service": "muse", "name": "Muse", "used_pct": None, "reset_at": None, "updated_at": None, "source": "ai-self"},
]


def now_hkt():
    return datetime.now(HKT).replace(microsecond=0)


def iso(dt):
    return dt.astimezone(HKT).replace(microsecond=0).isoformat() if dt else None


def _is_iso_tz(v):
    if not isinstance(v, str) or not ISO_TZ_RE.match(v):
        return False
    try:
        datetime.fromisoformat(v.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate(doc):
    """Return a list of error strings (empty = valid). Mirrors usage.schema.json."""
    errs = []
    if not isinstance(doc, dict):
        return ["top level must be an object"]
    extra = set(doc) - ALLOWED_TOP_KEYS
    if extra:
        errs.append(f"unexpected top-level keys: {sorted(extra)}")
    if "demo" in doc and not isinstance(doc["demo"], bool):
        errs.append("demo must be boolean")
    if "schema_version" in doc and doc["schema_version"] != 1:
        errs.append("schema_version must be 1")
    rows = doc.get("rows")
    if not isinstance(rows, list):
        return errs + ["rows must be an array"]
    seen = set()
    for i, r in enumerate(rows):
        p = f"rows[{i}]"
        if not isinstance(r, dict):
            errs.append(f"{p} must be an object"); continue
        missing = REQUIRED_ROW_KEYS - set(r)
        if missing:
            errs.append(f"{p} missing {sorted(missing)}")
        extra = set(r) - ALLOWED_ROW_KEYS
        if extra:
            errs.append(f"{p} unexpected keys {sorted(extra)}")
        s = r.get("service")
        if not isinstance(s, str) or not SERVICE_RE.match(s):
            errs.append(f"{p}.service must match {SERVICE_RE.pattern}")
        elif s in seen:
            errs.append(f"{p}.service duplicate '{s}'")
        else:
            seen.add(s)
        if "name" in r and not (isinstance(r["name"], str) and len(r["name"]) <= 40):
            errs.append(f"{p}.name must be a short string")
        u = r.get("used_pct")
        if u is not None and (isinstance(u, bool) or not isinstance(u, (int, float)) or not 0 <= u <= 100):
            errs.append(f"{p}.used_pct must be number 0-100 or null")
        for k in ("reset_at", "updated_at"):
            v = r.get(k)
            if v is not None and not _is_iso_tz(v):
                errs.append(f"{p}.{k} must be ISO 8601 with timezone offset or null")
        if r.get("source") not in SOURCES:
            errs.append(f"{p}.source must be one of {sorted(SOURCES)}")
    return errs


def load(path):
    if not os.path.exists(path):
        return {"schema_version": 1, "rows": [dict(r) for r in DEFAULT_ROWS]}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def merge_row(path, row, demo=None):
    """Replace the row with the same service (others untouched) and write atomically."""
    doc = load(path)
    rows = [r for r in doc.get("rows", []) if r.get("service") != row["service"]]
    # keep grok first, others in existing order; ensure muse placeholder exists
    rows.insert(0, row) if row["service"] == "grok" else rows.append(row)
    if not any(r.get("service") == "muse" for r in rows):
        rows.append(dict(DEFAULT_ROWS[1]))
    doc["rows"] = rows
    doc["schema_version"] = 1
    if demo is not None:
        if demo:
            doc["demo"] = True
        else:
            doc.pop("demo", None)
    errs = validate(doc)
    if errs:
        raise ValueError("refusing to write invalid usage.json: " + "; ".join(errs))
    write_atomic(path, doc)
    return doc


def write_atomic(path, doc):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".usage.", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
