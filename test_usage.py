#!/usr/bin/env python3
"""stdlib tests: parser, merge (preserves muse), atomic write, validator, CLI exit codes."""
import json, os, subprocess, sys, tempfile, unittest
from datetime import datetime, timedelta
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import grok_usage as g
from usage_lib import HKT, merge_row, validate

NOW = datetime(2026, 10, 29, 2, 0, tzinfo=HKT)

# Relevant lines from the real grok.com/?_s=usage layout (not a full-page dump).
REAL_LAYOUT = """\
Settings
Account
Weekly Premium Limit
Resets October 30, 2026 at 4:19 PM
Grok Bot
53%
Chat
4%
Imagine
1%
Something else
"""

class Parser(unittest.TestCase):
    def test_used_and_reset_in(self):
        u, r = g.parse_usage_text("Weekly limit\n54.7% used\nResets in 1d 14h", NOW)
        self.assertEqual(u, 54.7); self.assertEqual(r, NOW + timedelta(days=1, hours=14))
    def test_remaining(self):
        u, _ = g.parse_usage_text("You have 12% remaining this week", NOW)
        self.assertEqual(u, 88.0)
    def test_reset_iso(self):
        _, r = g.parse_usage_text("Used: 3%\nresets 2026-10-30T16:19:00+08:00", NOW)
        self.assertEqual(r.isoformat(), "2026-10-30T16:19:00+08:00")
    def test_reset_month_day(self):
        _, r = g.parse_usage_text("40% used · Resets Oct 30, 4:19 PM", NOW)
        self.assertEqual(r.isoformat(), "2026-10-30T16:19:00+08:00")
    def test_reset_full_month(self):
        _, r = g.parse_usage_text("10% used\nResets October 30, 2026 at 4:19 PM", NOW)
        self.assertEqual(r.isoformat(), "2026-10-30T16:19:00+08:00")
    def test_real_layout_sum_bare_pcts(self):
        # Prefer used/remaining first; this fixture has neither — sum 53+4+1.
        u, r = g.parse_usage_text(REAL_LAYOUT, NOW)
        self.assertEqual(u, 58.0)
        self.assertEqual(r.isoformat(), "2026-10-30T16:19:00+08:00")
    def test_real_layout_prefers_used_over_sum(self):
        text = REAL_LAYOUT + "\n58% used\n"
        u, _ = g.parse_usage_text(text, NOW)
        self.assertEqual(u, 58.0)  # explicit "used", not a double-count of parts
    def test_sum_ignores_pcts_before_anchor(self):
        text = "Elsewhere\n99%\nWeekly Premium Limit\nResets October 30, 2026 at 4:19 PM\n10%\n20%\n"
        u, _ = g.parse_usage_text(text, NOW)
        self.assertEqual(u, 30.0)
    def test_no_pct(self):
        with self.assertRaises(ValueError): g.parse_usage_text("hello", NOW)
    def test_logged_out(self):
        self.assertTrue(g.looks_logged_out("Sign in\nContinue with Google"))
        self.assertFalse(g.looks_logged_out("Log in\n20% used"))
        self.assertFalse(g.looks_logged_out(REAL_LAYOUT))
    def test_has_usage_signal_real(self):
        self.assertTrue(g.has_usage_signal(REAL_LAYOUT))
        self.assertFalse(g.has_usage_signal("hello world"))

class Merge(unittest.TestCase):
    def test_preserves_muse_and_demo_flag(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "usage.json")
            muse = {"service": "muse", "name": "Muse", "used_pct": 33.0, "reset_at": "2026-11-01T00:00:00+08:00",
                    "updated_at": "2026-10-29T01:00:00+08:00", "source": "ai-self"}
            json.dump({"schema_version": 1, "rows": [muse]}, open(p, "w"))
            row = g.build_row(50, NOW + timedelta(days=1), NOW)
            doc = merge_row(p, row, demo=True)
            self.assertTrue(doc["demo"])
            self.assertEqual([r["service"] for r in doc["rows"]], ["grok", "muse"])
            self.assertEqual(doc["rows"][1], muse)
            doc = merge_row(p, g.build_row(60, None, NOW), demo=False)
            self.assertNotIn("demo", doc); self.assertEqual(doc["rows"][0]["used_pct"], 60.0)
            self.assertEqual([f for f in os.listdir(d) if f.endswith(".tmp")], [])
    def test_refuses_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "u.json")
            bad = g.build_row(50, None, NOW); bad["used_pct"] = 150
            with self.assertRaises(ValueError): merge_row(p, bad)
            self.assertFalse(os.path.exists(p))

class Validator(unittest.TestCase):
    def ok(self): return {"rows": [{"service": "grok", "used_pct": 1, "reset_at": None, "updated_at": "2026-10-29T02:00:00+08:00", "source": "script"}]}
    def test_ok(self): self.assertEqual(validate(self.ok()), [])
    def test_naive_time(self):
        d = self.ok(); d["rows"][0]["updated_at"] = "2026-10-29T02:00:00"; self.assertTrue(validate(d))
    def test_extra_key_rejected(self):
        d = self.ok(); d["rows"][0]["token"] = "x"; self.assertTrue(validate(d))
        d = self.ok(); d["cookie"] = "x"; self.assertTrue(validate(d))
    def test_bad_source(self):
        d = self.ok(); d["rows"][0]["source"] = "manual"; self.assertTrue(validate(d))
    def test_dup(self):
        d = self.ok(); d["rows"].append(dict(d["rows"][0])); self.assertTrue(validate(d))

class CLI(unittest.TestCase):
    def run_cli(self, *a):
        return subprocess.run([sys.executable, str(HERE / "grok_usage.py"), *a], capture_output=True, text=True)
    def test_missing_profile_exit2_no_write(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "u.json")
            r = self.run_cli("--profile", os.path.join(d, "nope"), "--out", out)
            self.assertEqual(r.returncode, 2); self.assertFalse(os.path.exists(out))
    def test_fake_writes_valid(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "u.json")
            self.assertEqual(self.run_cli("--fake", "--fake-pct", "91", "--out", out).returncode, 0)
            doc = json.load(open(out)); self.assertEqual(validate(doc), []); self.assertTrue(doc["demo"])
    def test_default_url(self):
        self.assertEqual(g.DEFAULT_URL, "https://grok.com/?_s=usage")

if __name__ == "__main__":
    unittest.main(verbosity=1)
