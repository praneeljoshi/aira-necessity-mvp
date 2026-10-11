"""Drive the coordinator review page in headless Chrome over the DevTools protocol, against a stub dev server you
start here, and save screenshots of every step. Pure Python: stdlib + websocket-client (in .venv).

    .venv/bin/python -m scripts.verify_review --out DIR [--port 8020] [--port2 8021] [--port3 8022] [--cdp 9240]
                                              [--delay 0.3] [--skip-two-codes] [--skip-samples] [--keep]

Three stub servers, each on its own scratch --data dir: --port for the flow (fresh), --port2 with --two-codes
(fresh), --port3 seeded with read-only copies of four stored sample results (data/results, data/charts,
data/criteria, data/guidelines; data/ itself is never written). The samples are kept apart because the stored
criteria cache shares its key with what the stub's upload computes, and the stub must not be served the real model's
narrowing.

Steps (each printed, each screenshot path printed):
  1. start `scripts.dev_server --port PORT --delay DELAY --data DIR` (fresh);
  2. start Chrome headless with remote debugging on --cdp, open /review: the sign-in screen comes first (the product's
     name, "Your name", Continue; no password); type the name and press Enter (every later page load on a new
     server signs in the same way); screenshot;
  3. click "Add a case" (#addBtn), set the case input (#dropFiles, DOM.setFileInputFiles), the guideline
     select (#dlgGl) keeps its first choice, click #dlgGo; wait for the gate (#confirmBtn); screenshot;
  4. click #confirmBtn; wait for the case: the guideline (.gl .ln[data-id]) with the requirements marked in place
     (mark.q[data-crit]) and the chart's evidence under each block (.ev .evq[data-span], .ev .none); screenshot;
     click a mark.q to select that requirement (.sel on its marks and its quotes); screenshot;
  4b. the tree view: t switches the middle column to the outline (?view=tree, remembered, nothing for the
     highlighter to draw), a leaf opens the same panel with the navigator in sync, ArrowDown follows tree order,
     Ctrl+Enter accepts from the tree and both views update, a ?view=tree#<requirement> link opens there, t again
     brings the guideline back with its highlights; the accept is undone so the later steps start clean;
  5. click a guideline line, shift-click a few lines below, file should_be_requirement / not_a_requirement /
     logic_wrong / edit through #fbBar, #fbText, #fbProposal, #fbSend; a "mid-feedback" screenshot with the bar
     open and the text typed before sending; screenshot after each;
  6. click an evidence quote (.evq), file wrong_evidence and evidence_elsewhere (stored side chart, spans = the
     quote's lines, requirements = its criterion); screenshot; remove one chip (.fb-chip .rm);
  6b. sign-off and strike on the first chart (ready): the verdict reads "Evidence found for all N requirements. Accept each to sign off." until
     every requirement is accepted, then "Ready for sign-off.", the rail lists it under
     "Ready for sign-off", the packet button only previews a draft; "Not needed for this case" on a documented
     requirement, "Remove for this case" with no reason is refused on the page, with a reason the requirement is
     struck through in place with who and why, the sign-off panel lists it, the server has strikes.json and a
     not_a_requirement feedback item carrying the strike id; sign off with a typed name (#signName, #signBtn): the
     verdict reads "Ready to submit.", the rail moves it under "Signed off", the packet copies with the signer's
     line; "Put it back": the strike is undone, the sign-off no longer counts (the case changed), back to "Ready for
     sign-off"; the visible text outside the fold and the guideline's / chart's own words is checked for the
     internals' words (criterion, verdict, confidence, pathway, span); screenshot after each;
  6b'. (this round) the case is three columns: the navigator (↑/↓, j/k), the guideline (never moves) and the side
     panel; sign-off stays held back until every requirement is accepted (Ctrl+Enter from the keyboard) or struck;
     Undo takes an accept back; the summary fills ("5 of 5 accepted · 1 struck"); the packet copies from accepted items
  6c. highlight to ask on the first chart (answers open in the side panel; the live stroke is checked mid-drag): a mouse drag over a requirement line snaps to whole lines and the card
     reads the stored answer ("Already on this case's checklist", no model call); Esc closes it; a drag over "the
     varicosities … AND one or more of the following: 1. …; 2. …; 3. …" shows the logic as a small checklist with
     "One of these:" and the other option; click a set-aside line, shift + ArrowDown three times, Enter: the card
     reads "Checking the case…" then the stubbed answer with "Add to this case's checklist"; add it: the case is
     still ready, the sign-off panel lists the addition, the card says who added it; sign off, then "Take it off"
     withdraws the sign-off; in "The rest of the guideline" a drag over the billing heading reads "This isn't
     something the chart can show" and says where the lines come from; the asked lines carry the margin mark
     (.ln.probed) and the server has probes.json, additions.json and a should_be_requirement feedback item;
     screenshot after each;
  6e. edge states on a slow stub server (--port4) that fails at step I with a second guideline on file: the upload
     progress as calm lines, the failed check with Retry, "None of these" -> "This guideline doesn't apply" with the
     other guideline offered and re-checked;
  6d. deliverables: desktop light and desktop dark with a requirement open, a phone (the panel is a bottom sheet),
     ?style=classic and the switcher back to Marker (remembered in localStorage);
  7. second chart: upload again, at the gate uncheck the suggested section and check another, confirm; screenshot;
     the case is not ready: no sign-off control; strike one of its missing requirements: the ask lists one fewer;
  8. a second server with --two-codes on --port2: upload, gate with two picks, confirm; screenshots;
  9. the seeded server on --port3: /review/<id> for each stored sample, screenshot.
There is no chart column: the case page is the guideline, the chart appears only as evidence quotes.
Every real action is a mouse event at the element's box centre or typed text. If an element never appears the run
fails loudly with the page's console errors. Chrome and the servers are stopped in a finally block. Ports
8000-8003/8010/8025 belong to other people; the defaults here are 8020/8021/8022/8024/9240.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import websocket

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SAMPLES = DATA / "samples"
CHART_PDF = SAMPLES / "synthetic" / "maria_delgado_chart.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
STORED = ["maria_delgado_chart", "linda_park_chart", "robert_mitchell_chart_final", "james_okafor_chart"]
FORBIDDEN_PORTS = {8000, 8001, 8002, 8003, 8010, 8025}
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable


class StepFailed(Exception):
    pass


def say(msg: str) -> None:
    print(f"[verify] {msg}", flush=True)


# ---------------------------------------------------------------- Chrome over CDP


class Page:
    """One tab. `send` is synchronous; events are collected as they arrive (console messages, log entries)."""

    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True)
        self.ws.settimeout(30)
        self.n = 0
        self.console: list[str] = []
        self.events: list[dict] = []
        self.signin_as: str | None = "Dana"     # each server is a new origin: sign in through the page's own screen
        for d in ("Page", "Runtime", "DOM", "Log"):
            self.send(f"{d}.enable")
        self.scheme("light")

    def scheme(self, which: str) -> None:
        """Light or dark: the page's own switch (data-theme, remembered as review.theme; light is the default whatever
        the system says) and prefers-color-scheme for anything that still follows the system."""
        self.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": which}])
        try:
            self.ev(f"""(() => {{ try {{ localStorage.setItem('review.theme', '{which}'); }} catch (e) {{}}
                document.documentElement.dataset.theme = '{which}'; if (window.ReviewMarks) ReviewMarks.restyle(); return 1; }})()""")
        except StepFailed:
            pass

    def _handle(self, msg: dict) -> None:
        m = msg.get("method", "")
        self.events.append(msg)
        p = msg.get("params", {})
        if m == "Runtime.consoleAPICalled" and p.get("type") in ("error", "warning", "assert"):
            args = " ".join(str(a.get("value", a.get("description", ""))) for a in p.get("args", []))
            self.console.append(f"console.{p['type']}: {args}")
        elif m == "Runtime.exceptionThrown":
            d = p.get("exceptionDetails", {})
            self.console.append("exception: " + (d.get("exception", {}).get("description") or d.get("text", "")))
        elif m == "Log.entryAdded" and p.get("entry", {}).get("level") in ("error", "warning"):
            e = p["entry"]
            self.console.append(f"{e['source']} {e['level']}: {e.get('text', '')} {e.get('url', '')}")

    def send(self, method: str, **params):
        self.n += 1
        my = self.n
        self.ws.send(json.dumps({"id": my, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == my:
                if "error" in msg:
                    raise StepFailed(f"{method}: {msg['error']}")
                return msg.get("result", {})
            self._handle(msg)

    def pump(self, seconds: float) -> None:
        """Let events arrive for a while."""
        end = time.time() + seconds
        self.ws.settimeout(0.05)
        try:
            while time.time() < end:
                try:
                    self._handle(json.loads(self.ws.recv()))
                except websocket.WebSocketTimeoutException:
                    time.sleep(0.02)
        finally:
            self.ws.settimeout(30)

    def ev(self, expr: str):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            raise StepFailed("evaluate failed: " + (d.get("exception", {}).get("description") or d.get("text", "")) + f"\n  in: {expr[:200]}")
        return r.get("result", {}).get("value")

    def goto(self, url: str) -> None:
        self.send("Page.navigate", url=url)
        self.wait_js("document.readyState === 'complete'", 20, f"page load {url}")
        self.pump(0.3)
        if self.signin_as and self.ev("document.documentElement.classList.contains('signin')"):
            self.sign_in(self.signin_as)

    def sign_in(self, name: str) -> None:
        """The sign-in screen: type the name into "Your name" and press Enter, as a person would."""
        self.wait_for("#signinName", 10)
        self.type_into("#signinName", name)
        self.enter()
        self.wait_js("!document.documentElement.classList.contains('signin')", 10, "the sign-in screen to close")
        self.pump(0.2)

    def wait_js(self, cond: str, timeout: float, what: str):
        end = time.time() + timeout
        while time.time() < end:
            v = self.ev(f"(() => {{ try {{ return !!({cond}); }} catch (e) {{ return false; }} }})()")
            if v:
                return True
            self.pump(0.2)
        self.fail(f"timed out after {timeout:.0f}s waiting for {what}")

    def wait_for(self, selector: str, timeout: float = 60, visible: bool = True) -> None:
        cond = f"document.querySelector({json.dumps(selector)})"
        if visible:
            cond = f"(el => el && el.getClientRects().length > 0)(document.querySelector({json.dumps(selector)}))"
        self.wait_js(cond, timeout, f"element {selector}")

    def count(self, selector: str) -> int:
        return int(self.ev(f"document.querySelectorAll({json.dumps(selector)}).length") or 0)

    def text(self, selector: str) -> str:
        return self.ev(f"(document.querySelector({json.dumps(selector)}) || {{}}).textContent || ''") or ""

    def fail(self, why: str):
        url = self.ev("location.href")
        state = self.ev("(() => { try { return JSON.stringify((window.Review && Review.state && Review.state()) || null).slice(0, 600); } catch (e) { return 'n/a'; } })()")
        body = (self.ev("document.body ? document.body.innerText.slice(0, 1200) : ''") or "").strip()
        lines = [f"FAILED: {why}", f"  url: {url}", f"  Review.state(): {state}", "  console:"]
        lines += [f"    {c}" for c in self.console[-25:]] or ["    (no console errors)"]
        lines += ["  page text:", "    " + body.replace("\n", "\n    ")]
        raise StepFailed("\n".join(lines))

    def rect(self, selector: str, index: int = 0) -> dict:
        js = f"""(() => {{
            const els = document.querySelectorAll({json.dumps(selector)});
            const el = els[{index}];
            if (!el) return null;
            el.scrollIntoView({{block: 'center', inline: 'nearest'}});
            const r = el.getBoundingClientRect();
            return {{x: r.x, y: r.y, w: r.width, h: r.height}};
        }})()"""
        r = self.ev(js)
        if not r:
            self.fail(f"no element {selector}[{index}] to click")
        if r["w"] == 0 or r["h"] == 0:
            self.fail(f"element {selector}[{index}] has no box (hidden?)")
        return r

    def click(self, selector: str, index: int = 0, shift: bool = False) -> None:
        r = self.rect(selector, index)
        self.pump(0.1)
        r = self.rect(selector, index)                   # after the scroll settled
        x, y = r["x"] + r["w"] / 2, r["y"] + min(r["h"] / 2, 400)
        mods = 8 if shift else 0
        self.send("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, modifiers=mods)
        self.send("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1, modifiers=mods)
        self.send("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1, modifiers=mods)
        self.pump(0.25)

    def click_text(self, selector: str, shift: bool = False) -> None:
        """A real click on the first visual line of the element's text (an inline line that wraps has a bounding box
        whose centre can sit on another line)."""
        self.ev(f"document.querySelector({json.dumps(selector)}).scrollIntoView({{block: 'center'}})")
        self.pump(0.1)
        r = self.ev(f"""(() => {{ const el = document.querySelector({json.dumps(selector)}); if (!el) return null;
            const rg = document.createRange(); rg.selectNodeContents(el); const q = [...rg.getClientRects()].find(x => x.width > 4);
            return q ? {{x: q.left + Math.min(q.width / 2, 40), y: q.top + q.height / 2}} : null; }})()""")
        if not r:
            self.fail(f"no text to click in {selector}")
        mods = 8 if shift else 0
        for t in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.send("Input.dispatchMouseEvent", type=t, x=r["x"], y=r["y"], modifiers=mods,
                      **({} if t == "mouseMoved" else {"button": "left", "clickCount": 1}))
        self.pump(0.25)

    def drag(self, a: str, b: str, before_release=None):
        """Press at the start of the text of `a`, move in steps, release at the end of the text of `b`: a real
        mouse selection over the lines between."""
        js = lambda sel, end: f"""(() => {{ const el = document.querySelector({json.dumps(sel)}); if (!el) return null;
            const t = el.querySelector('.tx') || el; const rg = document.createRange(); rg.selectNodeContents(t);
            const rs = rg.getClientRects(); const r = rs[{'rs.length - 1' if end else '0'}] || t.getBoundingClientRect();
            return {{x: {'r.right - 2' if end else 'r.left + 1'}, y: r.top + r.height / 2}}; }})()"""
        self.ev(f"document.querySelector({json.dumps(a)}).scrollIntoView({{block: 'center'}})")
        self.pump(0.15)
        p, q = self.ev(js(a, False)), self.ev(js(b, True))
        if not p or not q:
            self.fail(f"no lines {a} / {b} to drag over")
        self.send("Input.dispatchMouseEvent", type="mouseMoved", x=p["x"], y=p["y"])
        self.send("Input.dispatchMouseEvent", type="mousePressed", x=p["x"], y=p["y"], button="left", clickCount=1)
        for i in range(1, 9):
            self.send("Input.dispatchMouseEvent", type="mouseMoved", x=p["x"] + (q["x"] - p["x"]) * i / 8,
                      y=p["y"] + (q["y"] - p["y"]) * i / 8, button="left", buttons=1)
        self.pump(0.1)
        got = before_release() if before_release else None
        self.send("Input.dispatchMouseEvent", type="mouseReleased", x=q["x"], y=q["y"], button="left", clickCount=1)
        self.pump(0.1)
        return got

    def key(self, key: str, shift: bool = False) -> None:
        codes = {"ArrowDown": 40, "ArrowUp": 38, "Enter": 13, "Escape": 27}
        for t in ("rawKeyDown", "keyUp"):
            self.send("Input.dispatchKeyEvent", type=t, key=key, code=key, windowsVirtualKeyCode=codes[key],
                      modifiers=8 if shift else 0)
        self.pump(0.15)

    def enter(self) -> None:
        """Enter as a keyboard types it (keyDown with its "\\r" text), so a form submits as it would for a person."""
        self.send("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, text="\r", unmodifiedText="\r")
        self.send("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)
        self.pump(0.15)

    def type_into(self, selector: str, text: str) -> None:
        self.wait_for(selector, 10)
        self.ev(f"(() => {{ const el = document.querySelector({json.dumps(selector)}); el.focus(); el.select && el.select(); }})()")
        self.send("Input.insertText", text=text)
        self.pump(0.1)
        got = self.ev(f"document.querySelector({json.dumps(selector)}).value")
        if text not in (got or ""):
            self.fail(f"typing into {selector} left value {got!r}")

    def set_file(self, selector: str, path: Path) -> None:
        root = self.send("DOM.getDocument", depth=1)["root"]["nodeId"]
        node = self.send("DOM.querySelector", nodeId=root, selector=selector).get("nodeId")
        if not node:
            self.fail(f"no file input {selector}")
        self.send("DOM.setFileInputFiles", files=[str(path)], nodeId=node)
        self.pump(0.3)

    def screenshot(self, path: Path) -> Path:
        m = self.send("Page.getLayoutMetrics")
        size = m.get("cssContentSize") or m.get("contentSize")
        height = int(min(max(size["height"], 1000), 8000))
        self.send("Emulation.setDeviceMetricsOverride", width=1440, height=height, deviceScaleFactor=1, mobile=False)
        self.pump(0.2)
        data = self.send("Page.captureScreenshot", format="png", captureBeyondViewport=True)["data"]
        self.send("Emulation.clearDeviceMetricsOverride")
        path.write_bytes(base64.b64decode(data))
        say(f"  screenshot -> {path}")
        return path


    def screenshot_around(self, selector: str, path: Path, pad: int = 220) -> Path:
        """The element and some of the page around it, at 1440 wide: what a person sees of the card."""
        r = self.ev(f"""(() => {{ const el = document.querySelector({json.dumps(selector)}); if (!el) return null;
            const b = el.getBoundingClientRect(); return {{y: b.top + window.scrollY, h: b.height}}; }})()""")
        if not r:
            return self.screenshot(path)
        data = self.send("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                         clip={"x": 0, "y": max(0, r["y"] - pad), "width": 1440, "height": r["h"] + 2 * pad, "scale": 1})["data"]
        path.write_bytes(base64.b64decode(data))
        say(f"  screenshot -> {path}")
        return path


def http(url: str, method: str = "GET", timeout: float = 5):
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "null")


def wait_http(url: str, timeout: float, what: str):
    end = time.time() + timeout
    err = None
    while time.time() < end:
        try:
            return http(url)
        except Exception as e:      # noqa: BLE001
            err = e
            time.sleep(0.2)
    raise StepFailed(f"{what} did not come up at {url}: {err}")


def start_chrome(cdp_port: int, profile: Path) -> subprocess.Popen:
    if not Path(CHROME).exists():
        raise StepFailed(f"Chrome not found at {CHROME}")
    p = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={cdp_port}", "--window-size=1440,1000",
                          f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check", "--use-angle=swiftshader",
                          "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist",
                          "--hide-scrollbars", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait_http(f"http://127.0.0.1:{cdp_port}/json/version", 20, "Chrome")
    return p


def new_tab(cdp_port: int) -> Page:
    t = http(f"http://127.0.0.1:{cdp_port}/json/new?about:blank", method="PUT")
    return Page(t["webSocketDebuggerUrl"])


def start_server(port: int, data: Path, delay: float, extra: list[str], log: Path) -> subprocess.Popen:
    if port in FORBIDDEN_PORTS:
        raise StepFailed(f"port {port} belongs to someone else")
    cmd = [PY, "-m", "scripts.dev_server", "--port", str(port), "--delay", str(delay), "--data", str(data)] + extra
    say("starting " + " ".join(cmd))
    f = open(log, "w")
    p = subprocess.Popen(cmd, cwd=str(ROOT), stdout=f, stderr=subprocess.STDOUT)
    try:
        wait_http(f"http://127.0.0.1:{port}/api/health", 40, f"dev server on {port}")
    except StepFailed:
        p.kill()
        raise StepFailed(f"dev server on {port} did not start; log:\n{log.read_text()[-3000:]}")
    return p


def seed(data: Path) -> list[str]:
    """Read-only copies of the stored sample results into the dev server's data dir. data/ is never written."""
    present = []
    for name in ("criteria", "guidelines"):
        src = DATA / name
        if src.exists():
            shutil.copytree(src, data / name, dirs_exist_ok=True)
    for cid in STORED:
        r, c = DATA / "results" / cid, DATA / "charts" / cid
        if (r / "result.json").exists() and c.exists():
            shutil.copytree(r, data / "results" / cid, dirs_exist_ok=True)
            shutil.copytree(c, data / "charts" / cid, dirs_exist_ok=True)
            present.append(cid)
        else:
            say(f"  stored sample {cid} not on disk; skipped")
    return present


