#!/usr/bin/env python3
"""Grok shared weekly quota reader -> usage.json (trial / phase 0).

Modes
  --fake       write clearly-marked demo data (top-level "demo": true). No browser.
  --dry-run    real read, but print the parsed row instead of writing.
  (default)    real read + atomic merge of the grok row into usage.json.

Real read = headless Google Chrome with heiman's dedicated profile (--user-data-dir),
driven over --remote-debugging-pipe (cdp_pipe.py); only document.body.innerText is read. This script NEVER opens, reads, copies, prints or
logs cookies, tokens, localStorage or sessionStorage; the page text is kept in memory only,
never written to disk or logged. Only used % and reset time leave this process.

Exit codes: 0 ok | 2 profile missing | 3 not logged in | 4 page loaded but parse failed
            | 5 browser error
"""
import argparse
import logging
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from usage_lib import HKT, iso, merge_row, now_hkt  # noqa: E402

DEFAULT_PROFILE = HERE / "profile-grok"
DEFAULT_OUT = HERE / "usage.json"
DEFAULT_URL = "https://grok.com/?_s=usage"

log = logging.getLogger("grok_usage")


# ---------------------------------------------------------------- parser (isolated)
# Everything the real page layout affects lives in this block. Fix here when it breaks.
LOGIN_MARKERS = re.compile(r"\b(sign in|log in|sign up|continue with (google|apple|x))\b|登入|登錄", re.I)
USED_PATTERNS = [
    re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%\s*(?:used|已用|consumed)", re.I),
    re.compile(r"(?:used|已用)\D{0,20}?(\d{1,3}(?:\.\d+)?)\s*%", re.I),
]
REMAINING_PATTERNS = [
    re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%\s*(?:remaining|left|剩餘|未用)", re.I),
    re.compile(r"(?:remaining|left|剩餘|未用)\D{0,20}?(\d{1,3}(?:\.\d+)?)\s*%", re.I),
]
# Real layout (2026-10): "Weekly Premium Limit" then bare "53%\n4%\n1%" (Bot/Chat/Imagine); total not in text.
SECTION_ANCHOR = re.compile(r"(?:Weekly\s+Premium\s+Limit|\bUsage\b)", re.I)
BARE_PCT_LINE = re.compile(r"^\s*(\d{1,3}(?:\.\d+)?)\s*%\s*$")
RESET_ISO = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2}))")
RESET_IN = re.compile(
    r"reset[s]?\s+in\s+(?:(\d+)\s*d(?:ays?)?)?[\s,]*(?:(\d+)\s*h(?:ours?|rs?)?)?[\s,]*(?:(\d+)\s*m(?:in(?:utes?)?)?)?",
    re.I)
# Captures "October 30, 2026 at 4:19 PM" / "Oct 30, 4:19 PM" etc. Month name up to 9 letters (September).
RESET_ON = re.compile(
    r"reset[s]?\s+(?:on|at)?\s*"
    r"([A-Z][a-z]{2,9}\.?\s+\d{1,2}(?:,\s*\d{4})?(?:,?\s*(?:at\s+)?\d{1,2}:\d{2}\s*(?:[AP]M)?)?)",
    re.I)


def parse_usage_text(text: str, now: datetime):
    """Return (used_pct, reset_at_datetime_or_None). Raises ValueError if no % found."""
    used = None
    for pat in USED_PATTERNS:
        m = pat.search(text)
        if m:
            used = float(m.group(1))
            break
    if used is None:
        for pat in REMAINING_PATTERNS:
            m = pat.search(text)
            if m:
                used = round(100 - float(m.group(1)), 1)
                break
    if used is None:
        used = _sum_section_pcts(text)
    if used is None or not 0 <= used <= 100:
        raise ValueError("no usage percentage found")

    reset = None
    m = RESET_ISO.search(text)
    if m:
        reset = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
    if reset is None:
        m = RESET_IN.search(text)
        if m and any(m.groups()):
            d, h, mi = (int(g or 0) for g in m.groups())
            reset = now + timedelta(days=d, hours=h, minutes=mi)
    if reset is None:
        m = RESET_ON.search(text)
        if m:
            reset = _parse_month_day(m.group(1), now)
    return used, reset


