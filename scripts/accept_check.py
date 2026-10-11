"""Accept, checked the way a person does it: real clicks and keys in Chromium (Playwright), on a fresh case.

    .venv/bin/python -m scripts.accept_check --data DIR [--case 395a14db63] [--port 8111] [--headed]
    .venv/bin/python -m scripts.accept_check --base http://127.0.0.1:8111 [--case ID]

With --data the folder is copied to a temporary one and a dev server (scripts.dev_server) is started on --port, so the
case in DIR is never changed. With --base the running server is used as it is, and the case must have nothing
accepted yet; every accept the run makes is undone at the end (the undo is recorded, as any Undo is).

Checks, in order (each printed; the run exits 1 on the first PROBLEM list that is not empty):
  1. no name in this browser: the sign-in screen comes first, the cursor in "Your name"; a name and Enter open the case;
  2. the name forgotten mid-session (another tab): Accept puts up the sign-in with a one-line prompt and the
     cursor in the field, accepts nothing (no POST without a name), and completes the accept once a name is typed;
  3. the panel's Accept: nothing covers it (elementFromPoint at its centre is the button, at four widths), a click
     POSTs /api/review/{id}/accepts {criterion, by}, 201, the navigator shows the check, focus moves to the next row;
  4. Ctrl+Enter and Meta+Enter (⌘↵) each accept the open requirement;
  5. the Tree view: open a leaf, Accept;
  6. a double click sends one POST and leaves no error on the panel;
  7. no page errors, no failed accept responses.
Ports 8000-8003, 8025, 8061, 8071, 8081, 8091 and 8101 belong to other people and are refused.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable
FORBIDDEN = {8000, 8001, 8002, 8003, 8025, 8061, 8071, 8081, 8091, 8101}
NAME = "Dana"
WIDTHS = [(1440, 900), (1280, 720), (1024, 768), (390, 844)]
problems: list[str] = []


def say(m: str) -> None:
    print(m, flush=True)


def problem(m: str) -> None:
    problems.append(m)
    say(f"  PROBLEM: {m}")


def http(url: str, method: str = "GET") -> dict:
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read() or b"{}")


def wait_up(base: str, timeout: float = 20) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(base + "/review", timeout=2)
            return
        except Exception:
            time.sleep(0.25)
    raise SystemExit(f"server at {base} did not come up")


class Watch:
    """Every accept request and response, and every page error."""

    def __init__(self, pg):
        self.posts: list[dict] = []
        self.resps: list[int] = []
        self.errors: list[str] = []
        pg.on("request", self._req)
        pg.on("response", self._resp)
        pg.on("pageerror", lambda e: self.errors.append(str(e)))

    def _req(self, r):
        if r.method == "POST" and r.url.endswith("/accepts"):
            self.posts.append(json.loads(r.post_data or "{}"))

    def _resp(self, r):
        if r.request.method == "POST" and r.url.endswith("/accepts"):
            self.resps.append(r.status)


def accepted(pg) -> int:
    return pg.evaluate("Review.state().case.progress.accepted")


def open_req(pg, crit: str) -> None:
    pg.click(f".nv[data-crit='{crit}']")
    pg.wait_for_selector("#acceptBtn", state="visible", timeout=5000)


def first_open(pg) -> str | None:
    return pg.evaluate("(Review.state().case.progress.open || [])[0] || null")


def covered(pg) -> str | None:
    """None when the Accept button is the topmost element at its centre; otherwise what is on top of it."""
    return pg.evaluate("""(() => { const b = document.querySelector('#acceptBtn'); if (!b) return 'no #acceptBtn';
      b.scrollIntoView({ block: 'center', behavior: 'instant' }); const r = b.getBoundingClientRect();
      const e = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return e && b.contains(e) ? null : (e ? e.outerHTML.slice(0, 160) : 'nothing at its centre'); })()""")


def wait_accepted(pg, n: int, what: str) -> bool:
    try:
        pg.wait_for_function(f"Review.state() && Review.state().case && Review.state().case.progress.accepted >= {n}", timeout=5000)
        return True
    except Exception:
        problem(f"{what}: the case shows {accepted(pg)} accepted, expected {n}")
        return False


def run(base: str, cid: str, headed: bool) -> None:
    d = http(f"{base}/api/review/{cid}")
    if d["case"]["progress"]["accepted"]:
        raise SystemExit(f"case {cid} already has accepts; use a fresh one")
    total = d["case"]["progress"]["total"]
    say(f"case {cid}: {total} requirements open")
    with sync_playwright() as p:
        br = p.chromium.launch(headless=not headed)
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        w = Watch(pg)
        mod = "Meta" if sys.platform == "darwin" else "Control"

        say("1. no name stored: the sign-in comes first")
        pg.goto(f"{base}/review/{cid}")
        pg.evaluate("localStorage.removeItem('review.name')")
        pg.reload()
        pg.wait_for_selector("#signinName", state="visible", timeout=5000)
        try:
            pg.wait_for_function("document.activeElement && document.activeElement.id === 'signinName'", timeout=1000)
        except Exception:
            problem("the sign-in does not put the cursor in 'Your name'")
        pg.keyboard.type(NAME)
        pg.keyboard.press("Enter")
        pg.wait_for_selector(".nv[data-crit]", state="visible", timeout=10000)

        say("2. the name forgotten mid-session: Accept asks for it, then accepts")
        crit = first_open(pg)
        open_req(pg, crit)
        pg.evaluate("localStorage.removeItem('review.name')")      # as another tab would
        pg.click("#acceptBtn")
        try:
            pg.wait_for_selector("#signinName", state="visible", timeout=3000)
        except Exception:
            problem("Accept without a name did not ask for one (nothing visible happened)")
        note = pg.text_content("#signinNote") or ""
        say(f"  prompt: {note!r}")
        if "accept" not in note.lower():
            problem(f"the sign-in does not say it is for the accept: {note!r}")
        try:
            pg.wait_for_function("document.activeElement && document.activeElement.id === 'signinName'", timeout=1000)
        except Exception:
            problem("the cursor is not in 'Your name'")
        if w.posts:
            problem(f"an accept was sent without a name: {w.posts}")
        pg.keyboard.type(NAME)
        pg.keyboard.press("Enter")
        wait_accepted(pg, 1, "after typing the name")
        if w.posts and w.posts[-1] != {"criterion": crit, "by": NAME}:
            problem(f"the accept sent {w.posts[-1]}, expected criterion {crit} by {NAME}")

        say("3. the panel's Accept: not covered, a click accepts, focus moves on")
        for vw, vh in WIDTHS:
            pg.set_viewport_size({"width": vw, "height": vh})
            pg.wait_for_timeout(250)
            c = first_open(pg)
            pg.evaluate(f"Review.select({json.dumps(c)})")
            pg.wait_for_selector("#acceptBtn", state="visible", timeout=5000)
            on_top = covered(pg)
            say(f"  {vw}x{vh}: {'clear' if on_top is None else 'COVERED by ' + on_top}")
            if on_top is not None:
                problem(f"at {vw}x{vh} the Accept button is covered by {on_top}")
        pg.set_viewport_size({"width": 1440, "height": 900})
        pg.wait_for_timeout(250)
        crit = first_open(pg)
        open_req(pg, crit)
        n0 = len(w.posts)
        pg.click("#acceptBtn")
        wait_accepted(pg, 2, "after clicking Accept")
        if len(w.posts) != n0 + 1:
            problem(f"one click sent {len(w.posts) - n0} accepts")
        if not pg.locator(f".nv[data-crit='{crit}'] .ck").count():
            problem("the navigator does not show the check on the accepted requirement")
        foc = pg.evaluate("(document.activeElement && document.activeElement.dataset && document.activeElement.dataset.crit) || null")
        say(f"  focus moved to {foc!r}")
        if foc in (None, crit):
            problem(f"focus did not move on to the next requirement (it is on {foc!r})")

        say("4. Ctrl+Enter and ⌘↵ accept")
        for k, n in (("Control+Enter", 3), (f"{mod}+Enter", 4)):
            crit = first_open(pg)
            open_req(pg, crit)
            pg.keyboard.press(k)
            wait_accepted(pg, n, k)

        say("5. Tree view: a leaf, then Accept")
        crit = first_open(pg)
        if pg.locator(".view-bar .seg button").count() >= 2:
            pg.click(".view-bar .seg button:nth-child(2)")
            pg.wait_for_selector(f"#treeDoc .tl[data-crit='{crit}'], #treeDoc [data-crit='{crit}']", state="visible", timeout=5000)
            pg.click(f"#treeDoc [data-crit='{crit}']")
            pg.wait_for_selector("#acceptBtn", state="visible", timeout=5000)
            if covered(pg) is not None:
                problem(f"in the Tree view Accept is covered by {covered(pg)}")
            pg.click("#acceptBtn")
            wait_accepted(pg, 5, "Tree view Accept")
            pg.click(".view-bar .seg button:nth-child(1)")
        else:
            say("  no Guideline | Tree toggle on this case; skipped")

        say("6. a double click sends one accept")
        crit = first_open(pg)
        if crit:
            open_req(pg, crit)
            n0, a0 = len(w.posts), accepted(pg)
            pg.dblclick("#acceptBtn")
            wait_accepted(pg, a0 + 1, "double click")
            pg.wait_for_timeout(600)
            if len(w.posts) - n0 != 1:
                problem(f"a double click sent {len(w.posts) - n0} accepts")
            err = pg.evaluate("[...document.querySelectorAll('#acceptBtn')].map(b => b.textContent).filter(t => !/^(Accept|Add to the ask|Confirmed outside the case)/.test(t))")
            if err:
                problem(f"the panel shows {err}")

        say("7. requests and errors")
        bad = [s for s in w.resps if s != 201]
        say(f"  {len(w.posts)} accept POSTs, responses {w.resps}")
        if bad:
            problem(f"accept responses that failed: {bad}")
        if w.errors:
            problem(f"page errors: {w.errors}")
        br.close()


def undo_all(base: str, cid: str) -> None:
    d = http(f"{base}/api/review/{cid}")
    for r in d["case"]["requirements"]:
        rec = r.get("accepted") or r.get("in_ask")
        if rec and rec.get("id"):
            http(f"{base}/api/review/{cid}/accepts/{rec['id']}?by={NAME}", method="DELETE")
    say(f"undid this run's accepts on {cid}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="a running server to use as it is (its case must be fresh; undone at the end)")
    ap.add_argument("--data", help="a data folder to copy and serve on --port")
    ap.add_argument("--port", type=int, default=8111)
    ap.add_argument("--case", default="395a14db63")
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()
    if not a.base and not a.data:
        ap.error("give --data DIR (copied, served on --port) or --base URL")
    srv, tmp = None, None
    base = a.base
    try:
        if not base:
            if a.port in FORBIDDEN:
                ap.error(f"port {a.port} belongs to someone else")
            tmp = Path(tempfile.mkdtemp(prefix="accept_check_"))
            shutil.copytree(a.data, tmp / "data")
            srv = subprocess.Popen([PY, "-m", "scripts.dev_server", "--port", str(a.port), "--delay", "0.2", "--data", str(tmp / "data")],
                                   cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            base = f"http://127.0.0.1:{a.port}"
            wait_up(base)
        else:
            port = int(base.rsplit(":", 1)[-1].split("/")[0])
            if port in FORBIDDEN:
                ap.error(f"port {port} belongs to someone else")
        run(base, a.case, a.headed)
    finally:
        if a.base:
            try:
                undo_all(base, a.case)
            except Exception as e:
                say(f"could not undo: {e}")
        if srv:
            srv.terminate()
            srv.wait(5)
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    if problems:
        say(f"\nFAIL: {len(problems)} problem(s)")
        for m in problems:
            say(f"  - {m}")
        sys.exit(1)
    say("\nOK: Accept works by click, by key, in the Tree view, without a name and on a double click")


if __name__ == "__main__":
    main()