def stop(p: subprocess.Popen | None, what: str) -> None:
    if p is None or p.poll() is not None:
        return
    try:
        p.send_signal(signal.SIGTERM)
        p.wait(timeout=8)
    except Exception:       # noqa: BLE001
        p.kill()
    say(f"stopped {what}")


# ---------------------------------------------------------------- the flow


class Run:
    def __init__(self, out: Path):
        self.out = out
        self.shot = 0
        self.problems: list[str] = []

    def snap(self, pg: Page, name: str) -> None:
        self.shot += 1
        pg.screenshot(self.out / f"{self.shot:02d}-{name}.png")

    def snap_card(self, pg: Page, name: str) -> None:
        self.shot += 1
        pg.screenshot_around(".ask-card", self.out / f"{self.shot:02d}-{name}.png")

    def problem(self, msg: str) -> None:
        self.problems.append(msg)
        say(f"  PROBLEM: {msg}")

    def upload(self, pg: Page, base: str) -> str:
        """Signed in (goto signs in through the sign-in screen when no name is remembered), open the dialog, set the
        chart, pick the guideline on file, go; wait for the gate. Returns the chart id."""
        pg.goto(f"{base}/review")
        pg.wait_for("#addBtn", 20)
        say("click #addBtn (Add a case)")
        pg.click("#addBtn")
        pg.wait_for("#dropFiles", 10, visible=False)
        say(f"drop zone (#dropFiles) <- {CHART_PDF.name}")
        pg.set_file("#dropFiles", CHART_PDF)
        got = pg.text("#dropGot")
        if "Case: " + CHART_PDF.name not in got:
            self.problem(f"the drop zone did not take the chart: {got!r}")
        if not getattr(self, "dropped", False):
            self.dropped = True
            self.snap_card_el(pg, "upload-drop", "#addDlg .dlg-card")
        pg.wait_for("#dlgGl option", 10, visible=False)
        pg.wait_js("!document.querySelector('#dlgGo').disabled", 10, "#dlgGo to be enabled")
        say("click #dlgGo")
        pg.click("#dlgGo")
        pg.wait_js("/\\/review\\/[0-9a-f]{6,}/.test(location.pathname)", 30, "navigation to /review/<id>")
        cid = pg.ev("location.pathname.split('/').pop()")
        say(f"chart {cid}: waiting for the gate (#confirmBtn)")
        pg.wait_for("#confirmBtn", 90)
        pg.pump(0.4)
        return cid

    def wait_case(self, pg: Page) -> None:
        """The finished case: the guideline lines, at least one requirement marked in place, the navigator and the
        side panel (the packet, until a requirement is opened)."""
        pg.wait_for(".gl .ln[data-id]", 90)
        pg.wait_for("mark.q[data-crit]", 30)
        pg.wait_for(".rq-nav .nv[data-crit]", 30)
        pg.wait_for("#side .pk-panel, #side .sp-req", 30)
        pg.pump(0.5)

    def describe_case(self, pg: Page) -> dict:
        d = {"lines": pg.count(".gl .ln[data-id]:not(.rest)"), "marks": pg.count("mark.q[data-crit]"),
             "criteria": len(set(pg.ev("[...document.querySelectorAll('mark.q[data-crit]')].map(m => m.dataset.crit)") or [])),
             "nav": pg.count(".rq-nav .nv[data-crit]"), "ticks": pg.count("#prog .ticks i"),
             "summary": (pg.ev("(document.querySelector('#prog .ticks') || {}).title || ''") or "").strip()}
        say(f"  {d['lines']} guideline lines, {d['marks']} marks on {d['criteria']} requirements, {d['nav']} in the navigator; "
            f"summary {d['summary']!r}")
        return d

    def open_req(self, pg: Page, crit: str) -> None:
        pg.click(f'.rq-nav .nv[data-crit="{crit}"]')
        pg.wait_js(f"document.querySelector('#side .sp-req') && Review.state() && document.querySelector('.nv[aria-current][data-crit=\"{crit}\"]')", 10, f"the panel for {crit}")
        pg.pump(0.2)

    def bar_open(self, pg: Page) -> bool:
        return bool(pg.ev("(el => el && el.getClientRects().length > 0)(document.querySelector('#fbBar'))"))

    def select_lines(self, pg: Page) -> tuple[str, str]:
        """Click a guideline line that is not a requirement (it opens the report bar), shift-click one three below."""
        a, b = pg.ev("""(() => {
            const all = [...document.querySelectorAll('.gl .ln[data-id]:not(.rest)')].filter(l => !l.closest('details:not([open])'));
            const i = all.findIndex(l => !l.querySelector('mark.q') && !l.classList.contains('heading') && l.textContent.trim().length > 20);
            return [all[i].dataset.id, all[Math.min(i + 3, all.length - 1)].dataset.id];
        })()""")
        say(f"click guideline line {a}, shift-click {b}")
        pg.click_text(f'.gl .ln[data-id="{a}"] .tx')
        pg.click_text(f'.gl .ln[data-id="{b}"] .tx', shift=True)
        pg.wait_for("#fbBar", 10)
        n_sel = pg.count(".gl .ln.fb-sel")
        say(f"  {n_sel} line(s) selected (.fb-sel)")
        if n_sel < 2:
            self.problem(f"click + shift-click selected {n_sel} guideline line(s), expected a range")
        return a, b

    def file_feedback(self, pg: Page, kind: str, text: str, proposal: str | None = None, mid: str | None = None) -> None:
        pg.wait_for(f"#fbBar [data-kind={kind}]", 10)
        say(f"feedback {kind}: click the kind button, type, send")
        pg.click(f"#fbBar [data-kind={kind}]")
        n0 = pg.count("#fbList .it[data-fid]")
        pg.type_into("#fbText", text)
        if proposal is not None:
            pg.wait_for("#fbProposal", 10)
            pg.type_into("#fbProposal", proposal)
        if mid:
            self.snap(pg, mid)
        pg.click("#fbSend")
        pg.wait_js(f"document.querySelectorAll('#fbList .it[data-fid]').length > {n0}", 15, f"a new feedback item after {kind}")
        pg.pump(0.3)

    def click_quote(self, pg: Page, crit: str) -> dict:
        """Open a requirement and click its first chart quote in the side panel; the report bar opens on it."""
        if not pg.count(f'#side .evq[data-crit="{crit}"]'):
            self.open_req(pg, crit)
        q = pg.ev(f"""(() => {{ const e = document.querySelector('#side .evq[data-span][data-crit="{crit}"]'); if (!e) return null;
            return {{span: e.dataset.span, lines: (e.dataset.lines || '').split(/\\s+/).filter(Boolean), crit: e.dataset.crit, side: e.dataset.side}}; }})()""")
        if not q:
            pg.fail(f"no chart quote in the side panel for {crit}")
        say(f"click evidence quote {q['span']} ({q['side']}, requirement {q['crit']}) in the side panel")
        pg.click(f'#side .evq[data-span][data-crit="{crit}"] q')
        pg.wait_for("#fbBar [data-kind=wrong_evidence]", 10)
        if not pg.count("#side .evq.fb-sel"):
            self.problem("clicking the evidence quote did not mark it .fb-sel")
        return q

    def flow(self, pg: Page, base: str) -> str:
        # a new browser: the sign-in screen comes first (the product's name, "Your name", Continue; nothing else)
        keep, pg.signin_as = pg.signin_as, None
        pg.goto(f"{base}/review")
        pg.signin_as = keep
        pg.wait_for("#signinName", 10)
        words = " ".join(pg.ev("document.querySelector('#signin').innerText").split())
        say(f"sign-in screen: {words!r}")
        if not words.startswith("Prior auth Your name Continue") or pg.ev("getComputedStyle(document.querySelector('.app')).display") != "none":
            self.problem(f"the sign-in screen reads {words!r} or shows the page behind it")
        if any(w in words.lower() for w in ("password", "secur", "log in", "account")):
            self.problem(f"the sign-in screen mentions more than a name: {words!r}")
        self.snap(pg, "signin")
        pg.sign_in(pg.signin_as or "Dana")
        if pg.ev("localStorage.getItem('review.name')") != "Dana":
            self.problem("signing in did not remember the name as review.name")
        cid = self.upload(pg, base)
        # the gate: one card for the selected indication (Suggested first), two more as rows, the rest folded
        card = pg.ev("(document.querySelector('.gcard.g1') || {dataset: {}}).dataset.pathway")
        rows = pg.ev("[...document.querySelectorAll('.g-row')].map(r => r.dataset.pathway)")
        more = pg.text("#gcMore") if pg.count("#gcMore") else ""
        say(f"gate: card {card}, rows {rows}, {more!r}")
        if card != "gsv" or len(rows) != 2 or more != "Show 1 more indication":
            self.problem(f"gate: card {card}, rows {rows}, more {more!r}; expected gsv, two rows and 'Show 1 more indication'")
        why = pg.count('.gcard.g1 .gc-q q')
        if why != 1 or not pg.count('.gcard.g1 .chip.for') or not pg.count('.gcard.g1 .gc-src'):
            self.problem("the suggested indication lacks its 'Suggested' mark, its source line or its one evidence line")
        clutter = pg.ev("(() => { const t = document.querySelector('.gate-page').innerText; return ['Suggested:', 'The order, as the chart gives it', 'Sections of the guideline', 'Why it might fit', 'Shares code', 'Compare', 'Codes ', 'Treats '].filter(w => t.includes(w)); })()")
        cpt_quotes = pg.ev("[...document.querySelectorAll('.gc-q q')].filter(q => /CPT/.test(q.textContent) && !/saphenous/i.test(q.textContent)).length")
        btn = pg.text("#confirmBtn")
        say(f"  clutter {clutter}, code-only quotes {cpt_quotes}, button {btn!r}, sticky bar {pg.count('.gate-bar')}")
        if clutter or cpt_quotes or "Great or Small Saphenous Veins" not in btn or pg.count(".gate-bar"):
            self.problem(f"gate: clutter {clutter}, code-only quotes {cpt_quotes}, button {btn!r}")
        self.snap(pg, "gate")
        self.vocab(pg, "gate")
        pg.click("#gcMore")
        n_all = pg.count(".g-row")
        pg.key("Escape")
        if n_all != 3 or pg.count(".g-row") != 2:
            self.problem(f"'Show 1 more indication' shows {n_all} rows, Esc leaves {pg.count('.g-row')}")
        # a row picked becomes the card; the warm line only where the order's code is not listed
        pg.click('.g-row[data-pathway="tributaries"]') if pg.count('.g-row[data-pathway="tributaries"]') else None
        warn = pg.ev("[...document.querySelectorAll('.gcard.g1 .gc-warn')].map(x => x.textContent)")
        if pg.ev("document.querySelector('.gcard.g1').dataset.pathway") == "tributaries" and warn != ["This indication doesn't list 36475."]:
            self.problem(f"the tributaries card should say it doesn't list 36475: {warn}")
        # the keyboard: ↑ back through the ranked list to the suggestion, ↓ one on, ↑ again; ⌘/Ctrl+Enter confirms
        for _ in range(4):
            pg.key("ArrowUp")
        top = pg.ev("document.querySelector('.gcard.g1').dataset.pathway")
        pg.key("ArrowDown")
        nxt = pg.ev("document.querySelector('.gcard.g1').dataset.pathway")
        pg.key("ArrowUp")
        say(f"  keyboard: ↑ to {top}, ↓ to {nxt}")
        if top != "gsv" or nxt == "gsv" or pg.ev("document.querySelector('.gcard.g1').dataset.pathway") != "gsv":
            self.problem(f"gate keyboard: top {top}, next {nxt}")
        say("Ctrl+Enter confirms")
        self.accept_key(pg)
        self.wait_case(pg)
        say("case:")
        d = self.describe_case(pg)
        if d["criteria"] != 6:      # the three not needed ones draw nothing
            self.problem(f"marks on {d['criteria']} requirements, expected 6")
        if d["nav"] != 3 or d["ticks"] != 3 or not d["summary"].startswith("0 of 6 accepted"):
            self.problem(f"navigator / summary: {d}")
        if pg.count(".gl .ev .evq") or pg.count(".chart-col"):
            self.problem("evidence is still drawn inline under the guideline")
        conf = http(f"{base}/api/review/{cid}").get("confirmation") or {}      # the confirmation record carries who
        if conf.get("by") != "Dana" or "confirmed by" in pg.text(".doc-head"):
            self.problem(f"the section confirmation does not carry the remembered name, or the sheet still says it: {conf.get('by')!r}")
        inline_pg = pg.ev("[...document.querySelectorAll('.gl .para > .pg')].filter(x => getComputedStyle(x).position !== 'absolute').length")
        if inline_pg:
            self.problem(f"{inline_pg} page marker(s) still sit inside the flowing text")
        st = pg.ev("JSON.stringify(window.ReviewMarks && ReviewMarks.state())")
        say(f"  highlighter: {st}")
        self.snap(pg, "case")
        # click a requirement's words: the evidence opens beside the guideline, which does not move
        crit = "reflux"
        y0 = pg.ev("document.querySelector('.gl .ln[data-id]').getBoundingClientRect().left")
        say(f"click mark.q ({crit})")
        pg.click_text(f'mark.q[data-crit="{crit}"]')
        pg.wait_for(f'#side .evq[data-crit="{crit}"]', 10)
        y1 = pg.ev("document.querySelector('.gl .ln[data-id]').getBoundingClientRect().left")
        marks, quotes = pg.count(f'mark.q.sel[data-crit="{crit}"]'), pg.count(f'#side .evq[data-crit="{crit}"]')
        say(f"  selected: {marks} mark(s), {quotes} quote(s) in the side panel; the guideline moved {y1 - y0:+.0f}px")
        if not (marks and quotes) or abs(y1 - y0) > 0.5:
            self.problem(f"selecting {crit}: {marks} mark(s), {quotes} quote(s), guideline moved {y1 - y0}")
        self.snap(pg, "requirement-selected")
        # ↑/↓ and j/k move between requirements
        pg.key("ArrowDown")
        nxt = pg.ev("(document.querySelector('.nv[aria-current]') || {dataset: {}}).dataset.crit")
        self.press_char(pg, "k")
        back = pg.ev("(document.querySelector('.nv[aria-current]') || {dataset: {}}).dataset.crit")
        say(f"  ArrowDown -> {nxt}, k -> {back}")
        if nxt != "size" or back != crit:      # reflux and ceap are one row
            self.problem(f"navigator keys: ArrowDown -> {nxt}, k -> {back}")
        pg.key("Escape")
        if not pg.count("#side .pk-panel"):
            self.problem("Esc did not close the requirement back to the packet")
        # feedback on guideline lines
        for kind, text, proposal, mid in (
                ("should_be_requirement", "This line states something the chart must show.", None, "mid-feedback"),
                ("not_a_requirement", "This is a description, not a requirement.", None, None),
                ("logic_wrong", "These are alternatives, not all required.", None, None),
                ("edit", "Wording is off.", "compression therapy for at least 3 months, with dates", "mid-feedback-edit")):
            if not self.bar_open(pg) or not pg.count(f"#fbBar [data-kind={kind}]"):
                self.select_lines(pg)
            self.file_feedback(pg, kind, text, proposal, mid=mid)
        # Marker: the notes on a paragraph collapse to one quiet "N notes" link that opens them in the side panel
        links = pg.ev("[...document.querySelectorAll('.gl .fb-notes')].map(a => [a.textContent, a.dataset.fids.split(' ').length])")
        say(f"  notes links after the guideline paragraphs: {links}; chips left in the text: {pg.count('.gl .fb-chip')}")
        if sum(n for _, n in links) < 4 or pg.count(".gl .fb-chip"):
            self.problem(f"guideline notes are not collapsed into links: {links}")
        self.snap(pg, "feedback-lines")
        pg.click(".gl .fb-notes")
        pg.wait_for("#side .fb-chip.in-notes", 5)
        say(f"  the link opens {pg.count('#side .fb-chip.in-notes')} note(s) in the side panel")
        self.snap(pg, "feedback-notes-panel")
        pg.key("Escape")
        # feedback on an evidence quote, in the side panel
        q = self.click_quote(pg, "reflux")
        self.file_feedback(pg, "wrong_evidence", "This note does not support it.", mid="mid-feedback-evidence")
        if not self.bar_open(pg) or not pg.count("#fbBar [data-kind=evidence_elsewhere]"):
            self.click_quote(pg, "reflux")
        self.file_feedback(pg, "evidence_elsewhere", "This describes the other leg.")
        if not pg.count('#side .evq[data-crit="reflux"]'):
            self.open_req(pg, "reflux")
        ev_chips = pg.count("#side .fb-chip[data-fid]")
        say(f"  {ev_chips} chip(s) in the side panel's quotes")
        if ev_chips < 2:
            self.problem(f"{ev_chips} .fb-chip in the side panel after two evidence items, expected 2")
        self.snap(pg, "feedback-evidence")
        items = http(f"{base}/api/review/{cid}/feedback")
        ev_items = [x for x in items if x["kind"] in ("wrong_evidence", "evidence_elsewhere")]
        for x in ev_items:
            if x["side"] != "chart" or (q["lines"] and x["spans"] != q["lines"]) or x["requirements"] != [q["crit"]]:
                self.problem(f"evidence item {x['kind']} stored as side={x['side']} spans={x['spans']} requirements={x['requirements']}")
        n = pg.count("#fbList .it[data-fid]")
        say(f"remove one feedback item of {n}")
        pg.click("#fbList .it .rm")
        pg.wait_js(f"document.querySelectorAll('#fbList .it[data-fid]').length < {n}", 10, "an item to disappear")
        items = http(f"{base}/api/review/{cid}/feedback")
        say(f"  server has {len(items)} feedback item(s)")
        if len(items) != 5:
            self.problem(f"expected 5 feedback items after one removal, server has {len(items)}")
        pg.key("Escape")
        return cid

    # ------------------------------------------------------------ the tree view: Guideline | Tree

    def tree_view(self, pg: Page, base: str, cid: str) -> None:
        """Toggle to the tree with t (URL and localStorage follow, the highlighter has nothing to draw), open a leaf
        (the same side panel, the navigator in sync), step with the arrow key in tree order, accept with Ctrl+Enter
        from the tree (both views update), open a ?view=tree#<requirement> link, toggle back (the highlighter measures
        again), and finally Undo the accept so the steps after this one start from the same case."""
        pg.goto(f"{base}/review/{cid}?view=guideline")
        self.wait_case(pg)
        if not pg.count(".view-bar .seg [data-view='tree']"):
            self.problem("no Guideline | Tree toggle above the guideline"); return
        say("press t: the tree view")
        pg.ev("document.activeElement && document.activeElement.blur && document.activeElement.blur()")
        self.press_char(pg, "t")
        pg.wait_js("document.querySelector('#glDoc').dataset.view === 'tree'", 5, "the tree view")
        pg.pump(0.3)
        st = pg.ev("JSON.stringify({url: location.search, ls: localStorage.getItem('review.view'), marks: ReviewMarks.state().marks, "
                   "leaves: document.querySelectorAll('#treeDoc .tl[data-crit]').length, groups: document.querySelectorAll('#treeDoc .tn-group').length, "
                   "root: document.querySelector('#treeDoc .tr-v').textContent, glShown: !!document.querySelector('#glDoc .gl-doc').getClientRects().length})")
        st = json.loads(st)
        say(f"  tree: {st}")
        if st["url"] != "?view=tree" or st["ls"] != "tree" or st["marks"] or st["glShown"] or st["leaves"] < 6 or st["groups"] < 2 \
                or st["root"] not in ("Ready for sign-off", "Signed off", "Evidence found, accept each to sign off") and not st["root"].startswith("Waiting on"):
            self.problem(f"tree view state: {st}")
        # an option another one made unneeded steps back (dimmed) only once a person accepted that one: before any
        # accept nothing is dimmed and it says what it waits on; after accepting the documented ones, it dims
        def dims() -> tuple[int, int]:
            return (pg.count("#treeDoc .tn.dim .tl"), pg.ev("[...document.querySelectorAll('#treeDoc .tn:not(.dim) .tl-s')]"
                    ".filter(x => /accept it to set this one aside/.test(x.textContent)).length"))
        dimmed, waits = dims()
        say(f"  before any accept: {dimmed} dimmed, {waits} waiting on an accept")
        if dimmed or not waits:
            self.problem(f"before any accept: {dimmed} option(s) dimmed, {waits} waiting on an accept (expected 0 and some)")
        took = []
        for k in http(f"{base}/api/review/{cid}")["case"]["progress"]["open"]:
            r = urllib.request.Request(f"{base}/api/review/{cid}/accepts", data=json.dumps({"criterion": k, "by": "Dana"}).encode(),
                                       method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=5) as resp:
                rec = next(x for x in json.loads(resp.read())["case"]["requirements"] if x["criterion"] == k)
                took.append((rec.get("accepted") or rec.get("in_ask") or {}).get("id"))
        pg.goto(f"{base}/review/{cid}?view=tree")
        pg.wait_js("document.querySelector('#treeDoc .tl[data-crit]')", 30, "the tree after a reload")
        pg.pump(0.3)
        dimmed, waits = dims()
        say(f"  after accepting the documented ones: {dimmed} dimmed, {waits} waiting")
        if not dimmed or waits or "another option is met" not in pg.text("#treeDoc .tn.dim .tl-s"):
            self.problem(f"after the accepts: {dimmed} option(s) dimmed, {waits} still waiting (expected some and 0)")
        self.snap(pg, "tree-after-accepts")
        for aid in took:                                  # back to the case as it was
            if aid:
                http(f"{base}/api/review/{cid}/accepts/{aid}?by=Dana", "DELETE")
        pg.goto(f"{base}/review/{cid}?view=tree")
        pg.wait_js("document.querySelector('#treeDoc .tl[data-crit]')", 30, "the tree after a reload")
        pg.pump(0.3)
        self.snap(pg, "tree-view")
        self.vocab(pg, "tree view")
        # open a leaf still to accept: the same panel, the navigator follows
        crit = pg.ev("(() => { const c = Review.state().case.requirements.find(r => r.counted && !r.accepted && !r.in_ask && r.mark !== 'struck'); return c && c.criterion; })()")
        if not crit:
            self.problem("nothing left to accept for the tree step"); return
        say(f"click the tree leaf {crit}")
        pg.click(f'#treeDoc .tl[data-crit="{crit}"]')
        pg.wait_js(f"document.querySelector('#side .sp-req') && document.querySelector('.nv[aria-current][data-crit=\"{crit}\"]') && document.querySelector('#treeDoc .tl[aria-current][data-crit=\"{crit}\"]')", 10, f"the panel for leaf {crit}")
        order = pg.ev("[...document.querySelectorAll('#treeDoc .tn:not(.dim) > .tl[data-crit]')].map(b => b.dataset.crit).filter(c => ((Review.state().case.requirements.find(r => r.criterion === c) || {}).near || [c])[0] === c)")   # a group is one step
        say("ArrowDown: the next leaf in tree order")
        pg.key("ArrowDown")
        nxt = pg.ev("(document.querySelector('#treeDoc .tl[aria-current]') || {dataset: {}}).dataset.crit")
        want = order[order.index(crit) + 1] if crit in order and order.index(crit) + 1 < len(order) else crit
        if nxt != want:
            self.problem(f"ArrowDown in the tree went to {nxt!r}, expected {want!r}")
        pg.key("ArrowUp")
        pg.wait_js(f"document.querySelector('#treeDoc .tl[aria-current][data-crit=\"{crit}\"]')", 5, "back on the leaf")
        say("Ctrl+Enter accepts (or adds to the ask) from the tree")
        self.accept_key(pg)
        pg.wait_js(f"(() => {{ const r = Review.state().case.requirements.find(x => x.criterion === {json.dumps(crit)}); return r && (r.accepted || r.in_ask); }})()", 15, f"{crit} accepted from the tree")
        pg.pump(0.3)
        both = pg.ev(f"""(() => {{ const t = document.querySelector('#treeDoc .tl[data-crit="{crit}"]'), n = document.querySelector('.nv[data-crit="{crit}"]');
            return [!!(t && t.querySelector('.ck, .ia')), !!(n && n.querySelector('.ck, .ia')), document.querySelector('#glDoc').dataset.view]; }})()""")
        say(f"  accepted: tree mark {both[0]}, navigator mark {both[1]}, view {both[2]}")
        grp = len(pg.ev(f"Review.state().case.requirements.find(x => x.criterion === {json.dumps(crit)}).near || [1]")) > 1     # a row of a group is marked once every member is
        if not (both[0] and (both[1] or grp)) or both[2] != "tree":
            self.problem(f"after an accept in the tree: {both}")
        self.snap(pg, "tree-accepted")
        rec = next(x for x in http(f"{base}/api/review/{cid}")["case"]["requirements"] if x["criterion"] == crit)
        aid = (rec.get("accepted") or rec.get("in_ask") or {}).get("id")
        # a link with ?view=tree#<requirement> opens the tree with that requirement open
        say(f"open /review/{cid}?view=tree#{crit} in a fresh load")
        pg.goto("about:blank")
        pg.goto(f"{base}/review/{cid}?view=tree#{crit}")
        pg.wait_js(f"document.querySelector('#glDoc') && document.querySelector('#glDoc').dataset.view === 'tree' && document.querySelector('#treeDoc .tl[aria-current][data-crit=\"{crit}\"]') && document.querySelector('#side .sp-req')", 15, "the deep link in the tree view")
        say("press t again: the guideline; the highlighter measures again")
        pg.ev("document.activeElement && document.activeElement.blur && document.activeElement.blur()")
        self.press_char(pg, "t")
        pg.wait_js("document.querySelector('#glDoc').dataset.view === 'guideline' && document.querySelectorAll('#glDoc mark.q').length > 0", 5, "the guideline back with its highlights")      # Plain draws the washes as CSS on the words, no canvas
        back = pg.ev("JSON.stringify({url: location.search + location.hash, ls: localStorage.getItem('review.view'), sel: document.querySelectorAll('mark.q.sel').length})")
        say(f"  back: {back}")
        if json.loads(back)["ls"] != "guideline" or "view=tree" in json.loads(back)["url"]:
            self.problem(f"the guideline view is not remembered: {back}")
        # typing t in a field does not switch
        # (the rail's name field became the sign-in screen; any text field on the page will do)
        pg.ev("(() => { const f = document.createElement('input'); f.id = 'tKeyProbe'; f.type = 'text'; document.querySelector('#main').appendChild(f); f.focus(); })()")
        self.press_char(pg, "t")
        if pg.ev("document.querySelector('#glDoc').dataset.view") != "guideline":
            self.problem("typing t in a field switched the view")
        pg.ev("document.querySelector('#tKeyProbe').remove()")
        if aid:
            urllib.request.urlopen(urllib.request.Request(f"{base}/api/review/{cid}/accepts/{aid}?by=Dana", method="DELETE"), timeout=10).read()

    def press_char(self, pg: Page, ch: str) -> None:
        code, vk = "Key" + ch.upper(), ord(ch.upper())
        pg.send("Input.dispatchKeyEvent", type="keyDown", key=ch, code=code, text=ch, windowsVirtualKeyCode=vk)
        pg.send("Input.dispatchKeyEvent", type="keyUp", key=ch, code=code, windowsVirtualKeyCode=vk)
        pg.pump(0.15)

    def accept_key(self, pg: Page) -> None:
        """Ctrl+Enter (the page takes ⌘ or Ctrl)."""
        for t in ("rawKeyDown", "keyUp"):
            pg.send("Input.dispatchKeyEvent", type=t, key="Enter", code="Enter", windowsVirtualKeyCode=13, modifiers=2)
        pg.pump(0.1)

    def accept_all_ui(self, pg: Page, base: str, cid: str) -> int:
        """Open the first requirement, then Ctrl+Enter until nothing is left: after each accept the page moves on by
        itself to the next requirement still open (struck ones and ones in the ask are skipped), focus on its row,
        with a one-line "Accepted … Undo" note. Returns how many were accepted."""
        n0 = sum(1 for x in http(f"{base}/api/review/{cid}")["case"]["requirements"] if x.get("accepted"))
        ids = pg.ev("[...document.querySelectorAll('.rq-nav .nv[data-crit]')].map(b => b.dataset.crit)")
        self.open_req(pg, ids[0])
        decided = lambda: pg.ev("Review.state().case.requirements.filter(x => x.accepted || x.in_ask).length")
        for _ in range(3 * len(ids)):            # a row can be a group: its panel stacks the members, each with its own Accept
            cur = pg.ev("(document.querySelector('.nv[aria-current]') || {dataset: {}}).dataset.crit || null")
            if not cur or not pg.count("#side .acceptBtn.primary"):
                if cur and pg.ev("document.querySelector('.nv[aria-current]') !== document.querySelector('.rq-nav .nv[data-crit]:last-of-type')"):
                    pg.key("ArrowDown"); continue
                break
            d0 = decided()
            if pg.count("#acceptBtn"):
                self.accept_key(pg)              # the key takes the first member's Accept
            else:
                pg.click("#side .acceptBtn.primary")   # the first is done: the next member by its own button
            pg.wait_js(f"Review.state().case.requirements.filter(x => x.accepted || x.in_ask).length > {d0}", 15, f"{cur} accepted")
            pg.wait_js("document.activeElement !== document.body", 5, "focus kept")
        n1 = sum(1 for x in http(f"{base}/api/review/{cid}")["case"]["requirements"] if x.get("accepted"))
        say(f"  accepted {n1 - n0} requirement(s) from the keyboard")
        return n1 - n0

    # ------------------------------------------------------------ sign-off, accept and strikes

    VOCAB = r"\b(criterion|criteria|verdicts?|confidence|pathways?|spans?)\b"     # the screen says "indication" (the owner's call)

    def vocab(self, pg: Page, where: str) -> None:
        """The page's own words (outside the fold; the guideline's lines, the chart's quotes and typed reasons are
        the documents' and the person's words, not the page's) must not use the internals' vocabulary."""
        hit = pg.ev(f"""(() => {{ const m = document.querySelector('#main').cloneNode(true);
            m.querySelectorAll('.fold, .gl .ln .tx, .evq q, .ev .wd, .removed li, .struck-why, .draft, .fb-list, .fb-chip, .sec-label, .doc-head b, .rule, .confirmed, .flag, .next li, .ask-card .pt-w, .ask-card .ac-where, .ask-card .ac-look, .sp-words, .nv-w, .pk-w, #side .note, .gc-first, .cmp-view, .gc-why, .lines, .gc-top h3, .banner b, .gap-strikes p').forEach(x => x.remove());
            const t = m.innerText; const r = new RegExp({json.dumps(self.VOCAB)}, 'i'); const x = t.match(r);
            return x ? t.slice(Math.max(0, x.index - 60), x.index + 60) : null; }})()""")
        if hit:
            self.problem(f"{where}: the page says an internal word: …{hit}…")
        # nor an internal line id ("g0041", "r0088") anywhere a coordinator looks (the folds are for the curious)
        ids = pg.ev("""(() => { const m = document.querySelector('#main').cloneNode(true); m.querySelectorAll('.fold, details.fold').forEach(x => x.remove());
            const side = document.querySelector('#side'); const t = m.innerText + ' ' + (document.querySelector('#fbBar') || {}).innerText;
            const x = t.match(/\\b[gr]\\d{4}\\b/); return x ? t.slice(Math.max(0, x.index - 50), x.index + 30) : null; })()""")
        if ids:
            self.problem(f"{where}: the page shows an internal line id: …{ids}…")

    def rail_group(self, pg: Page, cid: str) -> str:
        return pg.ev(f"""(() => {{ const b = document.querySelector('.row[data-id="{cid}"]'); if (!b) return null;
            const h = b.closest('.group').querySelector('h2'); return h ? h.dataset.title : null; }})()""") or ""

    def signoff_and_strike(self, pg: Page, base: str, cid: str) -> None:
        pg.goto(f"{base}/review")
        pg.wait_for(f'.row[data-id="{cid}"]', 20)
        say("open the case from the rail: it lands on its first requirement not yet accepted")
        pg.click(f'.row[data-id="{cid}"]')
        self.wait_case(pg)
        landed = pg.ev("(document.querySelector('.nv[aria-current]') || {dataset: {}}).dataset.crit")
        say(f"  landed on {landed}")
        if landed != "reflux":
            self.problem(f"from the rail the case opened on {landed!r}, expected its first requirement")
        # who is signed in: one quiet line in the rail, no Switch; the sign-in screen comes back only when no name is
        # stored (forgotten in another tab): nothing behind it moves (Ctrl+Enter there accepts nothing); signing in again
        # comes back to the same case
        signed = " ".join(pg.text("#signedAs").split())
        if signed != "Signed in as Dana" or pg.count("#switchBtn"):
            self.problem(f"the rail reads {signed!r}, expected 'Signed in as Dana' with no Switch")
        pg.ev("localStorage.removeItem('review.name')")
        pg.send("Page.navigate", url=f"{base}/review/{cid}")      # not goto: it would sign in by itself
        pg.wait_js("document.readyState === 'complete'", 20, "the case to load again")
        pg.pump(0.3)
        pg.wait_for("#signinName", 5)
        self.snap(pg, "signin-again")
        if pg.ev("getComputedStyle(document.querySelector('.app')).display") != "none":
            self.problem("the sign-in screen left the page showing behind it")
        if pg.ev("document.activeElement && document.activeElement.id") != "signinName":
            self.problem("the sign-in screen does not put the cursor in 'Your name'")
        self.accept_key(pg)
        if http(f"{base}/api/review/{cid}")["case"]["progress"]["accepted"]:
            self.problem("the case behind the sign-in screen accepted a requirement")
        pg.enter()              # an empty name is not taken
        if not pg.ev("document.documentElement.classList.contains('signin')"):
            self.problem("the sign-in screen took an empty name")
        pg.sign_in("Dana")
        if pg.ev("localStorage.getItem('review.name')") != "Dana" or " ".join(pg.text("#signedAs").split()) != "Signed in as Dana":
            self.problem("signing in again did not remember the name or show it in the rail")
        if pg.ev("location.pathname") != f"/review/{cid}" or not pg.count("mark.q[data-crit]"):
            self.problem("signing in again did not come back to the case")
        pg.key("Escape")        # the requirement's panel: the packet
        verdict = pg.text(".verdict").strip()
        say(f"ready case: verdict {verdict!r}, rail group {self.rail_group(pg, cid)!r}")
        # evidence is not a sign-off: until every requirement is accepted the header says so (the owner's scope rule)
        if not (verdict.startswith("Evidence found") and verdict.endswith("Accept each to sign off.")):
            self.problem(f"a ready case with nothing accepted reads {verdict!r}, expected 'Evidence found for all N requirements. Accept each to sign off.'")
        if self.rail_group(pg, cid) != "Ready for sign-off":
            self.problem(f"rail lists the ready case under {self.rail_group(pg, cid)!r}")
        if pg.count("#progSign") or not pg.count("#signBtn[disabled]"):      # one Sign off, in the packet panel
            self.problem("sign-off is not held back while nothing is accepted")
        r = urllib.request.Request(f"{base}/api/review/{cid}/signoff", data=b'{"by": "Dana"}', method="POST", headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(r, timeout=5)
            self.problem("the server signed off a case with nothing accepted")
        except urllib.error.HTTPError as e:
            say(f"  sign-off with nothing accepted: HTTP {e.code}")
        pg.click("#copyBtn")
        if not pg.text("#draft").startswith("DRAFT"):
            self.problem(f"the packet before sign-off is not marked a draft: {pg.text('#draft')[:80]!r}")
        self.vocab(pg, "ready for sign-off")
        self.snap(pg, "signoff-held")
        # strike a documented requirement from its panel
        crit = "size"
        self.open_req(pg, crit)
        say(f"click 'Not needed for this case' on {crit}")
        pg.click('#side .strike-btn')
        pg.wait_for("#side .strike-form .strike-why", 10)
        pg.click("#side .strike-form .strike-go")
        if not pg.count("#side .strike-form .strike-msg .err"):
            self.problem("removing without a reason was not refused on the page")
        reason = "The size line is a billing note here, not needed for this vein."
        pg.click('#side .strike-form .chip[data-code="billing"]')      # one tap on a reason, then a note
        pg.type_into("#side .strike-form .strike-why", reason)
        self.snap(pg, "mid-strike")
        pg.click("#side .strike-form .strike-go")
        pg.wait_for(f'mark.q.struck[data-crit="{crit}"]', 20)
        pg.wait_for('#side .struck-why', 10)
        why = pg.text('#side .struck-why')
        say(f"  struck: {why.strip()!r}")
        if reason not in why or "Dana" not in why:
            self.problem(f"the struck requirement does not show who and why: {why!r}")
        d = http(f"{base}/api/review/{cid}")
        sk = [x for x in d.get("strikes", []) if not x.get("undone")]
        fb = [x for x in d.get("feedback", []) if x.get("strike")]
        if len(sk) != 1 or sk[0]["criterion"] != crit or sk[0].get("code") != "billing" or len(fb) != 1 \
                or fb[0]["kind"] != "not_a_requirement" or fb[0].get("code") != "billing":
            self.problem(f"strike on the server: {sk} / {fb}")
        self.snap(pg, "struck")
        # accept everything else from the keyboard; the summary fills; sign-off opens
        say("accept every requirement: Ctrl+Enter, ArrowDown")
        n = self.accept_all_ui(pg, base, cid)
        pg.key("Escape")
        summary = (pg.ev("(document.querySelector('#prog .ticks') || {}).title || ''") or "").strip()      # the count is the bar's title; no words in the row
        say(f"  summary {summary!r}; packet panel lists {pg.count('#side .removed li')} removal(s)")
        if n != 5 or not summary.startswith("5 of 5 accepted") or "1 struck" not in summary:
            self.problem(f"after accepting: {n} accepted, summary {summary!r}")
        if pg.count("#side .removed li") != 1 or not pg.count("#signBtn:not([disabled])"):
            self.problem("the packet panel does not list the removal, or sign-off is still held back")
        self.vocab(pg, "all accepted")
        self.snap(pg, "accepted-all")
        say("sign off as Dana")
        pg.ev("document.querySelector('#signName').value = ''")
        pg.type_into("#signName", "Dana")
        pg.click("#signBtn")
        pg.wait_js("document.querySelector('.verdict') && document.querySelector('.verdict').textContent.trim() === 'Ready to submit.'", 20, "the verdict 'Ready to submit.'")
        pg.wait_js(f"(() => {{ const b = document.querySelector('.row[data-id=\"{cid}\"]'); return b && /Signed off/.test(b.closest('.group').textContent); }})()", 10, "the rail row under 'Signed off'")
        pg.click("#copyBtn")
        draft = pg.text("#draft")
        if "Signed off by Dana" not in draft or draft.count("\n   \"") < 5:
            self.problem(f"the copied packet: {draft[-160:]!r}")
        say(f"  header: {pg.text('.prog-done')!r}; stamp on the sheet: {pg.count('.sigblock')}")
        if pg.count(".sigblock") or not pg.text(".prog-done").startswith("Signed off by Dana"):
            self.problem(f"after sign-off the sheet carries a stamp, or the header reads {pg.text('.prog-done')!r}")
        self.vocab(pg, "signed off")
        self.snap(pg, "signed-off")
        # put it back: the case changed, the sign-off no longer counts; the put-back requirement is open again
        self.open_req(pg, crit)
        say("click 'Put it back'")
        pg.click('#side .unstrike')
        pg.wait_js("!document.querySelector('mark.q.struck')", 20, "the strike to be undone")
        pg.wait_js("/^Evidence found.*Accept each to sign off\\.$/.test(document.querySelector('.verdict').textContent.trim())", 10, "the verdict back to 'Evidence found … Accept each to sign off.' (one requirement open again)")
        if pg.count(".sigblock"):
            self.problem("the signature stayed on the sheet after the sign-off stopped counting")
        pg.key("Escape")
        d = http(f"{base}/api/review/{cid}")
        say(f"  server: sign-off {d['signoff']['state']}, can sign {d['signoff'].get('can_sign')}, open {d['case']['progress']['open']}")
        if d["signoff"]["state"] != "needed" or d["signoff"].get("can_sign") or d["case"]["progress"]["open"] != [crit] or not pg.count("#side .stale"):
            self.problem("after 'Put it back' the sign-off still counts, or the put-back requirement is not open again")
        self.snap(pg, "put-back")
        # Undo an accept from its panel
        self.open_req(pg, "reflux")
        pg.click("#side .unaccept")
        pg.wait_for("#acceptBtn", 10)
        if not pg.ev("!Review.state().case.requirements.find(x => x.criterion === 'reflux').accepted"):
            self.problem("Undo did not take the accept back")
        self.accept_key(pg)
        # accepted again: the page moves on to the requirement still open and says what it did, with Undo
        pg.wait_js("Review.state().case.requirements.find(x => x.criterion === 'reflux').accepted", 10, "reflux accepted again")
        pg.wait_for("#side .sp-done .unaccept", 10)
        pg.key("Escape")

    # ------------------------------------------------------------ highlight to ask, and adding lines to the checklist

    def line_with(self, pg: Page, needle: str, after: str | None = None) -> str:
        lid = pg.ev(f"""(() => {{ const all = [...document.querySelectorAll('#glDoc .ln[data-id]')];
            const from = {json.dumps(after)} ? all.findIndex(l => l.dataset.id === {json.dumps(after)}) : 0;
            const l = all.slice(Math.max(0, from)).find(l => (l.querySelector('.tx') || l).textContent.includes({json.dumps(needle)}));
            return l ? l.dataset.id : null; }})()""")
        if not lid:
            pg.fail(f"no guideline line on the page holds {needle!r}")
        return lid

    def card(self, pg: Page) -> dict:
        pg.wait_js("document.querySelector('#side .ask-card .ac-ruling') || document.querySelector('#side .ask-card .err')", 20, "the answer in the side panel")
        pg.pump(0.35)
        return pg.ev("""(() => { const c = document.querySelector('#side .ask-card'); return {
            ruling: (c.querySelector('.ac-ruling') || {}).textContent || '', src: (c.querySelector('.ac-src') || {}).textContent || '',
            where: (c.querySelector('.ac-where') || {}).textContent || '', quotes: c.querySelectorAll('.evq').length,
            more: (c.querySelector('.ac-more') || {}).textContent || '', groups: [...c.querySelectorAll('.grp-h')].map(x => x.textContent),
            parts: c.querySelectorAll('.pt').length, add: !!c.querySelector('.ac-add'), added: (c.querySelector('.ac-added') || {}).textContent || '',
            err: (c.querySelector('.err') || {}).textContent || '', snapped: document.querySelectorAll('#glDoc .ln.probe').length }; })()""")

    def ask_and_add(self, pg: Page, base: str, cid: str) -> None:
        pg.goto(f"{base}/review/{cid}")
        self.wait_case(pg)
        n_calls = lambda: len([p for p in http(f"{base}/api/review/{cid}").get("probes", []) if p["source"] == "asked"])
        size = self.line_with(pg, "The varicosities are at least 3 millimeters")
        say(f"drag over {size} (a requirement line); the live stroke is drawn while the mouse is down")
        live = pg.drag(f'#glDoc .ln[data-id="{size}"]', f'#glDoc .ln[data-id="{size}"]',
                       before_release=lambda: (pg.ev("JSON.stringify(window.ReviewMarks && ReviewMarks.state())"), self.snap_card_el(pg, "drag-live", f'#glDoc .ln[data-id="{size}"]')))
        say(f"  while dragging: {live and live[0]}")
        if live and '"draft":0' in (live[0] or "") and '"ok":true' in (live[0] or ""):
            self.problem("no live stroke while dragging")
        pg.wait_for(f'#glDoc .ln.probe[data-id="{size}"]', 5)
        c = self.card(pg)
        say(f"  card: {c}")
        if "Evidence found" not in c["ruling"] or c["src"] != "Already on this case's checklist" or c["add"] or not c["quotes"]:
            self.problem(f"a requirement line's card: {c}")
        if n_calls():
            self.problem("a known line took a model call")
        self.vocab(pg, "card on a requirement")
        self.snap(pg, "ask-known")
        pg.key("Escape")
        pg.wait_js("!document.querySelector('.ask-card') && !document.querySelector('#glDoc .ln.probe')", 5, "Esc to close the answer")
        hem = self.line_with(pg, "3. Hemorrhage", size)
        say(f"drag over {size}..{hem} (a mixed condition)")
        pg.drag(f'#glDoc .ln[data-id="{size}"]', f'#glDoc .ln[data-id="{hem}"]')
        c = self.card(pg)
        say(f"  card: {c}")
        if c["snapped"] != 5 or "One of these:" not in c["groups"] or c["parts"] < 5 or "Evidence found" not in c["ruling"]:
            self.problem(f"the mixed condition's card: {c}")
        self.vocab(pg, "card on a mixed condition")
        self.snap(pg, "ask-mixed")
        pg.key("Escape")
        lead = self.line_with(pg, "Treatment of the great or small saphenous veins by surgery (ligation")
        say(f"click {lead}, shift+ArrowDown x3, Enter")
        pg.ev(f"(() => {{ const d = document.querySelector('#glDoc .ln[data-id=\"{lead}\"]').closest('details'); if (d) d.open = true; }})()")   # its gap opens first
        pg.pump(0.2)
        pg.click_text(f'#glDoc .ln[data-id="{lead}"] .tx')
        for _ in range(3):
            pg.key("ArrowDown", shift=True)
        if pg.count("#glDoc .ln.probe") != 4 or not pg.count(".ask-pill"):
            self.problem(f"shift+ArrowDown x3 snapped {pg.count('#glDoc .ln.probe')} line(s), pill {pg.count('.ask-pill')}")
        self.snap(pg, "ask-keyboard-snapped")
        pg.key("Enter")
        pg.wait_js("(document.querySelector('#side .ask-card .checking') || document.querySelector('#side .ask-card .ac-ruling'))", 5, "the answer to open")
        if pg.count("#side .ask-card .checking"):
            say("  'Checking the case…' shown while the model reads")
        else:
            self.problem("no 'Checking the case…' state before the answer to new lines")
        c = self.card(pg)
        say(f"  card: {c}")
        if not c["add"] or n_calls() != 1:
            self.problem(f"new lines' card: {c}, model calls {n_calls()}")
        self.vocab(pg, "card on new lines")
        self.snap(pg, "ask-asked")
        say("click 'Add to this case's checklist'")
        if pg.count("#side .ask-card .ac-by"):
            pg.type_into("#side .ask-card .ac-by", "Dana")
        pg.click("#side .ask-card .ac-add")
        pg.wait_js("document.querySelector('#side .ask-card .ac-added')", 20, "the panel to say the lines were added")
        pg.pump(0.4)
        d = http(f"{base}/api/review/{cid}")
        adds = [x for x in d.get("additions", []) if not x.get("undone")]
        fb = [x for x in d.get("feedback", []) if x.get("addition")]
        say(f"  server: {len(adds)} addition(s), {len(fb)} feedback item(s), result {d['case']['result']['queue']}, progress {d['case']['progress']}")
        if len(adds) != 1 or len(fb) != 1 or fb[0]["kind"] != "should_be_requirement" or n_calls() != 1:
            self.problem(f"the addition on the server: {adds} / {fb}")
        pg.key("Escape")
        if pg.count("#side .removed.added li") != 1:
            self.problem("the packet panel does not list the addition")
        added = pg.ev("(document.querySelector('.rq-nav .nv[data-crit^=\"add\"]') || {dataset: {}}).dataset.crit")
        if not added:
            self.problem("the added requirement is not in the navigator")
        self.vocab(pg, "after adding")
        self.snap(pg, "added")
        # accept it too, sign off, then take the addition off: the sign-off no longer counts
        if added and d["case"]["result"]["queue"] == "ready":
            self.accept_all_ui(pg, base, cid)                 # the addition, and the one put back earlier
            pg.key("Escape")
            if not pg.count("#signBtn:not([disabled])"):
                self.problem(f"sign-off still held back after accepting the addition: {pg.text('#copyMsg')!r}")
            else:
                pg.ev("document.querySelector('#signName').value = ''")
                pg.type_into("#signName", "Dana")
                pg.click("#signBtn")
                pg.wait_js("document.querySelector('.verdict').textContent.trim() === 'Ready to submit.'", 20, "the verdict 'Ready to submit.'")
                self.snap(pg, "added-signed")
                self.open_req(pg, added)
                say("click 'Take it off' on the added requirement")
                pg.click("#side .unadd")
                pg.wait_js("document.querySelector('.verdict').textContent.trim() === 'Ready for sign-off.'", 20, "the sign-off to be withdrawn")
                so = http(f"{base}/api/review/{cid}")["signoff"]
                if so["state"] != "needed" or not (so["record"] or {}).get("withdrawn"):
                    self.problem(f"taking the addition off left the sign-off {so}")
                self.snap(pg, "addition-taken-off")
        else:
            self.problem(f"a documented addition made the case {d['case']['result']['queue']}")
        pg.ev("(() => { const a = document.querySelector('.gl-all'); if (a && a.textContent.startsWith('Show whole')) a.click(); })()")
        pg.pump(0.2)
        bill = self.line_with(pg, "BILLING/CODING INFORMATION")
        say(f"drag over {bill} in the rest of the guideline")
        pg.drag(f'#glDoc .ln[data-id="{bill}"]', f'#glDoc .ln[data-id="{bill}"]')
        c = self.card(pg)
        say(f"  card: {c}")
        if "This isn't something the case can show" not in c["ruling"] or "outside the confirmed indication" not in c["where"] or c["add"]:
            self.problem(f"the billing heading's card: {c}")
        self.vocab(pg, "card outside the section")
        self.snap(pg, "ask-outside")
        pg.key("Escape")
        marks = pg.count("#glDoc .ln.probed")
        pr = http(f"{base}/api/review/{cid}").get("probes", [])
        say(f"  {marks} line(s) carry the margin mark; probes.json has {len(pr)} ask(s)")
        if marks < 8 or len(pr) < 4:
            self.problem(f"margin marks {marks}, probes {len(pr)}")

    def snap_card_el(self, pg: Page, name: str, selector: str) -> None:
        self.shot += 1
        pg.screenshot_around(selector, self.out / f"{self.shot:02d}-{name}.png", pad=160)

    def styles_pass(self, pg: Page, base: str, cid: str) -> None:
        """Every style, light and dark, desktop and phone, on the same case with a requirement open: Plain (the
        default), Clinic, Marker, and Classic."""
        for style in ("plain", "clinic", "marker", "classic"):
            pg.goto(f"{base}/review/{cid}?style={style}")
            self.wait_case(pg)
            if pg.ev("document.documentElement.dataset.style") != style:
                self.problem(f"?style={style} did not switch the style")
            self.open_req(pg, "symptoms")      # the row of symptoms, ADL and compression
            pg.ev("window.scrollTo(0, 0)")
            for scheme in (("light", "dark") if style != "classic" else ("light",)):
                pg.scheme(scheme)
                pg.pump(0.5)
                for w, h, mob in ((1440, 1000, False), (390, 844, True)):
                    if style not in ("clinic", "plain") and mob:
                        continue
                    pg.send("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=2 if mob else 1, mobile=mob)
                    pg.pump(0.5)
                    self.shot += 1
                    p = self.out / f"{self.shot:02d}-style-{style}-{scheme}-{w}.png"
                    p.write_bytes(base64.b64decode(pg.send("Page.captureScreenshot", format="png")["data"]))
                    say(f"  screenshot -> {p}")
                    pg.send("Emulation.clearDeviceMetricsOverride")
            pg.scheme("light")
            self.vocab(pg, f"style {style}")
        pg.goto(f"{base}/review?style=plain")
        pg.wait_for("#landDrop", 10)
        self.snap(pg, "landing")

    def deliverables(self, pg: Page, base: str, cid: str) -> None:
        """The owner's two pictures: desktop light and desktop dark, a requirement open beside the guideline; and
        the Classic style, which keeps today's look."""
        pg.goto(f"{base}/review/{cid}")
        self.wait_case(pg)
        self.open_req(pg, "symptoms")      # the row of symptoms, ADL and compression
        pg.ev("window.scrollTo(0, 0)")
        pg.pump(0.4)
        for scheme in ("light", "dark"):
            pg.scheme(scheme)
            pg.pump(0.6)
            self.shot += 1
            pg.send("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)
            pg.pump(0.4)
            data = pg.send("Page.captureScreenshot", format="png")["data"]
            p = self.out / f"{self.shot:02d}-desktop-{scheme}.png"
            p.write_bytes(base64.b64decode(data))
            pg.send("Emulation.clearDeviceMetricsOverride")
            say(f"  screenshot -> {p}")
        pg.scheme("light")
        st = pg.ev("JSON.stringify(ReviewMarks.state())")
        say(f"  highlighter: {st}")
        if not pg.count("#glDoc mark.q"):      # Plain and Clinic bind the washes to the words (no canvas)
            self.problem(f"the highlighter did not draw: {st}")
        # a phone: the panel is a bottom sheet
        pg.send("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
        pg.pump(0.6)
        self.shot += 1
        p = self.out / f"{self.shot:02d}-mobile-sheet.png"
        p.write_bytes(base64.b64decode(pg.send("Page.captureScreenshot", format="png")["data"]))
        say(f"  screenshot -> {p}")
        pos = pg.ev("getComputedStyle(document.querySelector('#side')).position")
        if pos != "fixed":
            self.problem(f"on a phone the side panel is {pos}, expected a fixed bottom sheet")
        pg.send("Emulation.clearDeviceMetricsOverride")
        pg.goto(f"{base}/review/{cid}?style=classic")
        self.wait_case(pg)
        if pg.ev("document.documentElement.dataset.style") != "classic":
            self.problem("?style=classic did not switch the style")
        self.open_req(pg, "symptoms")      # the row of symptoms, ADL and compression
        self.snap(pg, "classic")
        pg.click('.style-switch [data-style="marker"]')
        if pg.ev("document.documentElement.dataset.style") != "marker" or pg.ev("localStorage.getItem('review.style')") != "marker":
            self.problem("the style switcher did not switch back to Marker or did not remember it")

    def edge_states(self, pg: Page, base: str) -> None:
        """A slow stub server that fails at step I and has two guidelines on file: the upload progress as calm lines,
        a failed check with Retry, and "None of these" at the gate -> "This guideline doesn't apply" with the other
        guideline offered."""
        pg.goto(f"{base}/review")
        pg.wait_for("#addBtn", 20)
        pg.click("#addBtn")
        pg.set_file("#dropFiles", CHART_PDF)
        pg.wait_js("!document.querySelector('#dlgGo').disabled", 10, "#dlgGo to be enabled")
        pg.click("#dlgGo")
        pg.wait_js("document.querySelectorAll('.runlines .rl.done').length >= 2", 30, "two stages filled in")
        lines = pg.ev("[...document.querySelectorAll('.runlines .rl')].map(x => x.className.split(' ')[1] + ': ' + x.textContent.trim())")
        say(f"  progress: {lines}")
        if not any(x.startswith("done: ✓Found the order") for x in lines):
            self.problem(f"the progress lines do not say what was found: {lines}")
        self.snap(pg, "upload-progress")
        pg.wait_for("#confirmBtn", 60)
        cid = pg.ev("location.pathname.split('/').pop()")
        say("confirm the suggested section; the stub fails at reading the chart")
        pg.click("#confirmBtn")
        pg.wait_js("document.querySelector('.verdict') && /stopped/.test(document.querySelector('.verdict').textContent)", 60, "the failed state")
        pg.pump(0.4)
        self.vocab(pg, "failed")
        self.snap(pg, "failed")
        pg.click("#retryBtn")
        pg.wait_js("/stopped/.test(document.querySelector('.verdict').textContent) && !document.querySelector('#retryBtn').disabled", 60, "Retry to run and stop again")
        # None of these, on a second upload
        cid2 = self.upload(pg, base)
        say("click 'None of these', then 'This guideline doesn't apply'")
        pg.click("#noneLink")
        pg.wait_for("#noneGo", 5)
        pg.click("#noneGo")
        pg.wait_js("document.querySelector('.verdict') && document.querySelector('.verdict').textContent.trim() === \"This guideline doesn't apply.\"", 20, "the doesn't-apply page")
        offers = pg.count("[data-recheck]")
        why = pg.text(".nofit-page .why")
        say(f"  {why!r}; {offers} other guideline(s) offered")
        if "Dana judged" not in why or offers != 1:
            self.problem(f"the doesn't-apply page: {why!r}, {offers} offer(s)")
        self.vocab(pg, "doesn't apply")
        self.snap(pg, "doesnt-apply")
        pg.click("[data-recheck]")
        pg.wait_js("document.querySelector('.runlines') || document.querySelector('#confirmBtn') || /Which pathway/.test(document.body.innerText)", 30, "the check against the other guideline to start")
        st = http(f"{base}/api/review/{cid2}")
        say(f"  re-check: state {st['state']}, guideline {st['guideline']['id']}")
        if st["guideline"]["id"] != "cms-ncd-20-8-3":
            self.problem(f"the re-check did not use the other guideline: {st['guideline']}")

    def strike_not_ready(self, pg: Page, base: str, cid: str) -> None:
        """A case that is not ready: sign-off stays held back; striking one of its missing requirements re-decides it."""
        n0 = pg.count("#side .pk.st-ask")
        crit = pg.ev("(() => { const a = document.querySelector('#side .pk.st-ask a[data-sel]'); return a ? a.dataset.sel : null; })()")
        if not crit:
            self.problem("the not-ready case lists nothing to ask")
            return
        if pg.count("#signBtn:not([disabled])"):
            self.problem("a case that is not ready offers an enabled sign-off")
        say(f"not ready: {n0} thing(s) to ask; strike {crit}")
        self.open_req(pg, crit)
        # a row of adjoining requirements stacks its members, each with its own button: strike the first member
        # (the last requirement left in the section cannot be removed, so the other stays), the highlight stays
        # until the whole run is struck
        pg.click('#side .strike-btn')
        pg.click('#side .strike-form .chip[data-code="not_for_case"]')
        pg.type_into("#side .strike-form .strike-why", "Not part of this payer's ask for this patient.")
        pg.click("#side .strike-form .strike-go")
        pg.wait_js(f"(Review.state().case.requirements.find(x => x.criterion === {json.dumps(crit)}) || {{}}).mark === 'struck'", 20, f"{crit} struck")
        pg.key("Escape")
        pg.pump(0.3)
        n1 = pg.count("#side .pk.st-ask")
        say(f"  {n1} thing(s) to ask after the strike")
        if n1 != n0 - 1:
            self.problem(f"striking a missing requirement left {n1} thing(s) to ask, expected {n0 - 1}")
        r = urllib.request.Request(f"{base}/api/review/{cid}/signoff", data=b'{"by": "Dana"}', method="POST",
                                   headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(r, timeout=5)
            self.problem("a case that is not ready was signed off")
        except urllib.error.HTTPError as e:
            say(f"  sign-off of a case that is not ready: HTTP {e.code}")
            if e.code != 409:
                self.problem(f"sign-off of a not-ready case answered {e.code}, expected 409")
        self.vocab(pg, "not ready, struck")
        self.snap(pg, "not-ready-struck")
        # Accept means proof: a requirement that is not in the chart is added to the ask, never accepted
        rest = pg.ev("(() => { const a = document.querySelector('#side .pk.st-ask a[data-sel]'); return a ? a.dataset.sel : null; })()")
        if rest:
            self.open_req(pg, rest)
            btn = pg.text("#acceptBtn").strip()
            say(f"  {rest}: the primary button reads {btn!r}")
            if not btn.startswith("Add to the ask"):
                self.problem(f"a requirement not in the chart offers {btn!r}, expected 'Add to the ask'")
            self.accept_key(pg)
            # added: the page moves on (here, to the packet: nothing else is open) and says "Added to the ask … Undo"
            pg.wait_for("#side .sp-done .unaccept", 10)
            nav = pg.text(f'.nv[data-crit="{rest}"]')
            d = http(f"{base}/api/review/{cid}")
            p = d["case"]["progress"]
            say(f"  after Ctrl+Enter: navigator {nav.strip()!r}, progress {p}, message {len(d['case']['message'])} chars")
            if "In the ask" not in nav or pg.count(f'.nv[data-crit="{rest}"] .ck') or p["in_ask"] != 1 or p["accepted"] != 0 or not d["case"]["message"]:
                self.problem(f"adding to the ask: navigator {nav!r}, progress {p}")
            if "1 in the ask" not in (pg.ev("(document.querySelector('#prog .ticks') || {}).title || ''") or "") or pg.count("#prog .n"):
                self.problem(f"the bar's title does not say what is in the ask, or the row shows words: {(pg.ev("(document.querySelector('#prog .ticks') || {}).title || ''") or "")!r}")
            self.snap(pg, "in-the-ask")
            pg.key("Escape")
            pg.pump(0.6)
            lane = self.rail_group(pg, cid)
            heads = pg.ev("[...document.querySelectorAll('.rail .group h2')].map(h => h.textContent.trim())")
            say(f"  rail lanes: {heads}; this case in {lane!r}")
            # the row shows only the name; the detail (who it waits on, the indication) is its tooltip
            row_tip = pg.ev(f"(document.querySelector('.row[data-id=\"{cid}\"]') || {{}}).title || ''") or ""
            row_txt = pg.text(f'.row[data-id="{cid}"]').strip()
            if lane != "In the ask" or "Waiting on Dr. Vasquez" not in row_tip or "Accessory Saphenous Veins" not in row_tip:
                self.problem(f"a case with something in the ask sits in {lane!r} (tooltip {row_tip!r})")
            if "Waiting on" in row_txt or "Saphenous" in row_txt:
                self.problem(f"the rail row shows a detail line: {row_txt!r}")
            self.snap_card_el(pg, "queue", ".rail")
            pg.click("#msgBtn")
            if not pg.text("#draft").startswith("Dr."):
                self.problem(f"the message to the surgeon is not assembled from the ask: {pg.text('#draft')[:80]!r}")

    def second_chart(self, pg: Page, base: str) -> str:
        cid = self.upload(pg, base)
        say("gate: pick another indication from the rows")
        other = pg.ev("""(() => { const r = [...document.querySelectorAll('.g-row')].find(x => x.dataset.pathway !== 'gsv'); return r ? r.dataset.pathway : null; })()""")
        if not other:
            pg.fail("no other indication row at the gate")
        pg.click(f'.g-row[data-pathway="{other}"]')
        now = pg.ev("document.querySelector('.gcard.g1').dataset.pathway")
        say(f"  the card is now: {now}")
        if now != other or not pg.count('.g-row[data-pathway="gsv"]'):
            self.problem(f"after picking {other!r} the card is {now!r} (the suggestion should drop into the rows)")
        self.snap(pg, "gate-repicked")
        pg.click("#confirmBtn")
        self.wait_case(pg)
        say("case (other section):")
        d = self.describe_case(pg)
        self.snap(pg, "case-other-section")
        doc = http(f"{base}/api/review/{cid}")
        used = (doc.get("case") or {}).get("result", {}).get("pathway_used")
        say(f"  result for {cid}: {doc.get('state')} pathway_used={used}")
        if used != [other]:
            self.problem(f"second chart: pathway_used {used}, expected [{other!r}]")
        missing = [r for r in (doc.get("case") or {}).get("requirements", []) if r["mark"] == "missing" and not r["evidence"]]
        if missing:
            self.open_req(pg, missing[0]["criterion"])
            msgs = pg.count("#side .none") + pg.count("#side .sp-help") + pg.count("#side .note")
            cards = max(pg.count("#side .sp-stack"), 1)      # one helpful sentence for each member of the row
            if not pg.count("#side .sp-help") or msgs != cards:
                self.problem(f"a requirement with nothing in the chart shows {msgs} messages, expected one helpful sentence")
            pg.key("Escape")
        self.strike_not_ready(pg, base, cid)
        return cid

    def samples(self, pg: Page, base: str, ids: list[str]) -> None:
        for cid in ids:
            say(f"stored sample /review/{cid}")
            pg.goto(f"{base}/review/{cid}")
            pg.wait_js("(() => { const s = window.Review && Review.state && Review.state(); return s && s.state === 'done' && "
                       "document.querySelector('#main') && !/Checking this case/.test(document.querySelector('#main').textContent); })()",
                       30, f"the finished case for {cid}")
            pg.pump(0.5)
            self.describe_case(pg)
            # each stored state reads as intended: not covered offers the message; the NCD shows its confirmed
            # section and the part that applies to every request; a missing case lists what to ask
            if "okafor" in cid and not (pg.count("#side #msgBtn") and "Nothing to accept" in pg.text("#prog")):
                self.problem("the not-covered sample does not offer the message to the surgeon")
            if "mitchell" in cid:
                if "Applies to every request under this guideline" not in pg.text("#glDoc"):
                    self.problem("the NCD sample does not show the part that applies to every request")
                # exclusions read as exclusions, driven by the server's proof
                ex = pg.ev("""(() => { const r = Review.state().case.requirements.filter(x => x.counted && (x.role === 'exclusion' || x.role === 'part'));
                    return r.map(x => [x.criterion, x.proof]); })()""")
                navx = pg.ev("[...document.querySelectorAll('.nv .nv-w')].filter(x => x.textContent.startsWith('Must not apply: ')).length")
                say(f"  NCD exclusions {len(ex)}, navigator labels 'Must not apply:' {navx}")
                if not ex or navx != len(ex):
                    self.problem(f"exclusions are not framed as exclusions in the navigator: {navx} of {len(ex)}")
                cleared = next((c for c, p in ex if p), None)
                if cleared:
                    self.open_req(pg, cleared)
                    rl, btn = pg.text("#side .sp-ruling").strip(), pg.text("#acceptBtn").strip()
                    reds = pg.ev("[...document.querySelectorAll('#side .evq .side')].map(x => x.textContent)")
                    say(f"  cleared exclusion {cleared}: {rl!r}, button {btn!r}, quote labels {reds}")
                    if "Doesn't apply to this patient" not in rl or not btn.startswith("Accept") or "Contradicts" in reds:
                        self.problem(f"a cleared exclusion reads {rl!r} / {btn!r} / {reds}")
                    self.snap(pg, "exclusion-cleared")
                    pg.key("Escape")
                applies = next((c for c, p in ex if not p), None)
                if applies:
                    self.open_req(pg, applies)
                    rl, hint = pg.text("#side .sp-ruling").strip(), pg.text("#side .sp-act .hint")
                    say(f"  exclusion that applies {applies}: {rl!r}; {hint!r}")
                    if not rl.startswith(("✗Applies", "?Can't tell")) or "signed off once the case shows it" in hint:
                        self.problem(f"an exclusion that applies reads {rl!r} / {hint!r}")
                    pg.key("Escape")
            if "linda" in cid and not pg.count("#side .pk.st-ask"):
                self.problem("the missing sample lists nothing to ask")
            self.vocab(pg, f"sample {cid}")
            self.snap(pg, f"sample-{cid}")

    def two_codes(self, pg: Page, base: str) -> None:
        cid = self.upload(pg, base)
        gate = http(f"{base}/api/review/{cid}")["gate"]
        codes = [c["code"] for c in gate.get("codes", [])]
        say(f"two codes: the code pick comes first: {gate.get('kind')} {codes}")
        if gate.get("kind") != "pick_code" or len(codes) != 2:
            self.problem(f"two-codes gate is {gate.get('kind')!r} with {codes}, expected the code pick with two codes")
        self.snap(pg, "two-codes-gate")
        pg.click("#confirmBtn")                  # the one code; then the indication gate for it
        pg.wait_js("(Review.state().gate || {}).suggested", 60, "the indication gate after the code pick")
        picks = http(f"{base}/api/review/{cid}")["gate"]["suggested"]
        say(f"  then the indication gate suggests {picks}")
        if len(picks) != 1:
            self.problem(f"after the code pick the gate suggested {picks}, expected one pick")
        pg.wait_for("#confirmBtn", 20)
        pg.click("#confirmBtn")
        self.wait_case(pg)
        conf = http(f"{base}/api/review/{cid}")["confirmation"]
        say(f"  confirmed {conf['confirmed']}")
        if conf["confirmed"] != picks:
            self.problem(f"two-codes confirmed {conf['confirmed']}, expected {picks}")
        self.snap(pg, "two-codes-case")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="folder for the screenshots")
    ap.add_argument("--port", type=int, default=8020)
    ap.add_argument("--port2", type=int, default=8021, help="the --two-codes server")
    ap.add_argument("--port3", type=int, default=8022, help="the server seeded with the stored samples")
    ap.add_argument("--port4", type=int, default=8024, help="a slow server that fails at step I, two guidelines on file")
    ap.add_argument("--cdp", type=int, default=9240)
    ap.add_argument("--delay", type=float, default=0.3)
    ap.add_argument("--skip-two-codes", action="store_true")
    ap.add_argument("--skip-samples", action="store_true")
    ap.add_argument("--keep", action="store_true", help="keep the scratch data dir and Chrome profile")
    a = ap.parse_args()
    for port in (a.port, a.port2, a.port3, a.port4, a.cdp):
        if port in FORBIDDEN_PORTS:
            print(f"port {port} belongs to someone else; pick another", file=sys.stderr)
            return 2
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="verify-review-"))
    data1, data2, data3, data4, profile = scratch / "data", scratch / "data2", scratch / "data3", scratch / "data4", scratch / "chrome"
    for d in (data1, data2, data3, data4, profile):
        d.mkdir(parents=True)
    say(f"scratch {scratch}; screenshots -> {out}")
    present = [] if a.skip_samples else seed(data3)
    say(f"seeded {len(present)} stored sample(s) for the samples server: {present}")
    srv1 = srv2 = srv3 = srv4 = chrome = None
    pg = None
    run = Run(out)
    code = 1
    try:
        srv1 = start_server(a.port, data1, a.delay, [], scratch / "server1.log")
        chrome = start_chrome(a.cdp, profile)
        pg = new_tab(a.cdp)
        base = f"http://127.0.0.1:{a.port}"
        say(f"--- first chart on {base}")
        first = run.flow(pg, base)
        say("--- the tree view on the first chart")
        run.tree_view(pg, base, first)
        say("--- sign-off and strike on the first chart")
        run.signoff_and_strike(pg, base, first)
        say("--- highlight to ask and add on the first chart")
        run.ask_and_add(pg, base, first)
        say("--- the two desktop pictures, a phone, and the Classic style")
        run.deliverables(pg, base, first)
        say("--- every style, light and dark, desktop and phone")
        run.styles_pass(pg, base, first)
        say("--- second chart, another section")
        run.second_chart(pg, base)
        srv4 = start_server(a.port4, data4, 1.0, ["--fail", "judge_chart", "--more-guidelines"], scratch / "server4.log")
        say(f"--- edge states on http://127.0.0.1:{a.port4}: progress, failed + Retry, None of these")
        run.edge_states(pg, f"http://127.0.0.1:{a.port4}")
        if not a.skip_two_codes:
            srv2 = start_server(a.port2, data2, a.delay, ["--two-codes"], scratch / "server2.log")
            base2 = f"http://127.0.0.1:{a.port2}"
            say(f"--- two codes on {base2}")
            run.two_codes(pg, base2)
        if present:
            srv3 = start_server(a.port3, data3, a.delay, [], scratch / "server3.log")
            base3 = f"http://127.0.0.1:{a.port3}"
            say(f"--- stored samples on {base3}")
            run.samples(pg, base3, present)
        errors = [c for c in pg.console if not c.startswith("console.warning")]
        say(f"console errors during the run: {len(errors)}")
        for c in errors[:30]:
            say(f"  {c}")
        if run.problems:
            say(f"{len(run.problems)} problem(s):")
            for p in run.problems:
                say(f"  - {p}")
            code = 1
        else:
            say(f"OK: {run.shot} screenshots in {out}")
            code = 0
    except StepFailed as e:
        print(str(e), file=sys.stderr, flush=True)
        if pg is not None:
            try:
                run.snap(pg, "FAILED")
            except Exception:       # noqa: BLE001
                pass
        code = 1
    finally:
        if pg is not None:
            try:
                pg.ws.close()
            except Exception:       # noqa: BLE001
                pass
        stop(chrome, "Chrome")
        stop(srv1, f"dev server :{a.port}")
        stop(srv2, f"dev server :{a.port2}")
        stop(srv3, f"dev server :{a.port3}")
        stop(srv4, f"dev server :{a.port4}")
        for log in ("server1.log", "server2.log", "server3.log", "server4.log"):
            p = scratch / log
            if p.exists() and code != 0:
                tail = p.read_text()[-2000:]
                if tail.strip():
                    say(f"{log} tail:\n{tail}")
        if a.keep or code != 0:
            say(f"scratch kept at {scratch}")
        else:
            shutil.rmtree(scratch, ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
