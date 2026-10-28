"""Minimal stdlib Chrome DevTools client over --remote-debugging-pipe (no TCP port opened).

Only the commands below are used: open a tab, read document.body.innerText, screenshot.
No Network/Storage/cookie domains are ever called.
"""
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time

ALLOWED_METHODS = {"Target.createTarget", "Target.attachToTarget", "Runtime.evaluate",
                   "Emulation.setDeviceMetricsOverride", "Page.captureScreenshot", "Browser.close"}
# Only this expression is ever evaluated in the page: rendered visible text.
INNER_TEXT_EXPR = "document.body ? document.body.innerText : ''"


def find_chrome():
    # Prefer the real binary: the /usr/bin/google-chrome bash wrapper re-plumbs stdio and
    # breaks --remote-debugging-pipe on this box.
    for c in ("/opt/google/chrome/chrome",):
        if os.access(c, os.X_OK):
            return c
    for c in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        p = shutil.which(c)
        if p:
            return p
    raise RuntimeError("no Chrome/Chromium found")


class Chrome:
    def __init__(self, user_data_dir=None, headless=True, extra_args=()):
        self._tmp = None
        if user_data_dir is None:
            self._tmp = tempfile.mkdtemp(prefix="cdp-")
            user_data_dir = self._tmp
        r_child, self._w = os.pipe()   # we write -> chrome fd 3
        self._r, w_child = os.pipe()   # chrome fd 4 -> we read
        args = [find_chrome(), "--remote-debugging-pipe", f"--user-data-dir={user_data_dir}",
                "--no-first-run", "--no-default-browser-check", "--disable-gpu", "--no-sandbox", *extra_args]
        if headless:
            args.insert(1, "--headless=new")
        args.append("about:blank")

        # move child ends above fd 10 so the redirections below can't clobber fds 3/4
        import fcntl
        hi_r, hi_w = fcntl.fcntl(r_child, fcntl.F_DUPFD, 10), fcntl.fcntl(w_child, fcntl.F_DUPFD, 10)
        os.close(r_child); os.close(w_child); r_child, w_child = hi_r, hi_w
        # Chrome expects the pipe on fds 3 (in) and 4 (out); let bash place them, then exec chrome.
        wrapper = ["bash", "-c", f'exec "$@" 3<&{r_child} 4>&{w_child} {r_child}<&- {w_child}>&-', "sh", *args]
        self.proc = subprocess.Popen(wrapper, pass_fds=(r_child, w_child),
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        os.close(r_child); os.close(w_child)
        self._id, self._buf = 0, b""

    def _send(self, method, params=None, session=None, timeout=30):
        if method not in ALLOWED_METHODS:
            raise ValueError(f"CDP method not allowed: {method}")
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        os.write(self._w, json.dumps(msg).encode() + b"\0")
        end = time.time() + timeout
        while time.time() < end:
            while b"\0" in self._buf:
                raw, self._buf = self._buf.split(b"\0", 1)
                m = json.loads(raw)
                if m.get("id") == self._id:
                    if "error" in m:
                        raise RuntimeError(f"{method}: {m['error'].get('message')}")
                    return m.get("result", {})
            if self.proc.poll() is not None:
                err = (self.proc.stderr.read() or b"").decode(errors="replace")
                hint = "profile in use? close the login window first" if "ProcessSingleton" in err or "SingletonLock" in err else f"exit {self.proc.returncode}"
                raise RuntimeError(f"chrome exited ({hint})")
            import select
            if select.select([self._r], [], [], 0.5)[0]:
                chunk = os.read(self._r, 1 << 20)
                if chunk:
                    self._buf += chunk
        raise TimeoutError(method)

    def open(self, url, width=None, height=None, scale=1, mobile=False):
        tid = self._send("Target.createTarget", {"url": "about:blank"})["targetId"]
        sid = self._send("Target.attachToTarget", {"targetId": tid, "flatten": True})["sessionId"]
        if width:
            self._send("Emulation.setDeviceMetricsOverride",
                       {"width": width, "height": height, "deviceScaleFactor": scale, "mobile": mobile}, sid)
        self._send("Runtime.evaluate", {"expression": f"location.href = {json.dumps(url)}"}, sid)
        return sid

    def inner_text(self, sid):
        r = self._send("Runtime.evaluate", {"expression": INNER_TEXT_EXPR, "returnByValue": True}, sid)
        return r.get("result", {}).get("value") or ""

    def wait_text(self, sid, predicate, timeout=30):
        end, text = time.time() + timeout, ""
        while time.time() < end:
            try:
                text = self.inner_text(sid)
            except RuntimeError:
                text = ""  # navigation in progress
            if predicate(text):
                return text
            time.sleep(1)
        return text

    def screenshot(self, sid, path):
        data = self._send("Page.captureScreenshot", {"format": "png"}, sid)["data"]
        with open(path, "wb") as f:
            f.write(base64.b64decode(data))

    def close(self):
        try:
            self._send("Browser.close", timeout=5)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        for fd in (self._r, self._w):
            try: os.close(fd)
            except OSError: pass
        if self._tmp:
            shutil.rmtree(self._tmp, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