def _sum_section_pcts(text: str):
    """Near Usage / Weekly Premium Limit, sum consecutive bare-N% lines (shared pool parts).

    Real layout (confirmed): after the anchor + reset line, bare % lines appear in a row
    (e.g. 53% / 4% / 1% for Bot/Chat/Imagine). At most one short label line is allowed
    between bare % lines; blank, another section, annotated %, or a second non-% ends the run.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if SECTION_ANCHOR.search(line):
            start = i
            break
    if start is None:
        return None
    pcts = []
    started = False
    pending_label = False
    for line in lines[start + 1:]:
        m = BARE_PCT_LINE.match(line)
        if m:
            pcts.append(float(m.group(1)))
            started = True
            pending_label = False
            continue
        if not started:
            continue  # skip reset line / preamble before the first %
        stripped = line.strip()
        if stripped == "" or SECTION_ANCHOR.search(line) or "%" in stripped:
            break
        if len(stripped) <= 40 and not pending_label:
            pending_label = True  # one short label between parts
            continue
        break
    if not pcts:
        return None
    total = round(sum(pcts), 1)
    if not 0 <= total <= 100:
        return None
    return total




def _parse_month_day(s: str, now: datetime):
    s = re.sub(r"\s+", " ", s.replace(".", "").replace(" at ", " ")).strip()
    for fmt in (
        "%B %d, %Y %I:%M %p", "%b %d, %Y %I:%M %p",
        "%B %d, %Y, %I:%M %p", "%b %d, %Y, %I:%M %p",
        "%b %d %I:%M %p", "%b %d, %I:%M %p",
        "%B %d, %Y", "%b %d, %Y", "%B %d", "%b %d", "%b %d %H:%M",
    ):
        try:
            dt = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if "%Y" not in fmt:
            dt = dt.replace(year=now.year)
            if dt.replace(tzinfo=HKT) < now - timedelta(days=1):
                dt = dt.replace(year=now.year + 1)
        return dt.replace(tzinfo=HKT)  # ASSUMPTION: page shows HKT local time
    return None


def has_usage_signal(text: str) -> bool:
    if any(p.search(text) for p in USED_PATTERNS + REMAINING_PATTERNS):
        return True
    if SECTION_ANCHOR.search(text) and any(BARE_PCT_LINE.match(l) for l in text.splitlines()):
        return True
    return False


def looks_logged_out(text: str) -> bool:
    if has_usage_signal(text):
        return False
    return bool(LOGIN_MARKERS.search(text))


# ---------------------------------------------------------------- browser (headless, profile)
def read_page_text(url: str, profile: Path, timeout: int = 45) -> str:
    """Headless Chrome on heiman's profile via --remote-debugging-pipe (no TCP port).
    Returns document.body.innerText only. Never logged, never written to disk."""
    from cdp_pipe import Chrome
    with Chrome(user_data_dir=str(profile)) as c:
        sid = c.open(url)
        return c.wait_text(sid, lambda t: has_usage_signal(t) or bool(LOGIN_MARKERS.search(t)), timeout)


# ---------------------------------------------------------------- main
def build_row(used, reset, now, source="script"):
    return {"service": "grok", "name": "Grok 共用池", "used_pct": round(float(used), 1),
            "reset_at": iso(reset), "updated_at": iso(now), "source": source}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fake", action="store_true", help="write demo data, no browser")
    ap.add_argument("--fake-pct", type=float, default=54.7, help="used %% for --fake (default 54.7)")
    ap.add_argument("--dry-run", action="store_true", help="print the row, do not write usage.json")
    ap.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    ap.add_argument("--url", default=os.environ.get("GROK_USAGE_URL", DEFAULT_URL))
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z")
    now = now_hkt()

    if a.fake:
        row = build_row(a.fake_pct, now + timedelta(days=1, hours=13, minutes=44), now)
        log.info("FAKE mode: demo row used=%s%% reset=%s (usage.json gets \"demo\": true)", row["used_pct"], row["reset_at"])
        if a.dry_run:
            print(row); return 0
        merge_row(str(a.out), row, demo=True)
        log.info("wrote %s", a.out)
        return 0

    if not a.profile.is_dir():
        log.error("profile missing: %s -> heiman must log in first (see README). Nothing written.", a.profile)
        return 2
    try:
        text = read_page_text(a.url, a.profile)
    except Exception as e:  # noqa: BLE001
        log.error("browser step failed: %s. Nothing written.", e)
        return 5
    if looks_logged_out(text):
        log.error("page looks logged out (login prompt, no percentage). Nothing written.")
        return 3
    try:
        used, reset = parse_usage_text(text, now)
    except ValueError as e:
        log.error("parse failed: %s (page layout / URL unverified, fix parser block). Nothing written.", e)
        return 4
    row = build_row(used, reset, now)
    log.info("parsed used=%s%% reset=%s", row["used_pct"], row["reset_at"])
    if a.dry_run:
        print(row); return 0
    merge_row(str(a.out), row, demo=False)
    log.info("wrote %s", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
