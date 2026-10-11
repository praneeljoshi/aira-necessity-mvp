/* Policy health: the page for one guideline (static/health.html). Draws GET /api/health/<id> as six short sections,
   each shown only when it has something in it. Every number is a count the server computed from stored cases;
   this file only lays them out. No framework, no build step. */
(function () {
'use strict';
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const day = iso => { const m = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? `${MONTHS[+m[2] - 1]}\u00a0${+m[3]}` : ''; };
const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + 's')}`;
const MIN = 5;                 // as app/health.MIN_CASES: fewer checklists than this read as a small sample
const HOT = 1 / 3;             // a rate at or above this, on enough cases, is where the payer should look

const gid = decodeURIComponent(location.pathname.replace(/\/+$/, '').split('/').pop() || '');
const caseLink = (id, text = 'Example') => id ? `<a class="ex" href="/review/${encodeURIComponent(id)}">${esc(text)}</a>` : '';

// the requirement's short label; its own words open on hover or focus (and in place on a phone, where there is no hover)
// (only when the label is shorter than the words: said once otherwise)
const bare = w => String(w || '').replace(/\s+/g, ' ').trim().replace(/[.;:,]+$/, '').toLowerCase();
const req = x => bare(x.label) === bare(x.words) ? `<span class="req plain">${esc(x.label)}</span>`
  : `<span class="req" tabindex="0" aria-describedby="w-${esc(x._k)}">${esc(x.label)}</span>`
  + `<span class="words" role="tooltip" id="w-${esc(x._k)}">“${esc(x.words)}”</span>`;
// a long list shows its first rows; the rest open in place
const SHOW = 5;
const rows = (list, row) => `<ol class="rows">${list.map((x, i) => `<li class="row${i >= SHOW ? ' more' : ''}"${i >= SHOW ? ' hidden' : ''}>${row(x)}</li>`).join('')}</ol>`
  + (list.length > SHOW ? `<button class="link more-btn" type="button">${list.length - SHOW} more</button>` : '');
const where = x => x.section ? `<div class="sub">${esc(x.section)}${x.page != null ? ' · page ' + esc(x.page) : ''}</div>` : '';
// "25 of 38" with a hairline meter under it; ink only when the rate is high on enough cases
function rate(k, n, unit = n === 1 ? 'case' : 'cases') {
  const hot = n >= MIN && k / n >= HOT;
  const w = n ? Math.max(2, Math.round(100 * k / n)) : 0;
  return `<div class="num${hot ? ' hot' : ''}"><span><b>${k}</b> of ${n} ${esc(unit)}</span>`
    + `<span class="meter" aria-hidden="true"><i style="width:${w}%"></i></span></div>`;
}
const notes = list => (list || []).length ? `<ul class="notes">${list.map(n => `<li>“${esc(n.text)}”${n.count > 1 ? `<span class="x">× ${n.count}</span>` : ''}</li>`).join('')}</ul>` : '';

function section(id, title, dek, body) {
  return `<section id="${id}" aria-labelledby="${id}-h"><h2 id="${id}-h">${esc(title)}</h2>${dek ? `<p class="dek">${dek}</p>` : ''}${body}</section>`;
}

function render(d) {
  const g = d.guideline, h = d.headline;
  let k = 0;
  for (const list of [d.removed, d.missing, d.outside]) for (const x of list) x._k = k++;
  document.title = `Policy health · ${g.name || g.id}`;
  const kicker = ['Policy health', g.issuer || g.payer, g.number].filter(Boolean).join(' · ');
  const when = d.span ? (d.span.from === d.span.to ? day(d.span.from) : `${day(d.span.from)} – ${day(d.span.to)}`) : '';
  let html = `<p class="kicker">${esc(kicker)}</p><h1>${esc(g.name || g.id)}</h1>`;
  if (!h.cases) {
    $('#page').innerHTML = html + `<p class="lede">No case has been checked against this policy yet. Its health shows here once coordinators have worked a few.</p>`;
    return;
  }
  html += `<p class="lede">What coordinators found while checking ${plural(h.cases, 'request')} against this policy${when ? `, <span class="nw">${esc(when)}</span>` : ''}.</p>`;
  html += `<div class="act"><button class="primary" id="copyBtn" type="button">Copy as a note to the payer</button>`
    + `<button class="link" id="peekBtn" type="button" aria-expanded="false" aria-controls="noteBox">See the note</button><span id="copyMsg" class="msg" role="status"></span></div>`
    + `<pre class="note" id="noteBox" hidden>${esc(d.note)}</pre>`;

  // 1. the headline: four plain numbers
  const stats = [[h.cases, 'checked'], [h.signed, 'signed off'], [h.waiting, 'waiting on the surgeon']];
  if (h.to_signoff_say) stats.push([h.to_signoff_say, 'typical time to sign-off', `The median from upload to sign-off, over ${plural(h.n_timed, 'signed case')}.`]);
  html += `<dl class="stats">${stats.map(([n, l, t]) => `<div${t ? ` title="${esc(t)}"` : ''}><dt>${esc(l)}</dt><dd>${esc(n)}</dd></div>`).join('')}</dl>`;

  // 2. requirements coordinators remove
  if (d.removed.length) html += section('removed', 'Requirements coordinators remove',
    'Struck from a case as not needed, and why. Often a sign the line is not a clinical requirement.',
    rows(d.removed, x => `<div class="what">${req(x)}${where(x)}`
      + `<div class="reasons">${x.reasons.map((r, i) => `<span${i ? '' : ' class="top"'}>${esc(r.label)} <b>${r.count}</b></span>`).join('')}</div>`
      + `${notes(x.notes)}</div><div class="side">${rate(x.count, x.cases)}${caseLink(x.example)}</div>`));

  // 3. requirements most often missing from charts
  if (d.missing.length) html += section('missing', 'Requirements most often missing from cases',
    'Not in the case when first checked, or added to the ask to the surgeon. What clinics can document better.',
    rows(d.missing, x => `<div class="what">${req(x)}${where(x)}`
      + (x.in_ask ? `<div class="reasons"><span>Added to the ask <b>${x.in_ask}</b></span></div>` : '')
      + `</div><div class="side">${rate(x.count, x.cases)}${caseLink(x.example)}</div>`));

  // 4. things a chart can't show
  if (d.outside.length) html += section('outside', 'Things a case can’t show',
    'Confirmed outside the case by the coordinator. Wording the payer could clarify.',
    rows(d.outside, x => `<div class="what">${req(x)}${where(x)}<p class="why">${esc(x.why)}</p></div>`
      + `<div class="side"><div class="num"><span><b>${x.cases}</b> ${x.cases === 1 ? 'case' : 'cases'}</span></div>`
      + `<div class="fine">${x.confirmed} confirmed${x.struck ? ` · ${x.struck} removed` : ''}</div>${caseLink(x.example)}</div>`));

  // 5. sections that get confused
  if (d.confused.length) {
    const moved = d.confused.reduce((a, x) => a + x.count, 0);
    html += section('confused', 'Indications that get confused',
      `${moved} of ${d.confirmations} section confirmations went to a different section than the one suggested.`,
      rows(d.confused, x => `<div class="what"><div class="pair"><span class="${x.none_suggested ? 'none' : ''}">${esc(x.from)}</span>`
        + `<span class="arrow" aria-label="confirmed as">→</span><span>${esc(x.to)}</span></div></div>`
        + `<div class="side"><div class="num"><span><b>${x.count}</b> ${x.count === 1 ? 'case' : 'cases'}</span></div>${caseLink(x.example)}</div>`));
  }

  // 6. lines coordinators flagged
  if (d.flagged.length) html += section('flagged', 'Lines coordinators flagged',
    'Feedback filed on the policy’s own lines, quoted as printed.',
    rows(d.flagged, x => `<div class="what"><div class="kind">${esc(x.say)}</div>`
      + `<blockquote>${esc(x.quote)}</blockquote><div class="sub">page ${esc(x.page)}</div>`
      + notes(x.notes)
      + (x.proposals || []).map(p => `<p class="prop"><span>Proposed</span> “${esc(p.text)}”</p>`).join('')
      + `</div><div class="side"><div class="num"><span><b>${x.count}</b> ${x.count === 1 ? 'time' : 'times'}</span></div>${caseLink(x.example)}</div>`));

  // footer: where the numbers come from, and demo data said plainly
  html += `<footer><p>Counted from what coordinators recorded on each case: removals and their reasons, asks, section confirmations, sign-offs and line feedback. Nothing here names a patient.</p>`
    + (d.demo ? `<p class="demo"><b>Demo data.</b> ${d.demo.cases === d.demo.of ? `All ${plural(d.demo.cases, 'case')}` : `${d.demo.cases} of the ${d.demo.of} cases`} behind these numbers are synthetic, seeded for this demonstration.</p>` : '')
    + `</footer>`;

  $('#page').innerHTML = html;
  $('#copyBtn').onclick = () => copy(d.note);
  document.querySelectorAll('.more-btn').forEach(b => b.onclick = () => {
    b.previousElementSibling.querySelectorAll('.row.more').forEach(r => { r.hidden = false; }); b.remove(); });
  $('#peekBtn').onclick = e => { const box = $('#noteBox'), open = box.hidden; box.hidden = !open;
    e.currentTarget.setAttribute('aria-expanded', String(open)); e.currentTarget.textContent = open ? 'Hide the note' : 'See the note'; };
}

async function copy(text) {
  const msg = $('#copyMsg');
  let ok = false;
  try { await navigator.clipboard.writeText(text); ok = true; } catch {
    const t = document.createElement('textarea'); t.value = text; t.setAttribute('readonly', ''); t.style.position = 'fixed'; t.style.opacity = '0';
    document.body.appendChild(t); t.select(); try { ok = document.execCommand('copy'); } catch {} t.remove();
  }
  msg.textContent = ok ? 'Copied. It names no patient.' : 'Could not copy; the note is below.';
  if (!ok) { $('#noteBox').hidden = false; $('#peekBtn').textContent = 'Hide the note'; }
  clearTimeout(copy.t); copy.t = setTimeout(() => { msg.textContent = ''; }, 4000);
}

async function load() {
  const page = $('#page');
  try {
    const r = await fetch('/api/health/' + encodeURIComponent(gid));
    if (r.status === 404) { page.innerHTML = '<p class="kicker">Policy health</p><h1>No such policy on file</h1><p class="lede"><a href="/experimental">Pick one on the experimental index</a>.</p>'; return; }
    if (!r.ok) throw new Error(r.statusText);
    render(await r.json());
  } catch (e) {
    page.innerHTML = `<p class="kicker">Policy health</p><h1>Something went wrong reading the cases</h1><p class="lede">${esc(e.message)}. Reload to try again.</p>`;
  } finally { page.removeAttribute('aria-busy'); }
}
load();

// the theme: Soft, Light or Dark, the same switch and key as the review page
(function () {
  const b = document.getElementById('themeBtn'), root = document.documentElement;
  const ORDER = ['soft', 'light', 'dark'], NAME = { soft: 'Soft', light: 'Light', dark: 'Dark' };
  const cur = () => ORDER.includes(root.dataset.theme) ? root.dataset.theme : 'soft';
  const show = () => { const t = cur(), n = ORDER[(ORDER.indexOf(t) + 1) % ORDER.length];
    b.textContent = NAME[t]; b.setAttribute('aria-label', `Theme: ${NAME[t]}. Switch to ${NAME[n]}`); b.title = `Theme: ${NAME[t]} · click for ${NAME[n]}`; };
  b.onclick = () => { const t = ORDER[(ORDER.indexOf(cur()) + 1) % ORDER.length]; root.dataset.theme = t;
    try { localStorage.setItem('review.theme', t); } catch {} show(); };
  show();
})();
})();
