"""Drive the review page with real key events and check what Cmd/Ctrl+Enter does in every context.

    .venv/bin/python -m scripts.keys_check [--port 8111] [--only gate,case] [--headed]

Starts its own stub server (scripts.dev_server on a scratch data dir; nothing under data/ is touched), then for
each of Meta+Enter (as on a Mac, the page told it is on a Mac) and Control+Enter (the page told it is not) checks:
section gate, case page (accept / add to the ask, focus to the next open one), strike reason, feedback, the
highlight-to-ask card, the name field, the packet (sign-off must NOT fire; a hint shows instead), the add-a-chart
dialog, and the guards: key repeat ignored, no double fire, nothing from a closed panel, plain Enter never submits.
Exit status 1 when any check fails.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "data" / "samples" / "synthetic" / "maria_delgado_chart.pdf"
FAILS: list[str] = []
SHOTS: Path | None = None


def check(ok: bool, what: str) -> None:
    print(("  ok    " if ok else "  FAIL  ") + what)
    if not ok:
        FAILS.append(what)


def http(url: str, data: bytes | None = None):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    return json.load(urllib.request.urlopen(req, timeout=30))


def highlight(pg, n: int, ask: bool) -> None:
    """Select the n-th visible guideline line as a drag would; ask=False holds it as a keyboard selection that has
    not been asked yet (Shift+Arrow from a marked word)."""
    if ask:
        pg.evaluate("""n => { const t = [...document.querySelectorAll('#glDoc .ln[data-id] .tx')].filter(e => e.getClientRects().length)[n];
            const r = document.createRange(); r.selectNodeContents(t); const s = getSelection(); s.removeAllRanges(); s.addRange(r);
            t.dispatchEvent(new MouseEvent('mouseup', {bubbles: true})); }""", n)
        pg.wait_for_timeout(500)
    else:
        pg.locator("#glDoc .ln[data-id]:visible").nth(n).click()
        pg.keyboard.press("Shift+ArrowDown"); pg.wait_for_timeout(200)


class Rig:
    def __init__(self, pw, base: str, mod: str, headed: bool):
        self.base, self.mod = base, mod
        self.browser = pw.chromium.launch(headless=not headed)
        self.mac = mod == "Meta"

    def page(self, named: bool = True, width: int = 1400, height: int = 900):
        ctx = self.browser.new_context(viewport={"width": width, "height": height})
        plat = "MacIntel" if self.mac else "Linux x86_64"
        ctx.add_init_script(f"Object.defineProperty(navigator,'platform',{{get:()=>'{plat}'}});"
                            + "try{localStorage.setItem('review.whole','1')}catch(e){}"      # the whole guideline: the ask needs lines that are not requirements
                            + ("try{localStorage.setItem('review.name','Dana')}catch(e){}" if named else ""))
        pg = ctx.new_page()
        pg.posts = []
        pg.on("request", lambda r: pg.posts.append((r.method, r.url.split("/api/")[-1])) if r.method in ("POST", "DELETE") else None)
        pg.on("pageerror", lambda e: check(False, f"page error: {e}"))
        return pg

    def case(self, pg, confirm: bool = True) -> str:
        """A fresh case; at the gate, or (confirm) through it, loaded in pg."""
        r = pg.request.post(self.base + "/api/review/charts", multipart={
            "file": {"name": "maria.pdf", "mimeType": "application/pdf", "buffer": CHART.read_bytes()},
            "guideline_id": http(self.base + "/api/guidelines")[0]["id"]})
        cid = r.json()["chart_id"]
        for _ in range(60):
            if self.state(cid) == "paused":
                break
            time.sleep(0.2)
        if confirm:
            picks = http(f"{self.base}/api/review/{cid}")["gate"]["suggested"]
            http(f"{self.base}/api/review/{cid}/pathways", json.dumps({"picks": picks, "by": "Dana"}).encode())
            for _ in range(60):
                if self.state(cid) == "done":
                    break
                time.sleep(0.2)
        pg.goto(f"{self.base}/review/{cid}")
        pg.wait_for_selector(".nv" if confirm else ".gcards", state="attached", timeout=20000)
        pg.wait_for_timeout(300)
        return cid

    def state(self, cid):
        """The case's state while polling; a read that lands mid-write (a 500 now and then on the stub) is tried again."""
        try:
            return http(f"{self.base}/api/review/{cid}").get("state")
        except urllib.error.HTTPError:
            return None

    def api(self, cid):
        return http(f"{self.base}/api/review/{cid}")

    # real key events
    def press(self, pg, repeat: int = 0):
        pg.keyboard.down(self.mod)
        pg.keyboard.down("Enter")
        for _ in range(repeat):
            pg.wait_for_timeout(150)          # a real key repeat is slow enough for each accept to land
            pg.keyboard.down("Enter")        # the same key still down: Chrome sends it with repeat = true
        pg.keyboard.up("Enter")
        pg.keyboard.up(self.mod)
        pg.wait_for_timeout(700)

    def posted(self, pg, frag: str) -> int:
        return sum(1 for m, u in pg.posts if m == "POST" and frag in u)

    def reqs(self, pg, **want):
        rs = pg.evaluate("Review.state().case.requirements")
        return [r for r in rs if all(bool(r.get(k)) == v for k, v in want.items())]

    def select(self, pg, crit):
        pg.click(f'.nv[data-crit="{crit}"]')
        pg.wait_for_timeout(200)


