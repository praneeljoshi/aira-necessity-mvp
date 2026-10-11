/* The proof thread (Plain and Clinic, desk-width screens). The product's claim is that the check ties a line of
   the payer's policy to proof in the chart; this draws that tie. While a requirement is open, a quiet bracket in the
   sheet's right margin spans its words, and a fine thread runs from the bracket to the chart quote on the slip
   beside it, the way a reviewer would pencil a margin note. When the chart has nothing for it, the thread is dashed
   and ends at the ruling ("not in the chart yet"): an unproven tie looks unproven. Drawn in one fixed SVG above
   the page, never catching the pointer; re-drawn on scroll, resize and whenever the page changes what is open.
   No motion beyond a short draw-on when the open requirement changes (none with reduced motion). */
(function () {
'use strict';
const root = document.documentElement;
const NS = 'http://www.w3.org/2000/svg';
const on = () => false;   // off: a fixed layer floats over the page while it scrolls; Plain and Clinic carry their washes on the words themselves
const still = matchMedia('(prefers-reduced-motion: reduce)');
let svg, bracket, thread, dotA, dotB, raf = 0, lastKey = '';

function setup(){
  if (svg) return;
  svg = document.createElementNS(NS, 'svg'); svg.id = 'proofThread'; svg.setAttribute('aria-hidden', 'true');
  const mk = (tag, cls) => { const e = document.createElementNS(NS, tag); e.setAttribute('class', cls); svg.appendChild(e); return e; };
  bracket = mk('path', 'pt-bracket'); thread = mk('path', 'pt-thread'); dotA = mk('circle', 'pt-dot'); dotB = mk('circle', 'pt-dot pt-end');
  dotA.setAttribute('r', '2'); dotB.setAttribute('r', '2.6');
  document.body.appendChild(svg);
}
function hide(){ if (svg) svg.classList.remove('show'); lastKey = ''; }

function draw(){
  raf = 0;
  if (!on()) return hide();
  const marks = [...document.querySelectorAll('#glDoc mark.q.sel')];
  const side = document.getElementById('side'), doc = document.querySelector('#glDoc .doc');
  if (!marks.length || !side || !doc || side.offsetParent === null) return hide();
  // the words: the vertical extent of every line the open requirement's marks sit on
  let top = Infinity, bottom = -Infinity;
  for (const m of marks) for (const r of m.getClientRects()) { if (r.height < 4) continue; top = Math.min(top, r.top); bottom = Math.max(bottom, r.bottom); }
  if (!isFinite(top) || bottom < 8 || top > innerHeight - 8) return hide();
  // the end on the slip: the first chart quote, or the ruling when the chart has nothing
  const quote = side.querySelector('.evq'), ruling = side.querySelector('.sp-ruling');
  const target = quote || ruling; if (!target) return hide();
  const tr = target.getBoundingClientRect(), dr = doc.getBoundingClientRect();
  if (tr.bottom < 0 || tr.top > innerHeight) return hide();
  setup();
  const bx = Math.round(dr.right - 18), t = Math.max(6, top + 2), b = Math.min(innerHeight - 6, bottom - 2), my = (t + b) / 2;
  const qx = Math.round(tr.left - 7), qy = Math.round(tr.top + (quote ? 13 : tr.height / 2));
  bracket.setAttribute('d', `M ${bx - 5} ${t} H ${bx} V ${b} H ${bx - 5}`);
  const k = Math.max(24, (qx - bx) * 0.55);
  thread.setAttribute('d', `M ${bx} ${my} C ${bx + k} ${my}, ${qx - k} ${qy}, ${qx} ${qy}`);
  dotA.setAttribute('cx', bx); dotA.setAttribute('cy', my); dotB.setAttribute('cx', qx); dotB.setAttribute('cy', qy);
  svg.classList.toggle('unproven', !quote);
  svg.classList.add('show');
  // a short draw-on when a different requirement opens
  const key = marks[0].dataset.crit + '|' + (quote ? quote.dataset.span || 'q' : 'none');
  if (key !== lastKey) {
    lastKey = key;
    if (!still.matches && thread.animate && !svg.classList.contains('unproven')) {
      const len = thread.getTotalLength ? thread.getTotalLength() : 300;
      thread.animate([{ strokeDasharray: `${len} ${len}`, strokeDashoffset: len }, { strokeDasharray: `${len} ${len}`, strokeDashoffset: 0 }],
        { duration: 240, easing: 'cubic-bezier(.2,.7,.2,1)' });
      dotB.animate([{ opacity: 0 }, { opacity: 0, offset: .7 }, { opacity: 1 }], { duration: 260 });
    }
  }
}
function need(){ if (!raf) raf = requestAnimationFrame(draw); }

addEventListener('scroll', need, { passive: true, capture: true });
addEventListener('resize', need);
document.addEventListener('DOMContentLoaded', () => {
  const main = document.getElementById('main'); if (!main) return;
  new MutationObserver(need).observe(main, { subtree: true, childList: true, attributes: true, attributeFilter: ['class'] });
  new MutationObserver(need).observe(root, { attributes: true, attributeFilter: ['data-style', 'data-theme', 'class'] });
});
if (document.fonts && document.fonts.ready) document.fonts.ready.then(need);
window.ProofThread = { refresh: need };
})();
