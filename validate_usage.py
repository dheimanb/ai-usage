#!/usr/bin/env python3
"""Validate usage.json (stdlib only). Usage: python3 validate_usage.py [usage.json]"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from usage_lib import validate  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent / "usage.json")
try:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
except Exception as e:
    print(f"INVALID {path}: cannot parse ({e})"); sys.exit(1)
errs = validate(doc)
if errs:
    print(f"INVALID {path}"); [print("  -", e) for e in errs]; sys.exit(1)
print(f"OK {path}: {len(doc['rows'])} rows" + (" (demo)" if doc.get("demo") else ""))
