#!/usr/bin/env python3
"""Screenshot index.html at iPhone size (390x844 @2x). Needs the page served over http.
Usage: python3 preview.py [url] [out.png] [height]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp_pipe import Chrome

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/index.html"
out = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).resolve().parent / "preview.png")
h = int(sys.argv[3]) if len(sys.argv) > 3 else 844
with Chrome() as c:  # throwaway temp profile, never heiman's
    sid = c.open(url, 390, h, 2, True)
    c.wait_text(sid, lambda t: "更新" in t or "讀唔到" in t, 20)
    c.screenshot(sid, out)
print("saved", out)