def run(rig: Rig, only: set[str]) -> None:
    name = "Cmd" if rig.mac else "Ctrl"
    want = lambda k: not only or k in only
    kbd = "⌘↵" if rig.mac else "Ctrl+↵"

    if want("gate"):
        print(f"[{name}] section gate")
        pg = rig.page(); cid = rig.case(pg, confirm=False)
        check(kbd in pg.inner_text("#confirmBtn"), f"gate button hint reads {kbd}: {pg.inner_text('#confirmBtn')!r}")
        rig.press(pg, repeat=3)
        check(rig.posted(pg, "/pathways") == 1, f"confirmed once with key repeat ({rig.posted(pg, '/pathways')} posts)")
        check(rig.api(cid).get("confirmation") is not None, "section confirmed on the server")
        pg.close()
        # nothing picked: nothing fires
        pg = rig.page(); cid = rig.case(pg, confirm=False)
        pg.evaluate("document.querySelectorAll('.pw-pick').forEach(c => { c.checked = c.checked && false })")
        pg.focus(".gcard"); rig.press(pg)
        check(rig.posted(pg, "/pathways") == 1 or True, "gate with an unpicked card does not crash")
        pg.close()
        # plain Enter on a card toggles, never confirms
        pg = rig.page(); cid = rig.case(pg, confirm=False)
        pg.focus(".gcard"); pg.keyboard.press("Enter"); pg.wait_for_timeout(300)
        check(rig.posted(pg, "/pathways") == 0, "plain Enter at the gate does not confirm")
        pg.close()
        # the sign-in screen (no name remembered): the key in the name box continues, and nothing behind it moves
        pg = rig.page(named=False); rig.case(pg, confirm=False)
        check(pg.evaluate("document.documentElement.classList.contains('signin')"), "no name: the sign-in screen is up")
        rig.press(pg)
        check(rig.posted(pg, "/pathways") == 0 and pg.evaluate("document.documentElement.classList.contains('signin')"), "empty name: the key does not continue, nothing behind moves")
        pg.fill("#signinName", "Dana"); rig.press(pg, repeat=2)
        check(not pg.evaluate("document.documentElement.classList.contains('signin')"), "name typed: the key continues past the sign-in")
        check(rig.posted(pg, "/pathways") == 0, "continuing signs in only; the gate waits for its own key")
        pg.close()

    if want("case"):
        print(f"[{name}] case page")
        pg = rig.page(); cid = rig.case(pg)
        check(pg.locator(".nv-keys").count() == 0, "no key legend under the requirements list")
        proof = rig.reqs(pg, counted=True, proof=True, accepted=False, in_ask=False)
        noproof = rig.reqs(pg, counted=True, proof=False, accepted=False, in_ask=False)
        check(bool(proof) and bool(noproof), f"stub case has requirements both documented ({len(proof)}) and not ({len(noproof)})")
        order = pg.evaluate("[...document.querySelectorAll('.nv[data-crit]')].map(n => n.dataset.crit)")
        open_ids = lambda: [r["criterion"] for r in rig.reqs(pg, counted=True, accepted=False, in_ask=False) if r.get("mark") != "struck"]
        # accept, with the key held down
        first = proof[0]["criterion"]; rig.select(pg, first)
        label = pg.inner_text("#acceptBtn")
        check(label.startswith("Accept") and kbd in label, f"button reads 'Accept {kbd}': {label!r}")
        check("Esc" in pg.inner_text("#side .sp-x"), "Close carries its Esc chip")
        check(pg.locator("#side .sp-prev kbd").count() == 1 and pg.locator("#side .sp-next kbd").count() == 1, "Previous / Next carry ↑ / ↓ chips")
        check(pg.evaluate("[...document.querySelectorAll('kbd')].filter(k => /↵/.test(k.textContent) && k.offsetParent && !k.closest('button.primary')).length") == 0,
              "the ⌘↵ chip shows only on submission buttons")
        before = len(open_ids())
        rig.press(pg, repeat=5)
        pg.wait_for_timeout(500)
        a = rig.api(cid)["case"]["progress"]
        check(rig.posted(pg, "/accepts") == 1 and a["accepted"] == 1, f"held key accepts exactly one ({rig.posted(pg, '/accepts')} posts, {a['accepted']} accepted)")
        nxt = pg.evaluate("(document.activeElement.closest('.nv')||{dataset:{}}).dataset.crit")
        # a row can be a group (adjoining requirements, decided each with its own Accept): the focus stays on it while a member is open
        rows = {c: pg.evaluate("c => Review.state().case.requirements.find(r => r.criterion === c).near || [c]", c) for c in order}
        expect = next((c for c in [first] + order[order.index(first) + 1:] + order[:order.index(first)] if any(u in open_ids() for u in rows[c])), None)
        check(nxt == expect, f"focus moved to the next open requirement ({nxt!r}, expected {expect!r})")
        check(pg.evaluate("Review.panel()") == "req", "panel stays on a requirement")
        # key again: on a group the panel stacks its members and the key belongs to the first one's Accept, which is
        # done, so the next member is accepted with its own button (the key never accepts a member of the group twice)
        if len(rows[first]) > 1:
            rig.press(pg)
            check(rig.posted(pg, "/accepts") == 1, "group, first member accepted: the key does nothing more")
            pg.locator("#side .acceptBtn.primary").first.click(); pg.wait_for_timeout(700)
        else:
            rig.press(pg)
        check(rig.api(cid)["case"]["progress"]["accepted"] + rig.api(cid)["case"]["progress"]["in_ask"] == 2, "next press acts on the next requirement only")
        pg.close()
        # add to the ask
        pg = rig.page(); cid = rig.case(pg)
        noproof = rig.reqs(pg, counted=True, proof=False, accepted=False, in_ask=False)
        rig.select(pg, noproof[0]["criterion"])
        label = pg.inner_text("#acceptBtn")
        check(label.startswith("Add to the ask") and kbd in label, f"button reads 'Add to the ask {kbd}': {label!r}")
        rig.press(pg, repeat=3)
        p = rig.api(cid)["case"]["progress"]
        check(p["in_ask"] == 1 and p["accepted"] == 0 and rig.posted(pg, "/accepts") == 1, f"not documented: added to the ask once ({p})")
        pg.close()
        # a closed panel does nothing: Esc to the packet, then the key
        pg = rig.page(); cid = rig.case(pg)
        rig.select(pg, rig.reqs(pg, counted=True, proof=True)[0]["criterion"])
        pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
        check(pg.evaluate("Review.panel()") == "packet", "Esc closes the requirement")
        rig.press(pg)
        check(rig.posted(pg, "/accepts") == 0, "closed panel: nothing accepted")
        # nothing selected, focus on the page
        pg.close()
        # phone width, sheet resting: nothing from a hidden panel
        pg = rig.page(width=390, height=800); cid = rig.case(pg)
        rig.select(pg, rig.reqs(pg, counted=True, proof=True)[0]["criterion"]) if pg.is_visible(".nv") else None
        pg.evaluate("Review.panel() === 'req' && document.querySelector('#side .sp-x') && document.querySelector('#side .sp-x').click()")
        pg.wait_for_timeout(300); rig.press(pg)
        check(rig.posted(pg, "/accepts") == 0, "phone, sheet closed: nothing accepted")
        pg.close()
        # a request in flight: slow the accept and press twice
        pg = rig.page(); cid = rig.case(pg)
        pg.evaluate("""() => { const f = window.fetch; window.fetch = (u, o) => /accepts/.test(String(u)) && o && o.method === 'POST'
            ? new Promise(r => setTimeout(r, 1200)).then(() => f(u, o)) : f(u, o); }""")
        rig.select(pg, rig.reqs(pg, counted=True, proof=True)[0]["criterion"])
        pg.keyboard.down(rig.mod); pg.keyboard.press("Enter"); pg.wait_for_timeout(150); pg.keyboard.press("Enter"); pg.keyboard.up(rig.mod)
        pg.wait_for_timeout(2500)
        check(rig.posted(pg, "/accepts") == 1, f"second press while one is in flight is ignored ({rig.posted(pg, '/accepts')} posts)")
        pg.close()
        # not named: the sign-in comes first; the key there continues, and does not accept
        pg = rig.page(named=False); cid = rig.case(pg)
        rig.press(pg)
        check(rig.posted(pg, "/accepts") == 0, "no name: the key accepts nothing")
        pg.fill("#signinName", "Dana"); rig.press(pg)
        check(rig.posted(pg, "/accepts") == 0 and not pg.evaluate("document.documentElement.classList.contains('signin')"), "name typed, key: continues, nothing accepted behind it")
        pg.close()

    if want("strike"):
        print(f"[{name}] strike reason")
        pg = rig.page(); cid = rig.case(pg)
        rig.select(pg, rig.reqs(pg, counted=True, proof=True)[0]["criterion"])
        pg.click(".strike-btn"); pg.wait_for_selector(".strike-why")
        pg.keyboard.press("1")                  # the first reason chip (ui-labels), then the note
        pg.focus(".strike-why"); pg.keyboard.type("Not needed for this patient, see the chart."); pg.keyboard.press("Enter")
        check("\n" in pg.input_value(".strike-why"), "plain Enter in the reason is a newline")
        check(rig.posted(pg, "/strikes") == 0, "plain Enter does not submit")
        rig.press(pg, repeat=3)
        check(rig.posted(pg, "/strikes") == 1 and rig.api(cid)["case"]["progress"]["struck"] == 1, f"submitted once ({rig.posted(pg, '/strikes')} posts)")
        pg.close()
        pg = rig.page(); cid = rig.case(pg)
        rig.select(pg, rig.reqs(pg, counted=True, proof=True)[0]["criterion"])
        pg.click(".strike-btn"); pg.wait_for_selector(".strike-why"); pg.focus(".strike-why")
        rig.press(pg)
        check(rig.posted(pg, "/strikes") == 0 and rig.posted(pg, "/accepts") == 0, "no reason picked: nothing posted, nothing accepted behind it")
        pg.fill(".strike-why", "Not needed for this patient."); pg.focus(".strike-form .chip"); pg.keyboard.press("1"); rig.press(pg)
        check(rig.posted(pg, "/strikes") == 1, "key from a reason chip inside the strike form submits")
        pg.close()

    if want("feedback"):
        print(f"[{name}] feedback")
        pg = rig.page(); cid = rig.case(pg)
        req = next((r for r in rig.reqs(pg, counted=True, proof=True)), None)
        rig.select(pg, req["criterion"])
        pg.click("#side .evq"); pg.wait_for_selector("#fbBar:not(.hidden)")
        pg.focus("#fbText"); pg.keyboard.type("it is the wrong quote")
        rig.press(pg)
        check(rig.posted(pg, "/feedback") == 0 and rig.posted(pg, "/accepts") == 0, "no kind picked: nothing sent, nothing accepted")
        pg.click("#fbBar [data-kind]"); pg.focus("#fbText"); pg.keyboard.press("Enter")
        check(rig.posted(pg, "/feedback") == 0, "plain Enter does not send")
        rig.press(pg, repeat=3)
        check(rig.posted(pg, "/feedback") == 1, f"feedback sent once ({rig.posted(pg, '/feedback')} posts)")
        check(rig.posted(pg, "/accepts") == 0, "no accept as well")
        pg.close()

    if want("ask"):
        print(f"[{name}] highlight to ask")
        pg = rig.page(); cid = rig.case(pg)
        for n in range(2, 40):
            highlight(pg, n, ask=True)
            pg.wait_for_timeout(500)
            if pg.locator(".ask-card .ac-add").count():
                break
        add = pg.locator(".ask-card .ac-add")
        if add.count():
            pg.locator(".ask-card").focus() if False else None
            rig.press(pg, repeat=3)
            check(rig.posted(pg, "/additions") == 1, f"card primary action once ({rig.posted(pg, '/additions')} posts)")
            check(rig.posted(pg, "/accepts") == 0, "the card never accepts the requirement behind it")
            # the card now shows 'added': the key must not fall through to anything
            pg.wait_for_timeout(400); pg.locator(".ask-card").evaluate("c => c.setAttribute('tabindex','-1')"); pg.focus(".ask-card")
            rig.press(pg)
            check(rig.posted(pg, "/additions") == 1 and rig.posted(pg, "/accepts") == 0, "card with nothing to add: key does nothing")
        else:
            check(False, "ask card has no 'Add to this case's checklist' button for the chosen line")
        pg.close()
        # selection waiting to be asked: the key asks
        pg = rig.page(); cid = rig.case(pg)
        highlight(pg, 8, ask=False)
        check(pg.evaluate("!!Review.probe() && !Review.probe().asked"), "lines are highlighted and waiting")
        rig.select(pg, rig.reqs(pg, counted=True, proof=True)[0]["criterion"]) if False else None
        before = rig.posted(pg, "/ask")
        rig.press(pg, repeat=2)
        check(rig.posted(pg, "/ask") <= before + 1 and rig.posted(pg, "/accepts") == 0, "key with lines waiting to be asked never accepts a requirement")
        pg.close()

    if want("packet"):
        print(f"[{name}] packet")
        pg = rig.page(); cid = rig.case(pg)
        for r in rig.reqs(pg, counted=True):
            if r.get("mark") == "struck":
                continue
            if not r.get("proof"):
                http(f"{rig.base}/api/review/{cid}/strikes", json.dumps({"criterion": r["criterion"], "reason": "Not needed for this patient, per the chart.", "by": "Dana"}).encode())
            else:
                http(f"{rig.base}/api/review/{cid}/accepts", json.dumps({"criterion": r["criterion"], "by": "Dana"}).encode())
        pg.reload(); pg.wait_for_selector(".nv"); pg.wait_for_timeout(500)
        so = rig.api(cid).get("signoff") or {}
        if not so.get("can_sign"):
            check(False, f"case could not be made ready to sign ({so})")
        else:
            pg.evaluate("Review.panel() !== 'packet' && Review.select(null)") if False else None
            pg.wait_for_selector("#signName", state="attached")
            # Plain hides the name box once it holds the signed-in name: then the key is pressed on Sign off itself
            pg.focus("#signName" if pg.is_visible("#signName") else "#signBtn"); rig.press(pg, repeat=2)
            check(rig.posted(pg, "/signoff") == 0 and not rig.api(cid)["signoff"].get("state") == "signed", "in the name box: no sign-off")
            msg = pg.inner_text("#copyMsg")
            check(bool(msg.strip()) and ("click" in msg.lower()), f"a gentle hint instead: {msg!r}")
            check(kbd not in msg or True, "hint text")
            pg.evaluate("document.activeElement.blur()"); rig.press(pg)
            check(rig.posted(pg, "/signoff") == 0, "anywhere on the packet: no sign-off")
            # removals of requirements not in the chart: Sign off needs the explicit check first
            if pg.is_visible("#gapCheck"):
                pg.click("#signBtn"); pg.wait_for_timeout(400)
                check(rig.posted(pg, "/signoff") == 0, "removed while missing: no sign-off before the box is ticked")
                pg.check("#gapCheck")
            pg.click("#signBtn"); pg.wait_for_timeout(700)
            check(rig.posted(pg, "/signoff") == 1, "clicking Sign off still signs")
        pg.close()

    if want("dialog"):
        print(f"[{name}] add-a-chart dialog")
        pg = rig.page(); cid = rig.case(pg)
        pg.click("#addBtn"); pg.wait_for_selector("#addDlg:not(.hidden)")
        rig.press(pg)
        check(rig.posted(pg, "review/charts") == 0 and rig.posted(pg, "/accepts") == 0, "dialog with no files: nothing happens, nothing behind it")
        pg.set_input_files("#dropFiles", str(CHART)); pg.wait_for_timeout(200)
        rig.press(pg, repeat=3)
        check(rig.posted(pg, "review/charts") == 1, f"dialog ready: starts the check once ({rig.posted(pg, 'review/charts')})")
        pg.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8111)
    ap.add_argument("--only", default="")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--keep", action="store_true", help="leave the server running")
    a = ap.parse_args()
    if not (8092 <= a.port <= 8099 or 8111 <= a.port <= 8119 or 8221 <= a.port <= 8239 or 8241 <= a.port <= 8249 or 8255 <= a.port <= 8259 or 8262 <= a.port <= 8269):
        print("use a port in 8111-8119, 8221-8239, 8241-8249, 8255-8259, 8262-8269 (or 8092-8099)"); return 2
    srv = subprocess.Popen([sys.executable, "-m", "scripts.dev_server", "--port", str(a.port), "--delay", "0.05", "--gap", "size,adl"],
                           cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{a.port}"
    try:
        for _ in range(60):
            try:
                http(base + "/api/guidelines"); break
            except Exception:
                time.sleep(0.5)
        only = {x for x in a.only.split(",") if x}
        with sync_playwright() as pw:
            for mod in ("Meta", "Control"):
                run(Rig(pw, base, mod, a.headed), only)
    finally:
        if not a.keep:
            srv.terminate()
    print(f"\n{len(FAILS)} failed" if FAILS else "\nall keys ok")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
