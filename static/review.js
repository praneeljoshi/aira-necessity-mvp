/* The coordinator's review page: upload, the section gate, then the case. The case page IS the guideline: the
   confirmed section line by line as printed (app/review.py's `tree`, drawn as static/tree.js draws it), each
   requirement's quoted words wrapped in <mark class="q"> with its status on the block's first line, and the chart's
   evidence attached directly under the requirement it belongs to (the exact quote, its note, date and page; for /
   against distinguished). There is no chart column. Feedback on a guideline line (or a range) and on an evidence
   quote. A requirement can be removed for this case ("Not needed for this case", a reason required; struck through
   in place with who and why, "Put it back" undoes it; the result is decided again). A ready case reads "Ready for
   sign-off" until a person signs it off (name remembered in localStorage); only then "Ready to submit" with the
   packet final. The case is three columns: the requirements (↑/↓, j/k), the guideline (never moves), and a side
   panel (a bottom sheet on narrow screens) that shows the packet being built, or one requirement's ruling and chart
   quotes with Accept (⌘/Ctrl+Enter; Undo), or the answer for selected lines. Accepting builds the case: a slim
   summary fills ("4 of 6 accepted · 1 to ask"), sign-off opens only when every requirement is accepted or struck
   and nothing is left to ask, the packet and the message to the surgeon are assembled from accepted items.
   Highlight to ask: select any lines of the guideline (the confirmed section, or "The rest of the guideline") and
   the selection snaps to whole lines; the panel gives the ruling, one chart quote and "+ N more", the logic as a
   small checklist, and "Add to this case's checklist" (POST /api/review/{id}/ask, .../additions). Lines asked about
   keep a faint mark in the margin. Shift + arrows extend from the line last clicked, Enter asks, Esc closes.
   Looks live in static/review-styles/ (Marker, the default, draws its highlighter with static/review-marks.js;
   Classic is the look before it); behaviour is the same in every style.
   No framework, no build step. Data: GET /api/review/{chart_id}.
   Vocabulary rule: outside the "How this was decided" fold the page says requirement / documented / section /
   lines, never the internals' words. CSS classes and data attributes are not the target. */
(function () {
'use strict';
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
// a request that never reached the server (offline, the server down) reads as one calm sentence, status 0
const UNREACHABLE = "Can't reach the server; nothing was saved.";
const api = async (path, opts={}) => {
  let r, t;
  try { r = await fetch('/api' + path, opts); t = await r.text(); }
  catch { const e = new Error(UNREACHABLE); e.status = 0; throw e; }
  let j; try { j = JSON.parse(t) } catch { j = { detail: t } }
  if (!r.ok) { const e = new Error(j.detail || r.statusText); e.status = r.status; throw e; } return j;
};
const post = (path, body) => api(path, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
// Fun mode is gone (the owner's call): forget its old setting
try { localStorage.removeItem('review.fun'); localStorage.removeItem('review.fun.sound'); } catch {}

// ------------------------------------------------------------------ words and marks (as index.html / tree.js)
// the rail's lanes: where each case is in the coordinator's work, with counts. A case opens where it needs her: the
// gate, or its first requirement not yet accepted (or not yet in the ask)
const QUEUE = {
  PAUSED:  { title:'Waiting for you',     g:'g-you'   },
  RUNNING: { title:'Checking now',        g:'g-wait'  },
  ASK:     { title:'In the ask',          g:'g-needs' },
  SIGNOFF: { title:'Ready for sign-off',  g:'g-ready' },
  READY:   { title:'Signed off',          g:'g-ready' },
  LOOK:    { title:'Needs a look',        g:'g-no'    },
};
const ORDER = ['PAUSED','RUNNING','ASK','SIGNOFF','READY','LOOK'];
const WAITS = ['NOT_APPLICABLE', 'CANT_CHECK'];
const queueOf = o => {
  if (o.queue === 'paused') return 'PAUSED';
  if (o.queue === 'running') return 'RUNNING';
  if (o.queue === 'failed') return 'LOOK';
  if (o.queue === 'ready' || o.signoff === 'needed' || o.signoff === 'signed') return o.signoff === 'signed' ? 'READY' : 'SIGNOFF';
  if (o.in_ask) return 'ASK';
  return 'LOOK';                     // something to look at, not covered, can't check, doesn't apply
};
// "3 h", "2 days": how long something has been waiting on the surgeon
const since = iso => { if (!iso) return ''; const h = (Date.now() - new Date(iso)) / 36e5; return h < 1 ? 'under 1 h' : h < 36 ? Math.round(h) + ' h' : Math.round(h / 24) + ' days'; };
const STATE = {
  MET:          { v:'v-ready', verdict:'Ready to submit.',                                        box:'ready' },
  INSUFFICIENT: { v:'v-needs', verdict:n=>`Ask ${n} for something first.`,                        box:'needs' },
  NOT_MET:      { v:'v-needs', verdict:n=>`Review with ${n} before submitting.`,                  box:'needs' },
  NOT_COVERED:  { v:'v-needs', verdict:n=>`Review with ${n}: the payer lists this as not covered.`, box:'no' },
  NOT_APPLICABLE: { v:'v-wait', verdict:"This guideline doesn't apply.",                          box:'' },
  CANT_CHECK:   { v:'v-wait', verdict:"Can't check this one against this guideline.",             box:'' },
};
// the pipeline finds evidence; only a person's Accept earns a check mark. What the chart appears to show reads
// neutrally ("Evidence found", a plain dot), never a green ✓ or "Documented", until someone accepts it
const MARK = {
  documented:['•','m-ev'], missing:['–','m-q'], contradicted:['✗','m-n'], not_needed:['○','m-o'], other_option:['○','m-o'],
  confirm:['?','m-q'], clear:['•','m-ev'], applies:['✗','m-n'], unclear:['?','m-q'], part_shown:['✗','m-n'], part_clear:['•','m-ev'],
  not_covered:['✗','m-n'], unchecked:['○','m-o'], struck:['—','m-o'],
};
const EVIDENCE_SAY = { documented: 'Evidence found', clear: "Evidence it doesn't apply", part_clear: 'Evidence this part is ruled out' };
const sayOf = (mark, say) => EVIDENCE_SAY[mark] || say || '';
const QUIET = ['not_needed', 'other_option', 'confirm', 'struck'];  // marks that carry no chart quotes
const KINDS = {
  should_be_requirement: 'This should be a requirement', not_a_requirement: 'This is not a requirement',
  logic_wrong: 'The logic here is wrong', edit: 'Edit',
  wrong_evidence: 'Wrong evidence', evidence_elsewhere: 'This evidence is about something else', is_evidence: 'This is the evidence',
};
// the name of the person using the page, for sign-off and removals; remembered in this browser only
const NAME_KEY = 'review.name';
const myName = () => { try { return (localStorage.getItem(NAME_KEY) || '').slice(0, 60); } catch { return ''; } };
const NAME_MAX = 60;                           // as the server keeps it (app/signoff.NAME_MAX)
const keepName = n => { n = String(n || '').slice(0, NAME_MAX); try { if (n) localStorage.setItem(NAME_KEY, n); } catch {} const f = document.getElementById('meShown'); if (f && n) f.textContent = n; };
const GL_KINDS = ['should_be_requirement', 'not_a_requirement', 'logic_wrong', 'edit'], CH_KINDS = ['wrong_evidence', 'evidence_elsewhere'];
const SG = { waiting:'○', running:'●', done:'✓', needs_person:'!', failed:'✗', skipped:'–' };
const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const fmtDate = iso => { if (!iso) return ''; const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/); if (!m) return iso; return `${MONTHS[+m[2]-1]} ${+m[3]}, ${m[1]}`; };
const surgeonName = s => s ? `Dr. ${s.replace(/^Dr\.?\s*/i,'').split(',')[0].trim().split(' ').pop()}` : 'the surgeon';
const glLabel = g => g ? `${g.payer || ''} ${g.guideline_number || g.title || ''}`.trim() : '';
// a guideline's own name (app/titles.py): its title, with "Florida Blue · Medical Coverage Guideline 02-33000-31"
// as a small line above it, and "Florida Blue 02-33000-31" where one short mention fits; the file name only when
// the document's first lines name nothing
const glTitle = g => (g && (g.name || g.title)) || 'the guideline';
const glKicker = g => g ? [g.issuer || g.payer, g.number].filter(Boolean).join(' · ') : '';
const glShort = g => g ? [g.issuer || g.payer, (g.number || '').split(' ').pop()].filter(Boolean).join(' ') || glTitle(g) : '';
const glById = id => guidelines.find(g => g.id === id) || null;
const tidy = t => String(t).replace(/\s{3,}/g, ' · ').replace(/\s+/g, ' ').trim();
const trimDot = w => String(w || '').replace(/\.$/, '');
function secs(a, b){ if (!a || !b) return ''; const s = (new Date(b) - new Date(a)) / 1000; return s < 1 ? '<1 s' : s < 60 ? Math.round(s) + ' s' : Math.round(s / 60) + ' min'; }
// "Visit Date: September 30, 2025 | Attending: Dr. … | Type: Follow-Up" -> "Follow-Up visit, September 30, 2025" (as tree.js)
function prettyHeading(h){
  if (!h) return '';
  return h.split(' › ').map(part => {
    const m = part.match(/^Visit Date:\s*([^|]+?)\s*(?:\|.*?)?(?:\|\s*Type:\s*(.+))?$/i);
    if (m) return (m[2] ? m[2].trim() + ' visit, ' : 'Visit of ') + m[1].trim();
    return part.replace(/^\d+\.\s+/, '').replace(/\b([A-Z]{2,})(?=[\sA-Z&/-]*$)/g, w => w[0] + w.slice(1).toLowerCase());
  }).join(' › ');
}

const MOD = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent) ? '⌘' : 'Ctrl+';   // the accept key as this keyboard writes it
// the chips written into review.html (Check, Continue) say the key as this keyboard writes it too
document.querySelectorAll('kbd.mod-enter').forEach(k => { k.textContent = MOD + '↵'; });
// ------------------------------------------------------------------ state
let orders = [], guidelines = [], current = null, doc = null, pollTimer = null;
let selectedCrit = null;                       // the requirement the page is focused on
let fbSel = null;                              // guideline: {side:'guideline', ids:[g…], anchor}  evidence: {side:'chart', crit, span, lines:[r…]}
let fbKind = null;
let lineCrits = {}, reqById = {}, blocks = {}, glOrder = [], pwNames = {}, pwLabels = {};
let probe = null, askSeq = 0, askTimer = null;   // highlight to ask: the snapped lines, the call in flight
let linePage = {};                             // guideline line id -> its page, to name lines by page
let navOrder = [], panelMode = 'packet', anchorLine = null, lastAsk = null, landNext = false;  // the navigator, what the side panel shows
// the middle column: the guideline as printed, or the same decision as an outline ("Guideline | Tree", key t).
// ?view=tree opens the tree (a link that can be sent); otherwise the view last chosen in this browser
const VIEW_KEY = 'review.view';
const viewParam = () => { try { const v = new URLSearchParams(location.search).get('view'); return v === 'tree' || v === 'guideline' ? v : null; } catch { return null; } };
let view = viewParam() || (() => { try { return localStorage.getItem(VIEW_KEY) === 'tree' ? 'tree' : 'guideline'; } catch { return 'guideline'; } })();
let treeOrder = [];                            // the tree's leaves in reading order (↑/↓ in the tree view)

// ------------------------------------------------------------------ rail
// "Guidelines on file" is folded under its heading ("Guidelines on file · N") unless the person opened it
const GL_OPEN_KEY = 'review.guidelines';
function glOpen(open){
  if (open != null) { try { if (open) localStorage.setItem(GL_OPEN_KEY, 'open'); else localStorage.removeItem(GL_OPEN_KEY); } catch {} }
  let is = false; try { is = localStorage.getItem(GL_OPEN_KEY) === 'open'; } catch {}
  const b = $('#glToggle'), l = $('#glList'); if (!b || !l) return is;
  b.setAttribute('aria-expanded', String(is)); l.hidden = !is;
  return is;
}
async function loadGuidelines(){
  guidelines = await api('/guidelines');
  const n = $('#glCount'); if (n) n.textContent = '· ' + guidelines.length;
  glOpen();
  $('#glList').className = guidelines.length ? '' : 'empty';
  $('#glList').innerHTML = guidelines.length
    ? guidelines.map(g => `<div class="glrow"><div><b>${esc(glTitle(g))}</b><span>${esc(glKicker(g))}</span></div></div>`).join('')
    : 'None yet. Add one with the first case.';
  renderDlgGuidelines();
}
async function loadOrders(){
  orders = await api('/orders');
  const groups = {};
  for (const o of orders) (groups[queueOf(o)] ||= []).push(o);
  let html = '';
  for (const k of ORDER) if (groups[k]) html += group(QUEUE[k].title, QUEUE[k].g, groups[k], k);
  $('#groups').innerHTML = html || '<div class="empty">No cases yet.</div>';
  $$('.row').forEach(b => b.onclick = () => { landNext = true; go(b.dataset.id); });
}
function group(title, cls, list, lane){
  return `<div class="group" data-lane="${esc(lane)}"><h2 class="${cls}" data-title="${esc(title)}" title="${esc(title)}: ${list.length}">${esc(title)} <button type="button" class="n lane-n" data-tip="${esc(title)}: ${list.length}" aria-label="${esc(title)}: ${list.length}" tabindex="${document.documentElement.classList.contains('rail-min') ? 0 : -1}">${list.length}</button></h2>` + list.map(o => {
    const st = o.status || {};
    let sub;
    // what tells two checks of one patient apart: the section, where the case stands, how long ago (never the
    // procedure again: the header has it)
    const sec = (o.section || []).join(' + ') || 'awaiting indication';
    const ago = o.updated_at ? since(o.updated_at) + ' ago' : '';
    const started = o.created_at || st.started_at;
    if (o.queue === 'paused') sub = ['Awaiting indication', started ? since(started) + ' ago' : ''].filter(Boolean).join(' · ');
    else if (lane === 'ASK') sub = [`Waiting on ${surgeonName(o.surgeon)}`, o.in_ask_since ? since(o.in_ask_since) : '', sec].filter(Boolean).join(' · ');
    else if ((o.queue === 'running' || o.queue === 'failed') && st.stage_label) sub = (o.queue === 'failed' ? 'Stopped while ' : '') + st.stage_label.charAt(0).toLowerCase() + st.stage_label.slice(1) + (o.queue === 'running' ? '…' : '');
    else if (lane === 'LOOK') sub = [o.determination === 'NOT_COVERED' ? 'Code not covered' : WAITS.includes(o.determination) ? "Guideline can't decide it" : sec + ' · to ask', ago].filter(Boolean).join(' · ');
    else sub = [sec, ago].filter(Boolean).join(' · ');
    // the row shows only the patient's name (the owner's call); the detail stays on hover
    const full = [sub, o.procedure_text || '', o.in_ask ? `${o.in_ask} in the ask, waiting on ${surgeonName(o.surgeon)}` : ''].filter(Boolean).join(' · ');
    // the one exception: "removed while missing" never disappears (a safety line, not a detail)
    const gap = (lane === 'READY' || lane === 'SIGNOFF') && o.removed_missing ? `<i class="row-gap" title="${esc(gapWords(o.removed_missing))}" aria-label="${esc(gapWords(o.removed_missing))}"></i>` : '';
    // sibling cases of one order (one code each): the code as a tiny suffix after the name
    const sib = o.code && orders.some(x => x !== o && x.code && x.code !== o.code && x.patient_name === o.patient_name);
    return `<button class="row" data-id="${esc(o.chart_id)}" aria-current="${o.chart_id===current}" title="${esc(full)}"><b>${esc(o.patient_name||o.filename||'Unknown patient')}${sib ? `<span class="row-code">${esc(o.code)}</span>` : ''}</b>${gap}</button>`;
  }).join('') + '</div>';
}
function markRows(){ $$('.row').forEach(b => b.setAttribute('aria-current', b.dataset.id === current)); }

// ------------------------------------------------------------------ address: /review and /review/<chart_id>
const pathOf = id => id ? '/review/' + encodeURIComponent(id) : '/review';
function idFromLocation(){ const m = location.pathname.match(/^\/review\/([^/]+)\/?$/); return m ? decodeURIComponent(m[1]) : null; }
// /review/<id>#<requirement> opens that requirement (a link that can be sent); the hash follows the open requirement
// (replaceState: moving between requirements is not history). Each history entry remembers where the page was
// scrolled, so reload, back and forward come back to the same place once the case is drawn.
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
// the address keeps what else it says (?style=, ?view=) when another chart is opened
function go(id){ if (location.pathname !== pathOf(id)) { keepPlace(); history.pushState({id}, '', pathOf(id) + location.search); } load(id); }
window.addEventListener('popstate', () => { const v = viewParam(); if (v) view = v; const id = idFromLocation(); if (id) load(id); else home(); });
// not while another chart is loading (its placeholder is short and would record the top)
function keepPlace(){ if (!current || !doc || doc.chart_id !== current) return; try { history.replaceState({ ...(history.state || {}), id: current, y: Math.round(window.scrollY) }, '', location.href); } catch {} }
let placeTimer = 0;
window.addEventListener('scroll', () => { clearTimeout(placeTimer); placeTimer = setTimeout(keepPlace, 160); }, { passive: true });
window.addEventListener('pagehide', keepPlace);
function syncHash(){
  if (!current || !doc || doc.chart_id !== current) return;
  const want = selectedCrit && panelMode === 'req' ? '#' + encodeURIComponent(selectedCrit) : '';
  if (location.hash !== want) try { history.replaceState(history.state, '', location.pathname + location.search + want); } catch {}
}
// on a phone the rail folds to a slim bar on every screen but the landing (the gate, progress, a stopped check, the
// case): the queue is a desk task (CSS: .app.slim under 820px)
function slimRail(on){ const a = document.querySelector('.app'); if (a) a.classList.toggle('slim', !!on); }
function home(){
  current = null; doc = null; clearTimeout(pollTimer); markRows(); hideFb(); probe = null; slimRail(false);
  $('#main').innerHTML = landingHtml();
  wireLanding();
}
// nothing open: the drop zone itself, and what happens next
function landingHtml(){
  return `<div class="landing narrow"><label class="drop big" id="landDrop" tabindex="0"><input id="landFiles" type="file" accept="application/pdf" multiple>
      <i class="drop-doc" aria-hidden="true"></i><b>Drop a case PDF to add it</b><span>Add the payer's policy too if it is not on file, or click to choose the PDFs.</span></label>
    <ol class="how">
      <li><b>Drop the case</b><span>The check reads it and finds the order.</span></li>
      <li><b>Confirm the pathway</b><span>It suggests the part of the policy that applies; you decide.</span></li>
      <li><b>Accept and sign off</b><span>Each requirement comes with the case's own words as proof.</span></li>
    </ol></div>`;
}
function wireLanding(){
  const z = $('#landDrop'); if (!z) return;
  $('#landFiles').onchange = e => { openDlg(); takeFiles(e.target.files); };
  z.addEventListener('dragover', e => { e.preventDefault(); z.classList.add('over'); });
  z.addEventListener('dragleave', () => z.classList.remove('over'));
  z.addEventListener('drop', e => { e.preventDefault(); e.stopPropagation(); z.classList.remove('over'); openDlg(); takeFiles(e.dataTransfer.files); });
}

// ------------------------------------------------------------------ load one chart and draw its state
async function load(id, quiet){
  current = id; markRows(); clearTimeout(pollTimer); slimRail(true);
  // no "Loading…" flash: the old page stays until the new one is ready; only a slow load (over 400 ms) says so
  let slow = null;
  if (!quiet) { hideFb(); slow = setTimeout(() => { if (current === id) $('#main').innerHTML = '<div class="busy">Loading…</div>'; }, 400); }
  let d;
  try { d = await api('/review/' + encodeURIComponent(id)); }
  catch(e){
    clearTimeout(slow);
    if (current !== id) return;
    const gone = e.status === 404 || /no case with this id/i.test(e.message);
    doc = null;
    $('#main').innerHTML = `<div class="narrow"><p class="verdict v-wait">${gone ? 'No case with this id.' : 'Could not load this case.'}</p>
      <p class="why">${gone ? `Nothing on file is called “${esc(id.length > 40 ? id.slice(0, 39) + '…' : id)}”. It may have been forgotten, or the link is old. Pick a case on the left, or add one.` : esc(e.message)}</p></div>`;
    return;
  }
  clearTimeout(slow);
  if (current !== id) return;
  const was = doc && doc.state, wasId = doc && doc.chart_id;
  const fresh = !quiet && wasId !== id;            // arriving at this chart (a link, reload, back / forward)
  const want = fresh ? decodeURIComponent(location.hash.slice(1)) : '', st0 = history.state || {};
  doc = d;
  const landed = !!(landNext && !quiet && d.case && !d.nofit && !want);   // opened from the rail: lands on the work
  if (d.state === 'running') renderRunning(d);
  else if (d.state === 'failed') renderFailed(d);
  else if (d.state === 'paused') renderGate(d);
  else if (d.nofit) renderNoFit(d);
  else if (d.case) { renderCase(d); if (landed) landOnWork(); }
  else renderRunning(d);
  landNext = false;
  if (fresh && !landed) {
    const y = st0.id === id && typeof st0.y === 'number' ? st0.y : null;
    if (d.case && want && reqById[want]) {
      selectRequirement(want, true);
      const nv = curView() === 'tree' ? placeOf(want) : document.querySelector(`.nv[data-crit="${CSS.escape(want)}"]`); if (nv && nv.getClientRects().length) nv.focus({ preventScroll: true });
      if (y == null) scrollToEl(placeOf(want), 'force-instant');
    }
    if (y != null || !(d.case && want && reqById[want])) window.scrollTo({ top: y || 0, behavior: 'instant' });
  }
  // a new state of the same chart (the check finished, the section was confirmed) is a new page: start at its top
  if (quiet && wasId === id && was && was !== d.state) window.scrollTo({ top: 0, behavior: 'instant' });
  if (d.state === 'running') pollTimer = setTimeout(() => { if (current === id) load(id, true); }, 600);   // land on the gate the moment it is ready
  else if (was === 'running' || quiet) loadOrders();     // the check ended: the row moves to its queue
}

// the header's first line, said once on every page of a chart: the patient's name, then quieter the procedure in
// short (its target, else its words) with its code and the guideline it is checked against; the full procedure, the
// payer and the guideline's title on hover. `right` sits at the end of the line (the case's Guideline | Tree)
function whoHtml(d, right = ''){
  const o = d.order || {}, g = d.guideline || {};
  // "Endovenous radiofrequency ablation, left great saphenous vein" -> "Left great saphenous vein ablation"
  const t = String(o.target || '').trim(), pt = String(o.procedure_text || ''), cut = pt.indexOf(',');
  const how = cut > 0 && pt.slice(cut).toLowerCase().includes(t.toLowerCase()) ? pt.slice(0, cut).trim().split(/\s+/).pop().toLowerCase() : '';
  const proc = t ? t[0].toUpperCase() + t.slice(1) + (how && !t.toLowerCase().includes(how) ? ' ' + how : '') : short(pt, 60);
  // one code, one pathway: once the case's code is known the header reads from `focus` (procedure · code · indication · guideline)
  const f = d.focus, conf = d.confirmation, ind = f ? ((conf && (conf.confirmed || []).length) ? [...new Set(conf.confirmed.map(x => nameOf(x.pathway)))].join('; ') : f.pathway_name) : '';
  const bits = f ? [String(f.procedure_short || proc).replace(/[\s,;:—-]+$/, ''), f.code, ind, g.title || g.name ? glShort(g) : ''].filter(Boolean)
    : [proc, (o.cpt || []).join(', '), g.title || g.name ? glShort(g) : ''].filter(Boolean);
  const full = [`${o.procedure_text || ''}${(o.cpt || []).length ? ` (${o.cpt.join(', ')})` : ''}`, o.payer, g.title || g.name ? glTitle(g) : ''].filter(Boolean).join(' · ');
  return `<div class="who"><div class="who-l"><b>${esc(o.patient_name||(d.status||{}).filename||'New case')}</b>${bits.length
    ? `<span class="who-s" title="${esc(full)}">${esc(bits.join(' · '))}</span>` : ''}</div>${right}</div>`;
}
function stagesHtml(st){
  if (!st || !st.stages) return '';
  return `<div class="stages">${st.stages.map(s => `<div class="stg ${esc(s.status)}"><span class="sg">${SG[s.status]||''}</span><div>
      <b>${esc(s.label)}</b>${s.cached ? '<small>from an earlier read</small>' : ''}${s.status !== 'waiting' && s.started_at && s.ended_at ? `<small>${secs(s.started_at, s.ended_at)}</small>` : ''}
      ${s.summary ? `<div class="sum">${esc(s.summary)}${(s.logs||[]).map(l => `<a href="${esc(l.url)}" target="_blank">log</a>`).join('')}</div>` : (s.logs||[]).length ? `<div class="sum">${s.logs.map(l => `<a href="${esc(l.url)}" target="_blank">log</a>`).join('')}</div>` : ''}
      ${s.status === 'failed' ? `<div class="gate"><b>${esc(wentWrong(s.id))}</b><div class="act"><button class="primary" id="retryBtn">Run it again</button><span class="hint" id="retryMsg"></span></div><details><summary style="font-size:12.5px;color:var(--sec)">Details</summary><pre>${esc(errClass(s.error) || 'Error')}</pre></details></div>` : ''}
      ${s.status === 'needs_person' && s.gate && !s.gate.answered ? `<div class="gate"><b>${esc(s.gate.title||'')}</b>${esc(s.gate.needs||'')}${(s.gate.options||[]).map(o => `<div class="opt" style="cursor:default">· ${esc(o)}</div>`).join('')}</div>` : ''}
    </div></div>`).join('')}</div>`;
}
function foldHtml(d){
  const st = d.status || {}, c = d.confirmation, cs = d.case || {};
  const links = [`<a href="/api/review/${esc(d.chart_id)}" target="_blank">This page's data</a>`,
                 `<a href="/api/orders/${esc(d.chart_id)}/status" target="_blank">The status record</a>`];
  if (st.run_id) links.push(`<a href="/api/runs/${esc(st.run_id)}" target="_blank">Every model exchange (run ${esc(st.run_id)})</a>`);
  let conf = '';
  if (c) conf = `<p>Confirmation record (pathways.json): confirmed ${esc(JSON.stringify(c.confirmed||[]))}, suggested ${esc(JSON.stringify(c.suggested||[]))}, by ${esc(c.by||'—')} at ${esc(c.at||'—')}, run ${esc(c.run_id||'—')}.</p>`;
  const so = d.signoff || {}, sr = so.record;
  if (sr) conf += `<p>Sign-off record (signoff.json): ${esc(sr.by || '—')} at ${esc(sr.at || '—')}, fingerprint ${esc(sr.fingerprint || '—')}, ${so.signed ? 'counts' : sr.withdrawn ? 'withdrawn (' + esc(sr.withdrawn.why || '') + ')' : so.stale ? 'stale: the case changed after it' : 'not in force'}.</p>`;
  if ((d.strikes || []).length) conf += `<p>Removals (strikes.json): ${d.strikes.map(k => `${esc(k.criterion)} by ${esc(k.by || '—')} at ${esc(k.at)}${k.undone ? ', put back at ' + esc(k.undone.at) : ''}`).join('; ')}. The criteria cache is not changed by a removal; this case's expression is pruned and K-L run again.</p>`;
  if ((d.additions || []).length) conf += `<p>Additions (additions.json): ${d.additions.map(k => `${esc(k.id)} on ${esc((k.spans || []).join(' '))} by ${esc(k.by || '—')} at ${esc(k.at)}${k.undone ? ', taken off at ' + esc(k.undone.at) : ''}`).join('; ')}. Each joins this case's expression as one more AND term, judged by its ask; the criteria cache is not changed.</p>`;
  if ((d.accepts || []).length) conf += `<p>Accepts (accepts.json): ${d.accepts.map(k => `${esc(k.criterion)} by ${esc(k.by || '—')} at ${esc(k.at)}${k.undone ? ', undone at ' + esc(k.undone.at) : ''}`).join('; ')}. An accept counts while its basis (run, checklist, requirement, the verdict shown) still matches.</p>`;
  if ((d.probes || []).length) conf += `<p>Asked about (probes.json): ${d.probes.map(p => `${esc((p.spans || []).join(' '))} (${esc(p.source)}, ${esc(p.mark)})`).join('; ')}. “known” and “cached” cost no model call; “asked” is one ask_guideline exchange in the run log.</p>`;
  const hk = cs.h_key || (c && c.h_key);
  const counts = Object.entries((cs.tree||{}).counts||{}).map(([k,v]) => `${v} ${k.replace('_',' ')}`).join(', ');
  const r = cs.result || {};
  return `<details class="fold"><summary>How this was decided</summary>
    <p>${links.join(' · ')}</p>${conf}${hk ? `<p>Criteria cache key for the confirmed pathway: <code>${esc(hk)}</code></p>` : ''}
    ${r.determination ? `<p>Verdict ${esc(r.determination)}, pathway ${esc((r.pathway_used||[]).join(', ')||'—')}, confidence ${esc(r.confidence == null ? '—' : Number(r.confidence).toFixed(2))}. Criterion rows: ${esc(counts||'none')}. Each row's words are the guideline's own, checked against the cited spans; each quote is the case's own lines, resolved from the citation.</p>` : ''}
  </details>`;
}

// running: the stage list
// the stages as calm single lines that fill in (the Marker style); Classic keeps the stage table
const DONE_WORDS = { chart:'Read the case', order:'Found the order', guideline:'Read the guideline', section:'Chose the section',
                     checklist:'Built the checklist', record:'Read the record', read:'Read the case against it', verify:'Checked every quote and date', decide:'Decided' };
// the running stage says how long it has been at it against how long it usually takes, and what it is doing when the
// pipeline knows (status: elapsed_s, typical_s, doing); the seconds tick here between polls, from the server's count
let runClock = null;
const fmtS = n => n < 60 ? `${Math.round(n)} s` : `${Math.floor(n / 60)} min ${String(Math.round(n % 60)).padStart(2, '0')} s`;
function runTiming(el, base, typ, t0){
  const n = base + (performance.now() - t0) / 1000, over = typ && n > typ * 1.25;
  const t = el.querySelector('.rl-t'), bar = el.querySelector('.rl-bar i');
  if (t) t.textContent = fmtS(n) + (typ ? (over ? ' · taking longer than usual' : ` · usually about ${fmtS(typ)}`) : '');
  if (bar) bar.style.width = typ ? Math.min(100, n / typ * 100).toFixed(1) + '%' : '0';
  el.classList.toggle('over', !!over);
}
let runSeen = null;   // {key, base, t0}: the clock survives the 600 ms re-renders; the server's count only moves it forward
function startRunClock(){
  clearInterval(runClock); runClock = null;
  const el = document.querySelector('.runlines .rl.running[data-elapsed]'); if (!el) { runSeen = null; return; }
  const key = (current || '') + '|' + el.dataset.stage, server = +el.dataset.elapsed, typ = +el.dataset.typical || 0;
  if (!runSeen || runSeen.key !== key) runSeen = { key, base: server, t0: performance.now() };
  else { const mine = runSeen.base + (performance.now() - runSeen.t0) / 1000; if (server > mine + 1.5) runSeen = { key, base: server, t0: performance.now() }; }
  const base = runSeen.base, t0 = runSeen.t0;
  runTiming(el, base, typ, t0);
  runClock = setInterval(() => { if (!el.isConnected) { clearInterval(runClock); runClock = null; return; } runTiming(el, base, typ, t0); }, 1000);
}
function runLinesHtml(st){
  setTimeout(startRunClock, 0);
  return `<ol class="runlines">${(st.stages||[]).filter(s => s.status !== 'skipped').map(s => {
    const run = s.status === 'running';
    const w = s.status === 'done' || s.status === 'needs_person' ? (DONE_WORDS[s.id] || s.label) : s.label;
    const sum = run ? '…' : s.summary ? ' · ' + s.summary : '';
    const timed = run && typeof s.elapsed_s === 'number';
    const extra = run ? `${s.doing ? `<span class="rl-doing">${esc(s.doing)}</span>` : ''}${timed ? `<span class="rl-t"></span>${s.typical_s ? '<span class="rl-bar" aria-hidden="true"><i></i></span>' : ''}` : ''}` : '';
    return `<li class="rl ${esc(s.status)}"${timed ? ` data-stage="${esc(s.id)}" data-elapsed="${+s.elapsed_s}" data-typical="${+(s.typical_s || 0)}"` : ''}><span class="rl-m" aria-hidden="true">${s.status === 'done' || s.status === 'needs_person' ? '✓' : s.status === 'failed' ? '✗' : ''}</span><span>${esc(w)}${esc(sum)}${s.cached ? ' <small>(from an earlier read)</small>' : ''}${extra}</span></li>`; }).join('')}</ol>`;
}
function renderRunning(d){
  const st = d.status || {};
  const cur = (st.stages||[]).find(s => s.status === 'running');
  if (document.documentElement.dataset.style !== 'classic') {
    $('#main').innerHTML = `<div class="narrow run-page">${whoHtml(d)}
      <p class="verdict v-wait">Checking this case…</p>
      <p class="why">It stops at the indications of the guideline for you to confirm; this page goes there by itself.</p>
      ${runLinesHtml(st)}${foldHtml(d)}</div>`;
    return;
  }
  $('#main').innerHTML = `<div class="narrow">${whoHtml(d)}
    <p class="verdict v-wait">Checking this case…</p>
    <p class="why">${cur ? esc(cur.label) + '… ' : 'Starting… '}The stages below fill in as the check goes; this page refreshes by itself. It will stop to let you confirm the indication of the guideline.</p>
    ${stagesHtml(st)}${foldHtml(d)}</div>`;
}
// a stage that raised, in plain words; the error itself stays folded under Details / What went wrong
const DOING = { chart:'reading the case', order:'finding the order', guideline:'reading the guideline', section:'choosing the indication',
                checklist:'building the checklist', read:'reading the case', verify:'checking the quotes and dates', decide:'deciding' };
// what went wrong, for the fold: the error's class only ("RuntimeError"), never a message, a path or a traceback
const errClass = t => { const m = String(t || '').match(/^\s*([A-Za-z_][\w.]*?)(?=:|\s*$)/); return m ? m[1].split('.').pop() : (t ? 'Error' : ''); };
const wentWrong = sid => `Something went wrong ${DOING[sid] || 'checking this case'}. Run it again.`;
// failed: the stage that stopped, with the error, and "Run it again"
function renderFailed(d){
  const st = d.status || {};
  if (document.documentElement.dataset.style !== 'classic') {     // calm lines, the stage that stopped, Retry
    const f = (st.stages || []).find(s => s.status === 'failed') || {};
    $('#main').innerHTML = `<div class="narrow run-page failed-page">${whoHtml(d)}
      <p class="verdict v-no">This check stopped.</p>
      <p class="why">${esc(wentWrong(f.id))} Nothing was decided.</p>
      <div class="act"><button class="primary" id="retryBtn">Run it again</button><span class="hint" id="retryMsg"></span></div>
      ${runLinesHtml(st)}
      <details class="fold"><summary>What went wrong</summary><pre class="trace">${esc(errClass(f.error || st.error) || 'Error')}</pre></details>
      ${foldHtml(d)}</div>`;
    const b = $('#retryBtn');
    b.onclick = async () => { b.disabled = true; $('#retryMsg').textContent = 'Starting…';
      try { await post('/review/' + encodeURIComponent(d.chart_id) + '/retry', {}); await loadOrders(); load(d.chart_id, true); }
      catch(e){ $('#retryMsg').textContent = e.message; b.disabled = false; } };
    return;
  }
  $('#main').innerHTML = `<div class="narrow">${whoHtml(d)}
    <p class="verdict v-no">This check stopped.</p>
    <p class="why">Nothing was decided. The stage that stopped is marked below, with the error; run it again.</p>
    ${stagesHtml(st)}${foldHtml(d)}</div>`;
  const b = $('#retryBtn');
  if (b) b.onclick = async () => { b.disabled = true; $('#retryMsg').textContent = 'Starting…';
    try { await post('/review/' + encodeURIComponent(d.chart_id) + '/retry', {}); await loadOrders(); load(d.chart_id, true); }
    catch(e){ $('#retryMsg').textContent = e.message; b.disabled = false; } };
}

// ------------------------------------------------------------------ paused: which section of the guideline applies?
function linesHtml(lines, showPage){
  let page = null, out = '';
  for (const l of (lines||[])) {
    if (showPage && l.page !== page) { out += `<div class="pg">page ${esc(l.page)}</div>`; page = l.page; }
    out += `<div class="ln ${l.blank_before ? 'blank' : ''}"><span class="id"></span><span class="tx">${esc(l.text)}</span></div>`;   // no internal line ids on screen
  }
  return out;
}
// The gate asks one question: which indication applies? One card, for the indication picked (the guideline reader's
// suggestion to start with), and every other indication in one dropdown above it. The card says three things: the
// indication, its source (the policy's own words for it, with the page) and the evidence (the one best chart line,
// with the page). An indication that does not list the order's code says so, in the warm ink; codes are otherwise
// not shown. "+ Add another indication" adds a second row (an order with more than one code). In the dropdown ↑/↓
// move, ⌘/Ctrl+Enter confirms; "None of these" in the confirm bar ends the check for this guideline.
const unglyph = t => tidy(String(t || '').replace(/^[\s•·▪➢❖◦‣∙*–-]+/, '').replace(/^\d+[.)]\s+/, '')).replace(/\s+·\s+$/, '');
const sentenceCase = t => /[a-z]/.test(t) ? t : t.charAt(0) + t.slice(1).toLowerCase();
// end a label at a natural break (a comma, "AND", "after", "in members who"), else at a word, never mid-phrase
function cutLabel(t, max = 72, breaks = true){
  t = unglyph(t).replace(/^note:\s*/i, '').replace(/[.;:]+$/, '');
  // a cut never leaves a bracket open ("Secondary Prevention (use of ICDs"): it falls back to before the bracket
  const shut = x => { const o = (x.match(/\(/g) || []).length, c = (x.match(/\)/g) || []).length;
    return o > c ? x.slice(0, x.lastIndexOf('(')).replace(/[,;:\s—-]+$/, '') : x; };
  if (breaks) for (const re of [/\s+meets the definition\b/i, /,\s/, /\s+AND\s+/, /\s+after\s+/i, /\s+in (?:members|children|adults) who\b/i, /;\s/, /\s+\(/])
    { const m = t.search(re); if (m >= 12 && m <= max) { const x = shut(t.slice(0, m)); if (x.length >= 12) return x; } }
  if (t.length <= max) return t;
  const cut = shut(t.slice(0, t.lastIndexOf(' ', max - 1)).replace(/[,;:\s]+$/, ''));
  return cut + '…';
}
// each indication's own words: its lines with the ones every look-alike shares set aside (the lead-in sentence many
// indications of one policy repeat), so the dropdown never offers the same label twice
function gateIndications(ps){
  const lines = p => (p.body && p.body.length ? p.body : p.lines || []).map(l => ({ ...l, t: l.text.trim() })).filter(l => l.t);
  const seen = {}; for (const p of ps) for (const t of new Set(lines(p).map(l => l.t))) seen[t] = (seen[t] || 0) + 1;
  const names = {}; for (const p of ps) names[p.name] = (names[p.name] || 0) + 1;
  const named = (p, breaks) => {
    const ls = lines(p), own = ls.filter(l => seen[l.t] < 2 && l.t !== p.name);
    const head = ls.length && /^[A-Z][A-Z &/-]{3,}$/.test(ls[0].t) && ls[0].t !== p.name ? sentenceCase(ls[0].t) : '';
    // a name of its own (not the lead-in many indications share) is the label; else the indication's own first line
    let label = names[p.name] < 2 ? sentenceCase(cutLabel(p.name, 72, breaks)) : own.length ? cutLabel(own[0].t, 72, breaks) : cutLabel(p.name, 72, breaks);
    if (head && names[p.name] > 1 && !label.toLowerCase().startsWith(head.toLowerCase())) label = `${head} — ${label}`;
    return { ls, own, label };
  };
  const out = ps.map(p => {
    const { ls, own, label } = named(p, true);
    const src = (own.length ? own : ls.slice(ls.length > 1 ? 1 : 0)).slice(0, 2);
    return { p, label, src: src.map(l => unglyph(l.t)).join(' '), page: (src[0] || ls[0] || {}).page };
  });
  const count = () => { const n = {}; for (const x of out) n[x.label] = (n[x.label] || 0) + 1; return n; };
  let n = count();
  for (const x of out) if (n[x.label] > 1) x.label = named(x.p, false).label;     // a longer cut tells them apart
  n = count();
  for (const x of out) if (n[x.label] > 1 && x.page != null) x.label += ` · page ${x.page}`;
  n = count();
  for (const x of out) if (n[x.label] > 1) x.label += ` · ${x.p.id.replace(/[_-]+/g, ' ').trim().replace(/^./, c => c.toUpperCase())}`;   // still alike: its own id tells them apart
  return out;
}
function gateCardHtml(x, orderCodes){
  const p = x.p, ev = (p.why || [])[0];
  const missing = (p.codes || []).length ? orderCodes.filter(c => !(p.codes || []).includes(c)) : [];
  const short = x.label.length > 44 ? x.label.slice(0, x.label.lastIndexOf(' ', 43)).replace(/[,;:\s—-]+$/, '') + '…' : x.label;
  return `<div class="card gcard g1" tabindex="-1" data-pathway="${esc(p.id)}">
    <div class="gc-body"><div class="gc-top"><h3>${esc(x.label)}</h3>${p.suggested ? '<span class="chip for">Suggested</span>' : ''}</div>
      ${x.src ? `<p class="gc-src"><span class="gc-k">Source</span><span class="gc-src-t">${esc(x.src)}</span>${x.page != null ? `<span class="gc-pg">page ${esc(x.page)}</span>` : ''}</p>` : ''}
      <div class="gc-ev"><span class="gc-k">Evidence</span>${ev ? `<div class="gc-q"><q>${esc(unglyph(ev.text))}</q><small>page ${esc(ev.page)}</small></div>` : '<div class="gc-q none-why">No case line names this indication.</div>'}</div>
      ${missing.map(c => `<p class="gc-warn">This indication doesn't list ${esc(c)}.</p>`).join('')}
      <div class="gc-go"><button class="primary" id="confirmBtn" title="${esc('Confirm ' + x.label)}">Confirm ${esc(short)} <kbd>${MOD}↵</kbd></button><span class="hint" id="confirmMsg"></span></div></div></div>`;
}
const GATE_ROWS = 2;   // under the selected card: two more indications, the rest behind "Show N more indications"
// one code, one pathway (app/onecode.py): an order with 2+ codes pauses before the guideline is read. The same look as
// the indication gate: the suggested code as the selected card (Source: its descriptor; Evidence: the chart line that
// names it), Confirm on the card (⌘↵); the other codes as rows, each with a quiet "Check as its own case"
function renderCodeGate(d){
  const g = d.gate || {}, codes = (g.codes || []).slice().sort((a, b) => !!b.suggested - !!a.suggested);
  const desc = c => unglyph(String(c.descriptor || '').replace(new RegExp('^\\s*' + c.code + '\\s*'), '').trim());
  let sel = (codes[0] || {}).code || null, going = false;
  const split = {};
  $('#main').innerHTML = `<div class="narrow gate-page">${whoHtml(d)}
    <p class="verdict v-needs">Which code does this case check?</p>
    ${g.needs ? `<p class="calm-note">${esc(g.needs)}</p>` : ''}
    <div class="gcards" id="gList"></div>
    <details class="fold gc-ran"><summary>How this check ran so far</summary>${stagesHtml(d.status)}</details>
    ${foldHtml(d)}${styleSwitchHtml()}</div>`;
  wireStyleSwitch();
  const byCode = Object.fromEntries(codes.map(c => [c.code, c]));
  const cardHtml = c => { const ev = (c.chart_lines || [])[0];
    return `<div class="card gcard g1" tabindex="-1" data-code="${esc(c.code)}">
      <div class="gc-body"><div class="gc-top"><h3>${esc(c.code)}</h3>${c.suggested ? '<span class="chip for">Suggested</span>' : ''}</div>
      ${desc(c) ? `<p class="gc-src"><span class="gc-k">Source</span><span class="gc-src-t">${esc(desc(c))}</span></p>` : ''}
      <div class="gc-ev"><span class="gc-k">Evidence</span>${ev ? `<div class="gc-q"><q>${esc(unglyph(ev.text))}</q><small>page ${esc(ev.page)}</small></div>` : '<div class="gc-q none-why">No case line names this code.</div>'}</div>
      <div class="gc-go"><button class="primary" id="confirmBtn">Check ${esc(c.code)} <kbd>${MOD}↵</kbd></button><span class="hint" id="confirmMsg"></span></div></div></div>`; };
  const rowHtml = c => `<div class="g-row g-code" data-code="${esc(c.code)}" role="option" tabindex="-1"><span class="g-row-n">${esc(c.code)}</span>${desc(c) ? `<span class="g-row-s">${esc(desc(c))}</span>` : ''}
      ${split[c.code] ? `<span class="g-split-done">${split[c.code]}</span>` : `<a href="#" class="g-split" data-code="${esc(c.code)}">Check as its own case</a>`}</div>`;
  const draw = focus => {
    if (!sel) return;
    $('#gList').innerHTML = cardHtml(byCode[sel]) + (codes.length > 1 ? `<div class="g-rows" role="listbox" aria-label="Other codes">${codes.filter(c => c.code !== sel).map(rowHtml).join('')}</div>` : '');
    $('#confirmBtn').onclick = go;
    if (focus) { const c = $('.gcard.g1'); if (c) c.focus({ preventScroll: true }); }
  };
  const go = async () => {
    if (going || !sel) return;
    going = true; const b = $('#confirmBtn'); b.disabled = true; $('#confirmMsg').textContent = 'Going on with the check…';
    try { await post('/review/' + encodeURIComponent(d.chart_id) + '/code', { code: sel, by: myName() || null }); await loadOrders(); load(d.chart_id, true); }
    catch(e){ $('#confirmMsg').innerHTML = `<span class="err">${esc(e.message)}</span>`; b.disabled = false; going = false; }
  };
  $('#gList').onclick = async e => {
    const sp = e.target.closest('.g-split');
    if (sp) { e.preventDefault(); e.stopPropagation(); const code = sp.dataset.code; sp.textContent = 'Starting…';
      try { await post('/review/' + encodeURIComponent(d.chart_id) + '/split', { code, by: myName() || null }); split[code] = 'Checking as its own case'; await loadOrders(); }
      catch(err){ split[code] = ''; sp.textContent = 'Check as its own case'; calm(err.message); return; }
      draw(false); return; }
    const r = e.target.closest('.g-row'); if (r && r.dataset.code !== sel) { sel = r.dataset.code; draw(true); }
  };
  const step = dir => { const v = codes.map(c => c.code); const i = v.indexOf(sel); const n = v[Math.max(0, Math.min(v.length - 1, i + dir))]; if (n !== sel) { sel = n; draw(true); } };
  draw(true);
  gateKeys = { go, step, fold: () => false };
}
function renderGate(d){
  if ((d.gate || {}).kind === 'pick_code') return renderCodeGate(d);
  const g = d.gate || {}, o = g.order || d.order || {}, codes = g.codes || [];
  const judged = codes.filter(c => c.outcome === 'judge').map(c => c.code);
  const orderCodes = (o.cpt && o.cpt.length ? o.cpt : judged);
  pwNames = Object.fromEntries((g.pathways||[]).map(p => [p.id, p.name])); pwLabels = Object.fromEntries(gateIndications(g.pathways || []).map(x => [x.p.id, x.label]));
  // the suggestion first, then the ones the chart names most, then as the policy orders them
  const ps = (g.pathways || []).map((p, i) => ({ p, i })).sort((a, b) => (!!b.p.suggested - !!a.p.suggested)
    || ((b.p.why || []).length - (a.p.why || []).length) || a.i - b.i).map(x => x.p);
  const xs = gateIndications(ps), byId = Object.fromEntries(xs.map(x => [x.p.id, x])), ranked = xs.map(x => x.p.id);
  let sel = ranked[0] || null, more = false;
  const stopped = (g.stopped||[]).map(c => `<div class="card stopped"><h3>Code ${esc(c.code)}${c.mapped ? ' <span class="chip">matched from the procedure name</span>' : ''}</h3>
      <div class="say">${esc(c.tag === 'investigational' ? 'Listed as investigational' : c.tag === 'not_addressed' ? 'Listed, but this guideline does not decide it' : c.outcome === 'cant_check' && !c.tag ? 'Not in the guideline\'s code table' : 'Listed as not covered')}</div>
      ${(c.lines||[]).length ? `<div class="lines">${linesHtml(c.lines, true)}</div>` : ''}</div>`).join('');
  $('#main').innerHTML = `<div class="narrow gate-page">${whoHtml(d)}
    <p class="verdict v-needs">Which indication applies?</p>
    <div class="gcards" id="gList">${xs.length ? '' : '<div class="card">This guideline has no indication this order could be checked under.</div>'}</div>
    <p class="g-none"><a href="#" id="noneLink">None of these</a><span class="none-confirm" id="noneConfirm" hidden></span></p>
    ${stopped ? `<h2>Codes the guideline stops at</h2>${stopped}` : ''}
    <details class="fold gc-ran"><summary>How this check ran so far</summary>${stagesHtml(d.status)}</details>
    ${foldHtml(d)}${styleSwitchHtml()}</div>`;
  wireStyleSwitch();
  const rowHtml = id => { const x = byId[id];
    return `<button type="button" class="g-row" data-pathway="${esc(id)}"><span class="g-row-n">${esc(x.label)}</span>${x.src ? `<span class="g-row-s">${esc(x.src)}</span>` : ''}</button>`; };
  const visible = () => more ? ranked : ranked.slice(0, GATE_ROWS + 1).concat(sel && ranked.indexOf(sel) > GATE_ROWS ? [sel] : []);
  const draw = (focus) => {
    if (!sel) return;
    const rest = ranked.filter(id => id !== sel), shown = rest.slice(0, more ? rest.length : GATE_ROWS), hidden = rest.length - shown.length;
    $('#gList').innerHTML = gateCardHtml(byId[sel], orderCodes)
      + (shown.length ? `<div class="g-rows" role="listbox" aria-label="Other indications">${shown.map(rowHtml).join('')}</div>` : '')
      + (hidden > 0 ? `<a href="#" class="gc-more" id="gcMore">Show ${hidden} more indication${hidden > 1 ? 's' : ''}</a>` : '')
      + (more && rest.length > GATE_ROWS ? `<a href="#" class="gc-more" id="gcLess">Show fewer <kbd>Esc</kbd></a>` : '');
    $('#confirmBtn').onclick = go;
    if (focus) { const c = $('.gcard.g1'); if (c) c.focus({ preventScroll: true }); }
  };
  const choose = (id, focus = true) => { if (!id || id === sel) return; sel = id; draw(focus); };
  $('#gList').onclick = e => {
    const r = e.target.closest('.g-row'); if (r) { choose(r.dataset.pathway); const c = $('.gcard.g1'); if (c) c.scrollIntoView({ block: 'nearest' }); return; }
    if (e.target.closest('#gcMore')) { e.preventDefault(); more = true; draw(); return; }
    if (e.target.closest('#gcLess')) { e.preventDefault(); more = false; draw(true); }
  };
  $('#noneLink').onclick = e => { e.preventDefault(); noneFits(d); };
  let going = false;
  const go = async () => {
    if (going || !sel) return;
    const p = byId[sel].p, cs = (p.codes || []).length ? orderCodes.filter(c => p.codes.includes(c)) : [];
    const picks = (cs.length ? cs : orderCodes).map(code => ({ code, pathway: sel }));
    if (!picks.length) return;
    going = true;
    const b = $('#confirmBtn'); b.disabled = true; $('#confirmMsg').textContent = 'Going on with the check…';
    try { await post('/review/' + encodeURIComponent(d.chart_id) + '/pathways', { picks, by: myName() || null }); await loadOrders(); load(d.chart_id, true); }
    catch(e){ $('#confirmMsg').innerHTML = `<span class="err">${esc(e.message)}</span>`; b.disabled = false; going = false; }
  };
  // ↑/↓ (j/k) move the selection through the indications on screen, in their ranked order; Esc folds the "more" list
  const step = dir => { const v = ranked.filter(id => visible().includes(id)); const i = v.indexOf(sel); choose(v[Math.max(0, Math.min(v.length - 1, i + dir))]); };
  const fold = () => { if (!more) return false; more = false; if (ranked.indexOf(sel) > GATE_ROWS) sel = ranked[0]; draw(true); return true; };
  draw(true);
  gateKeys = { go, step, fold };
}
let gateKeys = null;
function gateKey(e){
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === 'Escape') { if (gateKeys.fold()) e.preventDefault(); return; }
  const dir = { ArrowDown: 1, j: 1, ArrowUp: -1, k: -1 }[e.key]; if (!dir) return;
  e.preventDefault(); gateKeys.step(dir);
}
// "None of these": a short confirmation beside the link, then the guideline doesn't apply
function noneFits(d){
  const c = $('#noneConfirm');
  if (!c.hidden) return;
  c.hidden = false;
  c.innerHTML = `None of these indications fits? <button class="primary" id="noneGo">This guideline doesn't apply</button><button id="noneNo">Cancel</button><span class="hint" id="noneMsg"></span>`;
  $('#noneNo').onclick = e => { e.stopPropagation(); c.hidden = true; c.innerHTML = ''; $('#noneLink').focus(); };
  $('#noneGo').focus();
  $('#noneGo').onclick = async e => {
    e.stopPropagation(); $('#noneGo').disabled = true;
    try { redraw(await post('/review/' + encodeURIComponent(d.chart_id) + '/none', { by: myName() || null })); }
    catch (err) { $('#noneMsg').innerHTML = `<span class="err">${esc(err.message)}</span>`; $('#noneGo').disabled = false; }
  };
}
// the guideline doesn't apply (a person said so at the gate): who, when, and the other guidelines on file
function renderNoFit(d){
  const nf = d.nofit || {}, g = d.guideline || {};
  const glName = `${glShort(g)}, ${glTitle(g)}`;
  const sug = nf.suggested_names || (nf.suggested || []).map(x => x.pathway);
  const others = (d.guidelines || []).map(x => `<div class="card gl-other"><div><span class="doc-kicker">${esc(glKicker(x))}</span><b>${esc(glTitle(x))}</b></div>
      <button class="primary" data-recheck="${esc(x.id)}">Check against this one</button></div>`).join('');
  $('#main').innerHTML = `<div class="narrow nofit-page">${whoHtml(d)}
    <p class="verdict v-wait">This guideline doesn't apply.</p>
    <p class="why">${esc(nf.by || 'A person')} judged at the indication gate${nf.at ? ' on ' + fmtDate(nf.at) : ''} that no indication of ${esc(glName)} fits this order${sug.length ? ` (the guideline reader had suggested “${esc(sug.join('”, “'))}”)` : ''}. Nothing was decided against the patient.</p>
    <h2>Check it against another guideline</h2>
    ${others || '<div class="card empty-card">No other guideline is on file. Add one with “Add a case”: choose this case again and upload the payer\'s policy.</div>'}
    <span class="hint" id="recheckMsg"></span>
    ${foldHtml(d)}${styleSwitchHtml()}</div>`;
  wireStyleSwitch();
  $$('[data-recheck]').forEach(b => b.onclick = async () => {
    b.disabled = true; $('#recheckMsg').textContent = 'Starting the check against that guideline…';
    try { await post('/review/' + encodeURIComponent(d.chart_id) + '/recheck', { guideline_id: b.dataset.recheck, by: myName() || null }); await loadOrders(); load(d.chart_id, true); }
    catch (e) { $('#recheckMsg').innerHTML = `<span class="err">${esc(e.message)}</span>`; b.disabled = false; }
  });
}

// ------------------------------------------------------------------ done: the case is the guideline; the evidence opens beside it
// Three columns: the requirements (a navigator: ↑/↓ or j/k), the guideline as printed, and a side panel. The panel
// shows the packet being built when nothing is selected, a requirement's ruling and chart quotes when one is (with
// Accept, ⌘/Ctrl+Enter), or the answer for selected lines (highlight to ask). The guideline column never moves.
function indexCase(c){
  lineCrits = {}; reqById = {}; blocks = {}; glOrder = []; navOrder = []; linePage = {};
  for (const s of ((c.tree||{}).sections||[])) for (const l of s.lines) linePage[l.id] = l.page;
  for (const l of (c.rest || [])) linePage[l.id] = l.page;
  for (const r of (c.requirements||[])) { reqById[r.criterion] = r; for (const id of (r.refs||[])) (lineCrits[id] ||= []).push(r.criterion); }
  for (const b of ((c.tree||{}).blocks||[])) blocks[b.id] = b;
  for (const s of ((c.tree||{}).sections||[])) for (const l of s.lines) glOrder.push(l.id);
  navOrder = (c.requirements||[]).filter(r => r.counted && cleadOf(r.criterion) === r.criterion).map(r => r.criterion);
}
// identical words are one item (`same`, decided together); words that overlap or sit back to back are one run
// (`near`: the first id of each item) with one row, one highlight and a stacked panel. The first id leads.
const cleadOf = id => { const r = reqById[id] || {}; return (r.near || r.same || [id])[0]; };
const unitsOf = id => (reqById[id] || {}).near || [id];
const idsOf = id => (reqById[id] || {}).same || [id];
const groupGap = id => idsOf(id).some(m => GAP.includes((reqById[m] || {}).mark));
const RANK = ['bad', 'miss', 'doc', 'alt', 'struck'];
// a run drawn as one: the most urgent member's colour; accepted / in the ask only when all of them are
function runQ(us){
  const qs = us.map(u => reqById[u]), top = qs.slice().sort((a, b) => RANK.indexOf(toneOf(a)) - RANK.indexOf(toneOf(b)))[0];
  const acc = qs.every(q => q.accepted), ask = !acc && qs.every(q => q.accepted || q.in_ask);
  return { ...top, accepted: acc ? top.accepted : null, in_ask: ask ? (qs.find(q => q.in_ask) || {}).in_ask : null };
}
// an indication's name on screen: the gate's own distinct label (never a first line cut at its wrap), else its name
const nameOf = pid => pwLabels[pid] || pwNames[pid] || pid;
function whyLine(r){
  switch (r.determination) {
    case 'MET': return evidenceLine(r);
    case 'INSUFFICIENT': return (r.misses||[]).length ? "The payer's requirements are below in its own words. Accept each one; the gaps go into the message to the surgeon." : (r.reason || '');
    case 'NOT_MET': return 'Something in the case conflicts with what the payer requires. A person decides how to proceed; nothing is denied automatically.';
    case 'NOT_COVERED': return 'A person should confirm the code and the intent before anything is told to the patient.';
    default: return r.reason || '';
  }
}
// the payer packet, from accepted requirements only, and the signer once signed off (app/review.packet_text: whole
// sentences, the note and date when known); nothing about removals: those go into the internal audit note
// (review.audit_note), copied with its own button
const packetText = d => ((d.case || {}).packet_text) || '';
const auditText = d => ((d.case || {}).audit_note) || '';
const GAP = ['missing', 'contradicted', 'applies', 'unclear', 'not_covered'];   // the marks of app/tree.BAD: what the chart does not document
const activeStrikes = d => (d.strikes || []).filter(k => !k.undone);
const gapStrikes = d => activeStrikes(d).filter(k => GAP.includes(k.was));
// how a requirement reads in the text: its tone (the pen it is drawn with) and whether a person accepted it
const TONE = { documented:'doc', clear:'doc', part_clear:'doc', confirm:'doc', missing:'miss', unclear:'miss',
               contradicted:'bad', applies:'bad', part_shown:'bad', not_needed:'alt', other_option:'alt', struck:'struck' };
const toneOf = r => TONE[(r||{}).mark] || 'doc';
// the text of one guideline line with every requirement's quoted words wrapped in <mark class="q" data-crit>
function markedText(text, ranges){
  if (!ranges || !ranges.length) return esc(text);
  const n = text.length, cuts = new Set([0, n]);
  const rs = ranges.map(r => ({ crit: r.crit, q: r.q, s: Math.max(0, Math.min(n, r.start)), e: Math.max(0, Math.min(n, r.end)) })).filter(r => r.e > r.s);
  const run = {};      // a run's words join into one continuous highlight over what lies between them (and / or / ; ,)
  for (const r of rs) if (r.q) (run[r.crit] ||= []).push(r);
  for (const g of Object.values(run)) { g.sort((a, b) => a.s - b.s); for (let i = 1; i < g.length; i++) if (g[i].s > g[i-1].e && /^(?:[\W_]|\b(?:and|or)\b)*$/i.test(text.slice(g[i-1].e, g[i].s))) g[i-1].e = g[i].s; }
  for (const r of rs) { cuts.add(r.s); cuts.add(r.e); }
  const pts = [...cuts].sort((a, b) => a - b);
  let out = '';
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i], b = pts[i+1], seg = esc(text.slice(a, b));
    const cover = rs.filter(r => r.s <= a && r.e >= b).sort((x, y) => x.s - y.s || y.e - x.e).filter((r, i, a) => a.findIndex(z => z.crit === r.crit) === i);
    out += cover.map(r => { const q = r.q || reqById[r.crit] || {};
      return `<mark class="q t-${toneOf(q)}${q.mark === 'struck' ? ' struck' : ''}${q.accepted ? ' acc' : ''}${q.in_ask ? ' inask' : ''}" data-crit="${esc(r.crit)}">`; }).join('')
      + seg + cover.map(() => '</mark>').join('');
  }
  return out;
}
// one small mark per requirement on a paragraph that carries several (model output is shown, never merged): the
// paragraph's own mark first, then a dot for each of the others, stacked under it
function stackHtml(live){
  const more = live.length - 4;     // three dots at most under the mark, then "+N": the column never runs into a page label
  return live.slice(1, 4).map(q => `<i class="mk-i ${q.accepted ? 's-acc' : q.in_ask ? 's-ask' : ['miss', 'bad'].includes(toneOf(q)) ? 's-warn' : 's-doc'}" title="${esc(navWords(q))}"></i>`).join('')
    + (more > 0 ? `<i class="mk-n" title="${esc(live.slice(4).map(navWords).join(' · '))}">+${more}</i>` : '');
}
const UNSURE = ['missing', 'unclear'];       // INSUFFICIENT, or "can't tell": quotes are labelled neutrally
const EXCL_MARKS = ['applies', 'clear', 'unclear', 'part_shown', 'part_clear'];
function blockSay(b){
  const excl = (b.items||[]).some(i => i.role === 'exclusion' || i.role === 'part') && EXCL_MARKS.includes(b.mark);
  return (excl ? 'Must not apply: ' : '') + sayOf(b.mark, b.say);
}
// one chart quote: the exact lines, the note they sit under, the date written there, the page
function evqHtml(e, crit){
  const h = prettyHeading(e.heading), dt = e.date ? fmtDate(e.date) : '';
  const forSide = e.side === 'for';
  // for an exclusion the chart's "for" lines show that it applies and its "against" lines that it does not
  const ex = isExcl(reqById[crit]);
  // a ruling of "not in the chart yet" or "can't tell": the lines the check looked at are related, not proof either way
  const rel = UNSURE.includes((reqById[crit] || {}).mark);
  const word = rel ? 'Related lines' : ex ? (forSide ? 'Shows it applies' : "Shows it doesn't apply") : (forSide ? 'Supports' : 'Contradicts');
  const tone = rel ? 'rel' : ex ? (forSide ? 'against' : 'for') : (forSide ? 'for' : 'against');
  return `<div class="evq ${tone}" data-span="${esc(e.span)}" data-crit="${esc(crit)}" data-side="${esc(e.side)}" data-lines="${esc((e.lines||[]).join(' '))}" title="Click to report on this evidence">
      <span class="side">${word}</span><q>${esc(tidy(e.text))}</q>
      <small>${esc([h, h.includes(dt) ? '' : dt, e.page != null ? 'page ' + e.page : ''].filter(Boolean).join(' · '))}</small></div>`;
}
// an added requirement is taken off, not struck; every other one can be removed for this case
function changeCtl(it){
  if (!it.added) return strikeCtl(it);
  const a = it.added;
  return `<span class="added-note">Added for this case by ${esc(a.by || 'a person')}${a.at ? ' on ' + esc(fmtDate(a.at)) : ''}</span><a href="#" class="unadd" data-aid="${esc(a.id)}">Take it off</a>`;
}
function strikeCtl(it){
  return `<a href="#" class="strike-btn" data-strike="${esc(it.criterion)}" title="Remove this requirement for this case only">Not needed for this case</a>`;
}
// what was typed into a form that was closed before it was sent: kept for this page, given back when it reopens
const drafts = {};
document.addEventListener('input', e => {
  const t = e.target;
  if (t.matches && t.matches('.strike-why')) { drafts['strike:' + t.closest('.strike-form').dataset.crit] = t.value; strikeHint(t.closest('.strike-form')); }
  else if (t.id === 'fbText' || t.id === 'fbProposal') { const k = fbKey(); if (k) (drafts[k] ||= {})[t.id] = t.value; }
});
// why a requirement is not needed for this case: one tap on a reason (keys 1-6), a note when it helps. The reasons
// are the server's (app/strikes.REASONS); "Other" and a requirement the chart does not document need a written note
const reasons = () => (doc && doc.strike_reasons) || [];
const reasonLabel = code => (reasons().find(x => x.code === code) || {}).label || '';
function strikeForm(crit){
  const code = drafts['strikecode:' + crit] || '';
  return `<div class="strike-form" data-crit="${esc(crit)}" data-code="${esc(code)}"><div class="lbl" id="sf-${esc(crit)}">Why isn't it needed?</div>
    <div class="chips" role="radiogroup" aria-labelledby="sf-${esc(crit)}">${reasons().map((x, i) => `<button type="button" class="chip" role="radio" data-code="${esc(x.code)}" aria-checked="${x.code === code}" tabindex="${x.code === code || (!code && !i) ? 0 : -1}"><span class="n">${i + 1}</span>${esc(x.label)}</button>`).join('')}</div>
    <textarea class="strike-why" rows="2">${esc(drafts['strike:' + crit] || '')}</textarea>
    <div class="strike-act"><button class="primary strike-go">Remove for this case <kbd>${MOD}↵</kbd></button><button class="strike-cancel">Cancel</button><span class="hint strike-msg"></span></div></div>`;
}
// the note's placeholder says whether it is needed: for "Other", and for a requirement the chart does not document
function strikeHint(form){
  if (!form) return;
  const ta = form.querySelector('.strike-why'), code = form.dataset.code;
  const gap = groupGap(form.dataset.crit);
  ta.placeholder = gap ? 'Required: a sentence on why, for the person signing off' : code === 'other' ? 'Required: the reason' : 'Note (optional)';
}
// a removal of a requirement the chart does not document needs a real sentence: at least 3 words and 8 distinct
// letters, the same rule as app/strikes.real_sentence ("aaaaaaaaaaaa" is not a reason)
function realSentence(t){
  t = String(t || '');
  const words = t.match(/\p{L}+/gu) || [], letters = new Set((t.toLowerCase().match(/\p{L}/gu) || []));
  return words.length >= 3 && letters.size >= 8;
}
function pickReason(form, code){
  form.dataset.code = code;
  drafts['strikecode:' + form.dataset.crit] = code;
  form.querySelectorAll('.chip').forEach(c => { const on = c.dataset.code === code; c.setAttribute('aria-checked', on); c.tabIndex = on ? 0 : -1; });
  form.querySelector('.strike-msg').textContent = '';
  strikeHint(form);
  const gap = groupGap(form.dataset.crit);
  if (code === 'other' || gap) form.querySelector('.strike-why').focus();
  else form.querySelector(`.chip[data-code="${CSS.escape(code)}"]`).focus({ preventScroll: true });
}
// a removal's reason as it reads everywhere: the reason's label, then the note when one was written
function whyText(k){
  const lab = reasonLabel(k.code), note = String(k.reason || '').trim();
  return lab ? (note && note !== lab ? `${lab}: “${note}”` : lab) : note;
}
function struckHtml(it){
  const k = it.struck || {};
  if (k.removed_with) return `<div class="struck-why">Taken out with the requirement it is part of. Put that one back to restore it.</div>`;
  return `<div class="struck-why">${esc(whyText(k))} <span class="hint">${esc([k.by || 'a person', fmtDate(k.at)].filter(Boolean).join(' · '))}</span></div>
    <a href="#" class="unstrike" data-sid="${esc(idsOf(it.criterion).map(m => ((reqById[m] || {}).struck || {}).id).filter(Boolean).join(' ') || k.id)}">Put it back</a>`;
}
// the gaps between requirements: open one at a time (kept across redraws), or all at once ("Show whole guideline")
const openGaps = new Set();
const wholeOn = () => { try { return localStorage.getItem('review.whole') === '1'; } catch { return false; } };
function guidelineHtml(c){
  const t = c.tree || {};
  const hl = {};
  for (const r of (c.requirements||[])) if ((r.same || [r.criterion])[0] === r.criterion) for (const h of (r.highlights||[])) (hl[h.id] ||= []).push({ crit: cleadOf(r.criterion), q: r.near ? runQ(r.near) : null, start: h.start, end: h.end });
  const ind = s => (String(s).match(/^ */) || [''])[0].length;
  let docHtml = '';
  // lines are grouped into paragraphs (a new one at a blank line, a heading, a bullet or a numbered item): the Classic
  // style keeps one row per line (.para is display:contents), the Marker style lets a paragraph's lines flow as text.
  // The whole policy is here in document order. A requirement's paragraphs (and the heading over them) are open; each
  // run of other text between them is one quiet line ("⋯ 14 lines · p. 3–4") that opens in place; a run of two lines
  // or fewer just stays.
  const ITEM = /^\s*([•▪➢❖–\-]|\d+\.|[a-z]\.)\s/;
  const lo = s => s.lines.map(l => l.id).sort()[0] || '';
  const secs = [...(t.sections||[])].sort((a, b) => lo(a) < lo(b) ? -1 : 1), rest = c.rest || [], parts = [];
  let ri = 0;
  const takeRest = (before, tail) => { const ls = [];
    while (ri < rest.length && (before == null || rest[ri].id < before)) ls.push({ ...rest[ri++], kind: 'other', block: null, rest: true });
    if (ls.length) parts.push({ lines: ls, tail }); };
  for (const sec of secs) { takeRest(lo(sec)); parts.push(sec); }
  takeRest(null, true);
  let page = null, prevBlock = null;
  const lineHtml = ln => {
    const b = ln.block ? blocks[ln.block] : null;
    let h = '';
    if (ln.page !== page) { h += `<div class="pg" data-p="p. ${esc(ln.page)}">page ${esc(ln.page)}</div>`; page = ln.page; }
    const first = b && ln.block !== prevBlock;
    const live = b ? (b.items||[]).map(x => reqById[x.criterion]).filter(x => x && x.counted && x.mark !== 'struck' && (x.same || [x.criterion])[0] === x.criterion) : [];
    const acc = live.length && live.every(x => x.accepted);
    const ask = !acc && live.length && live.every(x => x.accepted || x.in_ask) && live.some(x => x.in_ask);
    const mark = first ? (acc ? ['✓', 'm-acc'] : ask ? ['→', 'm-inask'] : (MARK[b.mark] || ['',''])) : ['',''];
    const say = first ? `<span class="say ${mark[1]}">${acc ? 'Accepted' : ask ? 'In the ask' : b.bad ? `<span class="lbl">${esc(blockSay(b))}</span>` : esc(blockSay(b))}</span>` : '';
    prevBlock = ln.block;
    return h + `<div class="ln ${esc(ln.kind)} ${ln.rest ? 'rest' : ''} ${b ? 'b-' + esc(b.mark) : ''} ${acc ? 'b-acc' : ''} ${first ? 'first' : ''} ${ln.blank_before ? 'blank' : ''}" data-id="${esc(ln.id)}" ${first ? `id="${esc(b.id)}" data-block="${esc(b.id)}"` : b ? `data-block="${esc(b.id)}"` : ''}>
        <span class="mk ${mark[1]}" title="${b ? esc(acc ? 'Accepted' : ask ? 'In the ask' : blockSay(b)) : ''}">${mark[0]}${first && live.length > 1 ? stackHtml(live) : ''}</span><span class="tx" style="--ind:${ind(ln.text)}">${markedText(ln.text, hl[ln.id])}</span>${say}</div> `;
  };
  const paraHtml = p => `<div class="para" style="--ind:${ind(p[0].text)}">${p.map(lineHtml).join('')}</div>`;
  const gapHtml = run => {
    const ls = run.flat(), f = ls[0].text.trim().replace(/:$/, ''), p0 = ls[0].page, p1 = ls[ls.length - 1].page, n = `${ls.length} lines`;
    const head = (ls[0].kind === 'heading' || /^[A-Z][A-Z0-9 ,\/&()'’-]{3,}$/.test(f)) && f.length <= 48 ? (f === f.toUpperCase() ? f[0] + f.slice(1).toLowerCase() : f) : '';
    page = null;
    const body = run.map(paraHtml).join('');
    page = null;
    return `<details class="rest-fold" data-gap="${esc(ls[0].id)}" ${wholeOn() || openGaps.has(ls[0].id) ? 'open' : ''}><summary>${esc(head ? `${head} · ${n}` : `${n} · p. ${p0}${p1 !== p0 ? '–' + p1 : ''}`)}</summary>${body}<div class="rest-hint"><a href="#" class="gap-less">collapse</a></div></details>`;
  };
  let gaps = 0, codesDone = false;
  const codesHtml = (t.codes||[]).map(cd => { const ok = cd.outcome === 'judge';       // a code the guideline covers, listed beside the one that stopped the check
    return `<div class="sec"><div class="sec-label">The code table</div>` + (cd.lines||[]).map((l, i) =>
      `<div class="row-tbl ${ok ? '' : 'b-contradicted'}" data-id="${esc(l.id)}"><span class="mk ${ok ? '' : 'm-n'}">${i === 0 && !ok ? '✗' : ''}</span><span class="tx">${esc(l.text)}</span></div>`).join('') +
      `<div class="ev e-applies"><div class="it"><span class="st ${ok ? 'm-ev' : 'm-n'}">${esc(ok ? 'Covered: checked against the guideline' : cd.tag === 'investigational' ? 'Listed as investigational' : cd.tag === 'not_addressed' ? 'Listed, but this guideline does not decide it' : 'Listed as not covered')}</span>
        <small>Code ${esc(cd.code)}${cd.mapped ? ', matched from the procedure name' : ', as written in the case'} · page ${esc(cd.lines && cd.lines[0] ? cd.lines[0].page : '')}</small></div></div></div>`; }).join('');
  if (!secs.length && !(t.codes||[]).length) docHtml = `<div class="sec"><div class="ln other"><span class="mk"></span><span class="tx">No part of the guideline was checked for this order.</span></div></div>`;
  for (const sec of parts) {
    if (sec.tail && !codesDone) { docHtml += codesHtml; codesDone = true; }
    docHtml += `<div class="sec">${sec.label ? `<div class="sec-label">${esc(sec.label)}</div>` : ''}`;
    page = null; prevBlock = null;
    const paras = []; let para = null, prevKind = null, paraInd = 0;
    for (const ln of sec.lines) {
      const brk = !para || ln.blank_before || ITEM.test(ln.text) || ln.kind === 'heading' || prevKind === 'heading'
        || (ln.kind === 'gap') !== (prevKind === 'gap') || ind(ln.text) + 2 < paraInd;   // back out to a shallower indent
      if (brk) { paraInd = ind(ln.text); paras.push(para = []); }
      para.push(ln); prevKind = ln.kind;
    }
    const req = paras.map(p => p.some(ln => ln.block || hl[ln.id]));
    const keep = req.map((r, i) => r || (paras[i][0].kind === 'heading' && req[i + 1]));
    for (let i = 0; i < paras.length; ) {
      if (keep[i]) { docHtml += paraHtml(paras[i++]); continue; }
      let j = i; while (j < paras.length && !keep[j]) j++;
      const run = paras.slice(i, j); i = j;
      if (run.flat().length <= 2) docHtml += run.map(paraHtml).join(''); else { gaps++; docHtml += gapHtml(run); }
    }
    docHtml += '</div>';
  }
  if (!codesDone) docHtml += codesHtml;
  return (gaps ? `<div class="rest-hint"><a href="#" class="gl-all">${wholeOn() ? 'Show requirements only' : 'Show whole guideline'}</a></div>` : '') + docHtml;
}
// what a person changed on this case and where they looked, as the person signing off reads it
// removals appear once: the ones that were not in the chart sit in the amber box above; this lists only the rest
function changesHtml(so){
  const gaps = new Set(gapStrikes(doc || {}).map(k => k.id));
  const rest = (so.strikes || []).filter(k => !gaps.has(k.id));
  return (rest.length || !gaps.size ? removedHtml(rest) : '') + addedHtml(so.additions) + probedHtml();
}
function addedHtml(list){
  list = list || [];
  if (!list.length) return '';
  return `<div class="removed added"><b>Added for this case (${list.length})</b><ul>${list.map(k => `<li><a href="#" data-goto="${esc((k.spans||[])[0] || '')}">“${esc(trimDot(String(k.words || '').slice(0, 160)))}${String(k.words || '').length > 160 ? '…' : ''}”</a> <span class="hint">${esc([k.by, fmtDate(k.at)].filter(Boolean).join(' · '))}</span></li>`).join('')}</ul></div>`;
}
function probedHtml(){
  const n = new Set(((doc && doc.probes) || []).map(p => (p.spans || []).join(' '))).size;
  return n ? `<div class="removed probed-n">Asked about ${n} place${n > 1 ? 's' : ''} on the guideline; each is marked in the margin.</div>` : '';
}
function removedHtml(list){
  list = list || [];
  if (!list.length) return `<div class="removed none-removed">No requirement was removed for this case.</div>`;
  return `<div class="removed"><b>Removed for this case (${list.length})</b><ul>${list.map(k => `<li><a href="#" data-sel="${esc(k.criterion)}">“${esc(trimDot(k.words))}”</a> — ${esc(whyText(k))} <span class="hint">${esc([k.by, fmtDate(k.at)].filter(Boolean).join(' · '))}</span></li>`).join('')}</ul></div>`;
}
function confirmedHtml(d){
  const c = d.confirmation; if (!c) return '';
  const names = a => [...new Set((a||[]).map(x => nameOf(x.pathway)))].join(', ');
  const conf = names(c.confirmed), sug = names(c.suggested);
  const same = JSON.stringify((c.confirmed||[]).map(x => x.pathway).sort()) === JSON.stringify((c.suggested||[]).map(x => x.pathway).sort());
  return `<p class="confirmed">Pathway confirmed by <b>${esc(c.by || 'a person')}</b> on ${esc(fmtDate(c.at) || '—')}: <b>${esc(conf || '—')}</b>${same ? '' : ` (the guideline reader suggested ${sug ? '“' + esc(sug) + '”' : 'nothing'})`}</p>`;
}
const pageCount = ch => { const p = (ch||{}).pages; return Array.isArray(p) ? p.length : (typeof p === 'number' ? p : 0); };
const short = (w, n = 64) => { w = trimDot(String(w || '').replace(/\s+/g, ' ')); return w.length > n ? w.slice(0, n - 1).replace(/\s+\S*$/, '') + '…' : w; };
// the doc head's instruction shows until the first click or accept on this case (remembered in this browser)
const HINT_KEY = id => 'review.hint.' + id;
const hintSeen = id => { try { return localStorage.getItem(HINT_KEY(id)) === '1'; } catch { return false; } };
function hintDone(){
  if (!doc || hintSeen(doc.chart_id)) return;
  try { localStorage.setItem(HINT_KEY(doc.chart_id), '1'); } catch {}
  const h = $('.doc-hint'); if (h) h.remove();
}
// the pipeline found evidence; a person still reviews and accepts each requirement
function evidenceLine(){
  const p = (((doc || {}).case) || {}).progress || {}, n = p.of != null ? p.of : p.total;
  return n ? `Evidence found for all ${n} requirement${n > 1 ? 's' : ''}. Review and accept each.` : 'Evidence found. Review and accept each requirement.';
}
// the status line while evidence waits on a person, with the count, so the minimal header says it once
const evidenceVerdict = p => { const n = p.of != null ? p.of : p.total;
  return n ? `Evidence found for all ${n} requirement${n > 1 ? 's' : ''}. Accept each to sign off.` : 'Evidence found. Accept each to sign off.'; };
// the header's one sentence, following the state of the case
// ------------------------------------------------------------------ another tab, another person, the server down
// The page is one view of a case others may change. It looks again when the window comes back (focus, the tab shown
// again) and before the packet is copied; a case action answered 404 / 409 means the case is not what this tab drew:
// it is drawn again quietly with one calm line. A request that did not reach the server says so; nothing was saved.
// Errors are said in a line beside the control, never in a button's label.
const CHANGED = 'This case changed in another tab.';
let calmNext = '';
const calmTake = () => { const t = calmNext; calmNext = ''; return t; };
function calm(msg){ const el = $('#calmNote'); if (el) el.textContent = msg || ''; }
// what tells two versions of the document apart, the sign-off included (signing changes no file the version covers)
const docKey = d => { if (!d) return ''; const so = d.signoff || {}, rec = so.record || {};
  return [d.chart_id, d.state, d.version, so.state, rec.at, (rec.withdrawn || {}).at, !!d.nofit].join('|'); };
function showChanged(nd){
  calmNext = CHANGED;
  if (nd && nd.state === 'done' && nd.case && !nd.nofit && doc && doc.state === 'done') redraw(nd);
  else { calmNext = ''; load(nd ? nd.chart_id : current, true); }
}
async function changedElsewhere(){
  const id = current; if (!id) return;
  let nd;
  try { nd = await api('/review/' + encodeURIComponent(id)); }
  catch (e) { if (current !== id) return; if (e.status === 404) load(id, true); else calm(e.message); return; }
  if (current === id) showChanged(nd);
}
// a case action failed: 404 / 409 = the case changed under this tab; anything else is said where `say` puts it
function failed(e, say){
  if (e && (e.status === 404 || e.status === 409)) { changedElsewhere(); return; }
  const m = (e && e.message) || UNREACHABLE;
  if (say) say(m); else calm(m);
}
let rechecking = false;
async function recheck(){
  if (rechecking || !doc || !current || document.hidden || accepting) return;
  if (!['done', 'paused', 'failed'].includes(doc.state)) return;      // a running check polls by itself
  const id = current, k = docKey(doc);
  rechecking = true;
  try {
    const nd = await api('/review/' + encodeURIComponent(id));
    if (current === id && docKey(doc) === k && docKey(nd) !== k) showChanged(nd);
  } catch {} finally { rechecking = false; }
}
addEventListener('focus', recheck);
document.addEventListener('visibilitychange', () => { if (!document.hidden) recheck(); });

// a case ready only because requirements the chart did not document were removed says so wherever it is ready:
// the header, the signature stamp and the rail row, before and after sign-off
const gapWords = n => `Ready only because ${n} requirement${n > 1 ? 's' : ''} not in the case ${n > 1 ? 'were' : 'was'} removed.`;
function gapLineHtml(d){
  const n = gapStrikes(d).length, so = d.signoff || {}, r = ((d.case || {}).result) || {};
  if (!n || !(so.state === 'signed' || so.ready || r.queue === 'ready')) return '';
  return `<p class="flag gapflag" role="note">${esc(gapWords(n))} ${so.state === 'signed' ? 'The person signing off checked them.' : 'Read why before signing off.'}</p>`;
}
// one quiet line of facts: the guideline, the section and who confirmed it, the chart
// the sheet's head says which section was confirmed and by whom (and anything that belongs to no one requirement),
// quietly, above the policy it is about
function confHtml(d, np){
  const c = d.confirmation, sec = c && navOrder.length ? [...new Set((c.confirmed || []).map(x => nameOf(x.pathway)))].join(', ') : '';
  // the sheet starts with the policy (the owner's call): no confirmation line and no signature stamp on it; only the
  // review reasons tied to no requirement are said here, when there are any (the header carries the signed state and
  // the "removed while missing" warning)
  const bits = [...looseReasons(d)].filter(Boolean);
  return bits.length ? `<span class="doc-conf">${esc(bits.join(' · '))}</span>` : '';
}
// the review reasons that belong to no one requirement (the section picked, the checklist, the guideline's text),
// said in the facts line; a requirement's own reasons are said on it (its row's warm dot, a line in its panel), and
// a requirement a chart can't show already says so in its panel
function looseReasons(d){
  const c = d.case || {}, r = c.result || {};
  const tied = new Set((c.requirements || []).flatMap(x => x.reasons || []));
  return [...new Set(openReasons(c, r).filter(x => !tied.has(x) && !/cannot be shown by a case/.test(x)).map(plainReason))];
}
// a requirement's own review reason in a few words
function reqReason(t){
  const R = [[/notes for and against/, 'Notes disagree: read both'], [/measurements on both sides/, 'Measurements on both sides of the threshold'],
    [/^A note cited for/, "A cited note isn't in the case: read that part yourself"], [/^A date given for/, "A date isn't near its note: check it"],
    [/^A measurement for/, "A measurement isn't in its note: check it"], [/marked documented without a quoted note/, 'Marked documented without a quote: read the case'],
    [/was not assessed/, 'Not assessed: check it by hand'], [/needs a dated start note/, 'Needs a dated start note and a dated latest note']];
  for (const [re, out] of R) if (re.test(t)) return out;
  return plainReason(t);
}
const shortDate = iso => { const m = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? `${MONTHS[+m[2]-1].slice(0, 3)} ${+m[3]}` : ''; };
// the review reasons as short plain sentences: no guideline text quoted inside, no percentage; two shown, the rest
// behind "N more"
function plainReason(t){
  t = String(t || '').replace(/\s*\(\d+%\)/g, '');
  let m;
  if ((m = t.match(/^The (?:section|pathway) was chosen by (.+?): “(.+?)” \(the guideline reader suggested (?:“(.+?)”|nothing)\)/)))
    return `${m[1] === myName() ? 'You' : m[1]} picked ${m[2]}; the check ${m[3] ? 'suggested ' + m[3] : 'suggested no indication'}.`;
  const R = [
    [/was not assessed/, 'One requirement was not assessed; check it by hand.'],
    [/^A note cited for/, 'A note cited by the check could not be found in the case; read that part yourself.'],
    [/marked documented without a quoted note/, 'One requirement was marked documented without a quote; read the case yourself.'],
    [/notes for and against/, 'The case has notes for and against one requirement; read both.'],
    [/^A date given for/, 'A date could not be found near its note; check the dates by hand.'],
    [/^A measurement for/, 'A measurement could not be found in its note; check it by hand.'],
    [/measurements on both sides/, 'The case has measurements on both sides of a threshold; confirm which one applies.'],
    [/^The dated notes for .+ span ([\d.]+) months .*less than the ([\d.]+) required/, null],
    [/needs a dated start note/, 'A duration needs a dated start note and a dated latest note; check the dates.'],
    [/cannot be shown by a case/, "One requirement can't be shown by a case; confirm it outside the case."],
    [/less certain than usual/, 'The check is less certain than usual on this case; read the quoted notes.'],
    [/could not be fully built/, 'The checklist could not be fully built from the guideline; read the indication.'],
    [/^No requirements were built for/, 'No requirements were built for one indication.'],
    [/could not be read cleanly/, 'Part of the guideline could not be read cleanly; open “How this was decided”.'],
    [/^The case gives .+ matched to (\S+)/, null],
  ];
  for (const [re, out] of R) {
    const x = t.match(re); if (!x) continue;
    if (out) return out;
    if (/months/.test(re.source)) return `The dated notes span ${x[1]} months, less than the ${x[2]} required; check the dates.`;
    return `The procedure was matched to code ${x[1]} from its name; confirm the code.`;
  }
  return t.replace(/“[^”]{30,}”/g, 'a requirement');
}
// the reasons still open: the ones asking to confirm, outside the chart, what no chart shows close once each is confirmed
function openReasons(c, r){
  const outside = (c.requirements || []).filter(x => x.mark === 'confirm');
  const done = outside.length && outside.every(x => x.accepted);
  return (r.review_reasons || []).filter(x => !(done && (r.confirm_reasons || []).includes(x)));
}
// a requirement's state as the packet reads it
// driven by the server's `proof` (review.case_view): a requirement the chart documents, or an exclusion the chart
// shows does not apply, is proof; anything else goes to the ask
function stateOf(r){
  if (r.mark === 'struck') return ['struck', 'Removed for this case'];
  if (!r.proof) return r.in_ask ? ['inask', 'In the ask'] : ['ask', ruling(r)[2] + ' · not in the ask yet'];
  if (r.accepted) return ['ok', r.mark === 'confirm' ? 'Confirmed outside the case' : 'Accepted'];
  return ['open', ruling(r)[2] + ' · not accepted yet'];
}
const isExcl = r => r && (r.role === 'exclusion' || r.role === 'part');
// how a requirement's ruling reads: [glyph, class, words]. An exclusion reads as an exclusion: it must not apply
function ruling(r){
  if (r.mark === 'struck') return ['—', 'm-o', 'Removed for this case'];
  if (isExcl(r)) {
    if (r.proof) return ['•', 'm-ev', "Evidence it doesn't apply to this patient"];
    const who = surgeonName(((doc || {}).case || {}).surgeon);
    return r.excl === 'NOT_MET' ? ['✗', 'm-n', `Applies: ask ${who}`] : ['?', 'm-q', `Can't tell from the case: ask ${who}`];
  }
  const [g, cls] = MARK[r.mark] || ['', ''];
  return [g, cls, sayOf(r.mark, r.say)];
}
const navWords = r => (isExcl(r) ? 'Must not apply: ' : '') + label(r.words);
// a 3-6 word label from a requirement's own words, by code, the same every time: filler out ("There is",
// "documentation of", "the following"), parentheticals out, numbers and units kept ("at least 3 millimeters" ->
// "≥ 3 mm"); the full words stay on the sheet and in the panel
function label(w){
  let t = ' ' + String(w || '').replace(/\([^)]*\)/g, ' ').replace(/\*/g, '').replace(/[;:,.]?\s*(AND|OR)\s*$/, '') + ' ';
  const rw = [
    [/\b(?:conservative management including )?(compression(?: therapy| stockings)?)\b.*?\bfor at least (\d+) months\b.*/i, ' $2 months of compression '],
    [/^.*?\bsymptoms are associated with\b/i, ' Symptoms from '],
    [/\b(?:significantly )?interfere with activities of daily living\b/i, ' affect daily living '],
    [/\bare at least (\d+(?:\.\d+)?) millimeters?\b/i, ' ≥ $1 mm '], [/\bat least (\d+(?:\.\d+)?) millimeters?\b/i, ' ≥ $1 mm '],
    [/\bat least (\d+(?:\.\d+)?) /i, ' ≥ $1 '], [/\bmillimeters?\b/gi, ' mm '], [/\bin size\b/gi, ' '],
    [/\bclass\b/gi, ' '], [/\bor greater\b/gi, ' or greater '],
  ];
  for (const [re, to] of rw) t = t.replace(re, to);
  const FILL = /^\s*(there is|there are|documentation of|documented|demonstrated|the patient has|the following|the|a|an)\s+/i;
  for (let i = 0; i < 6 && FILL.test(t); i++) t = t.replace(FILL, ' ');
  // a parenthetical taken out never leaves a space before the punctuation after it ("Federal Employee Program: Follow")
  t = t.replace(/\s+/g, ' ').replace(/\s+([,;:.])/g, '$1').trim().replace(/[,;:.]+$/, '');
  const ws = t.split(' ');
  if (ws.length > 6) t = ws.slice(0, 6).join(' ').replace(/\s+(of|and|or|to|with|the|a|in|for|by)$/i, '') + '…';
  return t ? t[0].toUpperCase() + t.slice(1) : short(w, 40);
}

// the case's progress in words, the same everywhere: over every requirement that counts ("4 of 6 accepted · 2 in
// the ask"), what is still to ask split by why, and the removals
function progWords(p, bold){
  const B = x => bold ? `<b>${x}</b>` : String(x), by = p.to_ask_by || {}, of = p.of != null ? p.of : p.total;
  const bits = of ? [`${B(`${p.accepted || 0} of ${of}`)} accepted`] : [];
  if (p.in_ask) bits.push(`${B(p.in_ask)} in the ask`);
  if (p.to_ask_by) {
    if (by.missing) bits.push(`${B(by.missing)} not in the case`);
    if (by.contradicted) bits.push(`${B(by.contradicted)} contradicted`);
    if (by.applies) bits.push(`${B(by.applies)} ${by.applies > 1 ? 'exclusions apply' : 'exclusion applies'}`);
  } else if (p.to_ask) bits.push(`${B(p.to_ask)} to ask`);
  if (p.struck) bits.push(`${B(p.struck)} struck`);
  return bits.join(' · ');
}
// the slim summary that fills as the coordinator works
function progHtml(d){
  const c = d.case, p = c.progress || {}, so = d.signoff || {};
  if (!navOrder.length) return `<div class="prog" id="prog"><div class="n">${esc((c.result || {}).determination === 'NOT_COVERED'
    ? 'Nothing to accept: the guideline stops at the code.' : 'Nothing to accept: no requirement was checked for this order.')}</div></div>`;
  const ticks = navOrder.map(id => { const [k] = stateOf(reqById[id]); return `<i class="${k}"></i>`; }).join('');  // ok · inask · ask · struck · open
  const signed = so.state === 'signed';
  // sign-off lives in one place: the packet panel, beside the packet's actions (never a second button up here)
  const btn = signed ? `<span class="prog-done">Signed off by ${esc((so.record || {}).by || '')}</span>` : '';
  // only the bar: the count words are its title (hover) and its label (screen readers); the packet box keeps its count
  const words = progWords(p, false);
  return `<div class="prog" id="prog"><div class="ticks" role="img" aria-label="${esc(words)}" title="${esc(words)}">${ticks}</div>${btn}</div>`;
}
function signReason(d){
  const c = d.case, p = c.progress || {}, r = c.result || {};
  const asks = (p.asks || []).length;
  if (asks) return `${asks} requirement${asks > 1 ? 's are' : ' is'} not in the case yet; ask ${surgeonName(c.surgeon)} first${p.to_ask ? ` (add ${p.to_ask > 1 ? 'them' : 'it'} to the ask)` : ''}.`;
  if ((p.open || []).length) return `Accept or remove ${p.open.length} more requirement${p.open.length > 1 ? 's' : ''} to sign off.`;
  if (!(d.signoff || {}).ready) return 'This case has something to look at before it can be signed off.';
  return '';
}
// the left column: "Requirements" (what is still to be approved: open, in the ask, struck) and under it "The packet",
// a dark-blue box that grows as requirements are accepted (or confirmed outside the chart); an accepted row moves
// from the list into the box, an undo moves it back
const inPacket = r => !!(r && unitsOf(r.criterion).every(u => (reqById[u] || {}).accepted && reqById[u].mark !== 'struck'));
const navSeq = () => navOrder.filter(id => !inPacket(reqById[id])).concat(navOrder.filter(id => inPacket(reqById[id])));
const navOpen = new Set();      // the rows of several requirements that are open
let packetWas = null;           // {chart, ids}: what the box held at the last draw, so a row that changed sides lands briefly
function navRow(id){
  const r = reqById[id], [k, w] = stateOf(r), rs = (r.reasons || []).map(reqReason);
  const moved = packetWas && packetWas.chart === (doc || {}).chart_id && packetWas.ids.has(id) !== inPacket(r);
  const us = unitsOf(id), open = navOpen.has(id), ask = us.some(u => reqById[u].in_ask);
  const cnt = us.length > 1 ? `<span class="nv-n" data-tog="${esc(id)}" role="button" aria-expanded="${open}" title="${us.length} requirements on these words">${us.length}</span>` : '';
  const subs = open ? us.map(u => `<span class="nv-sub">${esc(navWords(reqById[u]))}${reqById[u].accepted ? ' ✓' : reqById[u].in_ask ? ' · in the ask' : ''}</span>`).join('') : '';
  return `<button class="nv st-${k} t-${toneOf(r)}${rs.length ? ' rsn' : ''}${moved ? ' moved' : ''}" data-crit="${esc(id)}" title="${esc(trimDot(r.words) + ' — ' + [w, ...rs].join(' · '))}"><span class="dot" aria-hidden="true"></span><span class="nv-w">${esc(navWords(r))}</span>${inPacket(r) ? '<span class="ck" aria-label="accepted">✓</span>' : ask ? '<span class="ia">In the ask</span>' : ''}${cnt}${subs}</button>`;
}
function navHtml(){
  if (!navOrder.length) return '<div class="nv-empty">No requirements to accept for this order.</div>';
  const p = ((doc || {}).case || {}).progress || {}, of = p.of != null ? p.of : (p.total || navOrder.length);
  const left = navOrder.filter(id => !inPacket(reqById[id])), got = navOrder.filter(id => inPacket(reqById[id]));
  const h = `<div class="nv-h">Requirements</div>` + (left.length ? left.map(navRow).join('') : '<div class="nv-none">Nothing left to approve.</div>')
    + `<div class="pk-box${got.length ? '' : ' empty'}" id="pkBox" role="group" aria-label="The packet"><div class="pk-box-h">The packet <span class="pk-box-n">· ${got.reduce((n, id) => n + unitsOf(id).length, 0)} of ${of}</span></div>${got.map(navRow).join('')}</div>`;
  packetWas = { chart: (doc || {}).chart_id, ids: new Set(got) };
  return h;
}

// ------------------------------------------------------------------ the tree view: the same decision as an outline
// app/tree.outline compiles every group's status from its children (met · ask · open · contradicted) after strikes
// and additions; the page only words it. Leaves are the requirements, drawn as the navigator draws them.
const hasTree = c => !!(c && c.logic && (c.logic.sections || []).length);
const curView = () => hasTree((doc || {}).case) ? view : 'guideline';
const GROUP_WORDS = n => ({ all: 'All of these', any: 'One of these is enough', at_least: `At least ${n.k} of these`,
  none: n.n > 1 ? 'None of these may apply' : 'This must not apply', not_all: 'These may not all apply together' })[n.op] || '';
const GROUP_SAY = { met: 'Evidence found', ask: 'Waiting on the ask', open: 'Not shown yet', contradicted: 'Contradicted' };
// a group is "Accepted" only once a person accepted every requirement under it that counts
function groupAccepted(n){
  const leaves = [], walk = x => { if (x.criterion) { if (!x.dim) leaves.push(reqById[x.criterion]); } else (x.kids || []).forEach(walk); };
  walk(n);
  const live = leaves.filter(r => r && r.counted && r.mark !== 'struck');
  return live.length > 0 && live.every(r => r.accepted);
}
const DIM_SAY = { not_needed: 'Not needed: another option is met', other_option: 'Another option; not the one being completed' };
function viewBarHtml(c){
  if (!hasTree(c)) return '';
  const v = curView(), b = (k, w) => `<button type="button" role="radio" data-view="${k}" aria-checked="${v === k}" tabindex="${v === k ? 0 : -1}">${w}</button>`;
  return `<div class="view-bar"><div class="seg" role="radiogroup" aria-label="View">${b('guideline', 'Guideline')}${b('tree', 'Tree')}</div><span class="view-key"><kbd>t</kbd> switch</span></div>`;
}
function leafHtml(n){
  const r = reqById[n.criterion]; if (!r) return '';
  // an option another one made unneeded is set aside only once that one is accepted (the server's `dim`)
  const [k, w] = stateOf(r), dim = n.dim || ('dim' in r ? r.dim : (QUIET.includes(r.mark) && r.mark !== 'struck' && r.mark !== 'confirm' ? r.mark : null));
  if (!dim && cleadOf(n.criterion) === n.criterion && !treeOrder.includes(n.criterion)) treeOrder.push(n.criterion);    // the keys step through what counts, as the navigator does
  const tail = dim ? `<span class="tl-s">${esc(DIM_SAY[dim] || '')}</span>`
    : r.accepted && r.mark !== 'struck' ? '<span class="ck" aria-label="accepted">✓</span>'
    : r.in_ask ? '<span class="ia">In the ask</span>'
    : n.route ? '<span class="tl-s">Or: another route; needs its own evidence</span>'
    : r.mark === 'not_needed' ? `<span class="tl-s">${esc(r.say || '')}</span>`
    : r.mark === 'struck' ? '<span class="tl-s">Removed for this case</span>'
    : !r.proof ? `<span class="tl-s">${esc(ruling(r)[2])}</span>` : '';
  return `<li class="tn tn-leaf${dim ? ' dim' : ''}"><button type="button" class="tl st-${k} t-${toneOf(r)}${(r.reasons || []).length ? ' rsn' : ''}" data-crit="${esc(n.criterion)}" aria-label="${esc(trimDot(r.words) + ' — ' + (dim ? DIM_SAY[dim] : w))}">`
    + `<span class="dot" aria-hidden="true"></span><span class="tl-w"><span class="tl-t">${esc(navWords(r))}</span></span>${tail}`
    + `<span class="tl-full" aria-hidden="true">${isExcl(r) ? '<b>Must not apply</b> ' : ''}“${esc(trimDot(r.words))}”</span></button></li>`;
}
function groupHtml(n, top){
  if (n.criterion) return leafHtml(n);
  const dim = !!n.dim;
  const say = dim ? DIM_SAY[n.dim] : n.status === 'met' && groupAccepted(n) ? '✓ Accepted' : GROUP_SAY[n.status];
  return `<li class="tn tn-group s-${esc(n.status)}${dim ? ' dim' : ''}${top ? ' top' : ''}"><div class="tg-h"><span class="tg-w">${esc(GROUP_WORDS(n))}</span><span class="tg-s">${esc(say || '')}</span></div>`
    + `<ul class="tg-k">${n.kids.map(k => groupHtml(k, false)).join('')}</ul></li>`;
}
function treeHtml(d){
  const c = d.case; treeOrder = [];
  if (!hasTree(c)) return '';
  const L = c.logic, p = c.progress || {}, so = d.signoff || {};
  const ready = L.status === 'met', n = (L.waiting || []).length;
  const signed = so.state === 'signed';
  const verdict = ready ? (signed ? 'Signed off' : so.can_sign ? 'Ready for sign-off' : 'Evidence found, accept each to sign off') : `Waiting on ${n} item${n === 1 ? '' : 's'}`;
  const counts = { ask: 0, open: 0, contradicted: 0, applies: 0 };
  for (const id of (L.waiting || [])) { const r = reqById[id]; if (!r) continue; counts[r.in_ask ? 'ask' : r.mark === 'applies' ? 'applies' : ['contradicted', 'part_shown'].includes(r.mark) ? 'contradicted' : 'open']++; }
  const sub = ready ? progWords(p, false)
    : [counts.ask ? `${counts.ask} in the ask` : '', counts.open ? `${counts.open} not in the case` : '', counts.contradicted ? `${counts.contradicted} contradicted` : '',
       counts.applies ? `${counts.applies} ${counts.applies > 1 ? 'exclusions apply' : 'exclusion applies'}` : ''].filter(Boolean).join(' · ');
  const st = ready && !signed && !so.can_sign ? 'evidence' : L.status;
  // no count line under the verdict (the owner's call): the counts are the header bar's title and the root's tooltip
  let h = `<div class="tr-root s-${esc(st)}"${sub ? ` title="${esc(sub)}"` : ''}><span class="tr-v">${esc(verdict)}</span></div>`;
  for (const s of L.sections) {
    h += `<section class="tr-sec">${L.sections.length > 1 || s.name ? `<div class="tr-name">${esc(s.name || nameOf(s.pathway))}</div>` : ''}<ul class="tr" role="list">${groupHtml(s.tree, true)}</ul></section>`;
  }
  const struck = (c.requirements || []).filter(r => r.mark === 'struck' && r.counted);
  if (struck.length) h += `<section class="tr-sec tr-struck"><div class="tr-name">Removed for this case</div><ul class="tr" role="list"><li class="tn tn-group top"><ul class="tg-k">${struck.map(r => leafHtml({ criterion: r.criterion })).join('')}</ul></li></ul></section>`;
  return `<div class="doc tree-doc" id="treeDoc">${h}</div>`;
}
// the order ↑/↓ walks: the navigator's, or in the tree view the same requirements in the tree's reading order
const stepOrder = () => curView() === 'tree' && treeOrder.length ? treeOrder : navSeq();
// the element that stands for a requirement in the view on screen: its words in the guideline, or its leaf
function placeOf(id){
  if (!id) return null;
  if (curView() === 'tree') return document.querySelector(`#treeDoc .tl[data-crit="${CSS.escape(id)}"]`);
  return document.querySelector(`mark.q[data-crit="${CSS.escape(id)}"]`) || document.querySelector('.gl .ln.sel');
}
// switch the middle column; the address and this browser remember it. The highlighter has nothing to draw in the
// tree: it measures again either way (nothing to draw, or the guideline's words back where they are)
function setView(v, how){
  view = v === 'tree' ? 'tree' : 'guideline';
  try { localStorage.setItem(VIEW_KEY, view); } catch {}
  applyView(how);
}
function applyView(how){
  const g = $('#glDoc'); if (!g) return;
  const v = curView();
  if (g.dataset.view !== v && (probe || $('.ask-card'))) closeCard(true);
  if (g.dataset.view !== v) hideFb();
  g.dataset.view = v;
  for (const b of $$('.view-bar [data-view]')) { const on = b.dataset.view === v; b.setAttribute('aria-checked', String(on)); b.tabIndex = on ? 0 : -1; }
  if (hasTree((doc || {}).case)) try {
    const u = new URL(location.href);
    if (v === 'tree') u.searchParams.set('view', 'tree'); else u.searchParams.delete('view');
    if (u.href !== location.href) history.replaceState(history.state, '', u.pathname + u.search + u.hash);
  } catch {}
  if (how === 'switch' && selectedCrit) scrollToEl(placeOf(selectedCrit), 'instant');
  marksRefresh();
}

function renderCase(d){
  const c = d.case, r = c.result || {}, o = d.order || {}, g = d.guideline || {};
  if (d.gate && d.gate.pathways) { pwNames = Object.fromEntries(d.gate.pathways.map(p => [p.id, p.name])); pwLabels = Object.fromEntries(gateIndications(d.gate.pathways).map(x => [x.p.id, x.label])); }
  indexCase(c);
  selectedCrit = null; fbSel = null; fbKind = null; probe = null; anchorLine = null;
  const s = STATE[r.determination] || STATE.CANT_CHECK, name = surgeonName(c.surgeon || d.surgeon);
  let verdict = typeof s.verdict === 'function' ? s.verdict(name) : s.verdict, vcls = s.v;
  if (r.determination === 'MET' && r.needs_review && !(d.signoff || {}).ready) { verdict = 'Looks ready; worth a second look first.'; vcls = 'v-needs'; }
  // "Ready for sign-off" only once sign-off is possible; until then the evidence waits on a person
  else if (r.determination === 'MET' && (d.signoff || {}).state !== 'signed') { verdict = (d.signoff || {}).can_sign ? 'Ready for sign-off.' : evidenceVerdict(c.progress || {}); }
  const glName = glTitle(g);
  const ch = c.chart || {}, np = pageCount(ch);
  $('#main').innerHTML = `<div class="case">
    ${whoHtml(d, viewBarHtml(c))}
    <p class="verdict ${vcls}">${esc(verdict)}</p>
    ${gapLineHtml(d)}
    <p class="calm-note" id="calmNote" role="status" aria-live="polite">${esc(calmTake())}</p>
    ${progHtml(d)}
    <div class="case-grid">
      <nav class="rq-nav" id="rqNav" aria-label="Requirements and the packet">${navHtml()}</nav>
      <div class="tv gl" id="glDoc" data-view="${curView()}"><div class="doc gl-doc">
        <div class="doc-head">${glKicker(g) ? `<span class="doc-kicker">${esc(glKicker(g))}</span>` : ''}<b>${esc(glName)}</b>${confHtml(d, np)}${!navOrder.length ? `<span>Where the guideline lists this order's code.</span>`
          : hintSeen(d.chart_id) ? '' : `<span class="doc-hint">The confirmed indication in the payer's own words. Click a requirement to see the case's evidence beside it; select any lines to ask what the case shows.</span>`}</div>
        ${guidelineHtml(c)}</div>${treeHtml(d)}</div>
      <aside class="sidepanel" id="side" aria-label="Evidence and the packet"></aside>
    </div>
    <div class="fb-list" id="fbList"></div>
    ${setAsideHtml(c)}${foldHtml(d)}${styleSwitchHtml()}</div>`;
  renderFeedback();
  markProbes();
  // each requirement is one Tab stop in the guideline (its first marked words), in reading order; Enter opens it
  const seen = new Set();
  for (const m of $$('#glDoc mark.q[data-crit]')) {
    const id = m.dataset.crit; if (seen.has(id) || !reqById[id]) continue; seen.add(id);
    m.tabIndex = 0; m.setAttribute('role', 'button'); m.setAttribute('aria-label', `Requirement: ${trimDot(reqById[id].words)}. ${stateOf(reqById[id])[1]}`);
  }
  showPacket();
  $('#rqNav').onclick = e => {
    const t = e.target.closest('.nv-n'); if (t) { const k = t.dataset.tog; navOpen.has(k) ? navOpen.delete(k) : navOpen.add(k); $('#rqNav').innerHTML = navHtml(); const cur = selectedCrit && $(`.nv[data-crit="${CSS.escape(selectedCrit)}"]`); if (cur) cur.setAttribute('aria-current', 'true'); return; }
    const b = e.target.closest('.nv[data-crit]'); if (b) selectRequirement(b.dataset.crit); };
  // the toggle, and a leaf of the tree opens the same panel as the requirement's words do
  for (const b of $$('.view-bar [data-view]')) b.onclick = () => { if (curView() !== b.dataset.view) setView(b.dataset.view, 'switch'); };
  const vb = $('.view-bar .seg');
  if (vb) vb.onkeydown = e => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); e.stopPropagation(); setView(curView() === 'tree' ? 'guideline' : 'tree', 'switch'); const on = $('.view-bar [aria-checked="true"]'); if (on) on.focus({ preventScroll: true }); } };
  const td = $('#treeDoc');
  if (td) td.onclick = e => { const b = e.target.closest('.tl[data-crit]'); if (b) { hintDone(); selectRequirement(b.dataset.crit, true); b.focus({ preventScroll: true }); } };
  applyView();
  wireStyleSwitch();
  const gl = $('#glDoc');
  // a shift-click widens the feedback range; it must not also start a text selection
  gl.onmousedown = e => { clearTimeout(askTimer); if (e.shiftKey && e.target.closest('.ln[data-id]')) e.preventDefault(); };
  gl.onclick = e => {
    const ws = window.getSelection();
    if (ws && !ws.isCollapsed && gl.contains(ws.anchorNode)) return;   // the end of a drag, not a click on a line
    if (e.target.closest('.fb-chip') || e.target.closest('a') || e.target.closest('summary')) return;
    const ln = e.target.closest('.ln[data-id]'); if (!ln) return;
    if (probe) closeCard(true);
    const mk = e.target.closest('mark.q');
    const hits = []; for (let m = mk; m; m = m.parentElement && m.parentElement.closest('mark.q')) hits.push(m.dataset.crit);
    const seq = navSeq(), stack = [...new Set(hits)].sort((a, b) => (seq.indexOf(a) + 1 || 1e9) - (seq.indexOf(b) + 1 || 1e9));
    const pickMk = stack.length > 1 && stack.includes(selectedCrit) ? stack[(stack.indexOf(selectedCrit) + 1) % stack.length] : stack[0];
    const crits = mk ? [pickMk] : (lineCrits[ln.dataset.id] || (ln.dataset.block && blocks[ln.dataset.block] ? blocks[ln.dataset.block].items.map(i => i.criterion) : []));
    if (e.shiftKey) { pickLine(ln.dataset.id, true); return; }
    anchorLine = ln.dataset.id;
    if (crits.length) { hideFb(); selectRequirement(crits.includes(selectedCrit) && !mk ? selectedCrit : crits[0], true); }
    else pickLine(ln.dataset.id, false);
  };
  $('#side').onclick = e => sideClick(e, d);
  const sa = $('#setAside');
  if (sa) sa.onclick = e => {
    const b = e.target.closest('.sa-ask'); if (!b) return;
    e.preventDefault(); b.disabled = true; b.textContent = 'Asking…';
    post('/review/' + d.chart_id + '/unprune', { criterion: b.dataset.crit, by: myName() || null })
      .then(nd => redraw(nd, b.dataset.crit)).catch(err => { b.disabled = false; b.textContent = 'Ask it anyway'; failed(err); });
  };
  marksRefresh();
}
// admin lines step H set aside for this case (billing, paperwork, headings: app/admin.py): never asked or counted;
// folded at the foot of the page, each with "Ask it anyway"
function setAsideHtml(c){
  const list = c.set_aside || [];
  if (!list.length) return '';
  return `<details class="set-aside" id="setAside"><summary>Not asked of the case (${list.length})</summary><ul>${list.map(x =>
    `<li><span class="sa-q">“${esc(trimDot(short(x.words, 140)))}”</span> <span class="sa-why">· ${esc(x.why)}${x.source && x.source.page ? ` · page ${esc(x.source.page)}` : ''}</span> <button class="sa-ask" data-crit="${esc(x.criterion)}">Ask it anyway</button></li>`).join('')}</ul></details>`;
}

// from the rail: open the first requirement still waiting on the coordinator (not accepted, or not yet in the ask)
function landOnWork(){
  const p = (doc.case || {}).progress || {};
  const next = stepOrder().find(id => { const r = reqById[id]; return r.mark !== 'struck' && !r.accepted && !r.in_ask; });
  if (next && (p.open || []).concat(p.asks || []).includes(next)) selectRequirement(next);
}

// ------------------------------------------------------------------ the side panel
// On a phone the panel is a bottom sheet. It rests as a peek bar (the case's progress) so the guideline has the
// screen; a tap or an upward swipe opens it; opening a requirement opens it with a ‹ › stepper in its bar; a downward
// swipe or Close lets it rest again. On a wide screen the bar is hidden and nothing here changes anything.
let sheetOpen = false;
const narrow = () => matchMedia('(max-width:820px)').matches;
function sheetBar(){
  const p = ((doc || {}).case || {}).progress || {};
  if (panelMode === 'req') {
    const i = stepOrder().indexOf(selectedCrit), n = stepOrder().length;
    return `<div class="sheet-bar sb-step"><button type="button" class="sb-prev" aria-label="Previous requirement" ${i <= 0 ? 'disabled' : ''}>‹</button>
      <span class="sb-title">${i >= 0 ? `Requirement ${i + 1} of ${n}` : 'Requirement'}</span><button type="button" class="sb-next" aria-label="Next requirement" ${i < 0 || i >= n - 1 ? 'disabled' : ''}>›</button></div>`;
  }
  const words = progWords(p, false);
  return `<button type="button" class="sheet-bar sb-toggle" aria-expanded="${sheetOpen}"${words ? ` title="${esc(words)}"` : ''}><span class="sb-sum"><b>${navOrder.length ? 'The packet' : 'The next step'}</b></span><span class="sb-chev" aria-hidden="true"></span></button>`;
}
function setSide(html){
  const side = $('#side'); if (!side) return;
  if (panelMode !== 'packet') sheetOpen = true;
  side.innerHTML = sheetBar() + html;
  side.classList.toggle('peek', panelMode === 'packet' && !sheetOpen);
}
function setSheet(open){
  sheetOpen = open;
  if (!open && panelMode !== 'packet') { closeSide(); return; }
  const side = $('#side'); if (!side) return;
  side.classList.toggle('peek', panelMode === 'packet' && !open);
  const t = side.querySelector('.sb-toggle'); if (t) t.setAttribute('aria-expanded', String(open));
  if (open) side.scrollTop = 0;
}
// a swipe on the sheet's bar: up opens, down lets it rest
(function(){
  let y0 = null;
  document.addEventListener('touchstart', e => { const b = e.target.closest && e.target.closest('#side .sheet-bar'); y0 = b && e.touches.length === 1 ? e.touches[0].clientY : null; }, { passive: true });
  document.addEventListener('touchend', e => {
    if (y0 == null) return; const dy = e.changedTouches[0].clientY - y0; y0 = null;
    if (Math.abs(dy) < 36) return;
    e.preventDefault();                          // a swipe, not a tap on the bar
    setSheet(dy < 0);
  }, { passive: false });
})();
function sideHead(kicker, close){ return `<div class="sp-head"><span class="sp-kicker">${kicker}</span>${close ? '<a href="#" class="sp-x" title="Close (Esc)">Close <kbd>Esc</kbd></a>' : ''}</div>`; }
// nothing selected: the packet as it is being built
function showPacket(){
  if (!doc || !doc.case) return;
  if (panelMode !== 'packet') sheetOpen = false;   // back from a requirement or an answer: the sheet rests
  panelMode = 'packet'; selectedCrit = null;
  $$('.sel').forEach(x => x.classList.remove('sel')); $$('.nv[aria-current], .tl[aria-current]').forEach(x => x.removeAttribute('aria-current'));
  const d = doc, c = d.case, r = c.result || {}, p = c.progress || {}, so = d.signoff || {}, rec = so.record || {};
  const name = surgeonName(c.surgeon || d.surgeon), signed = so.state === 'signed';
  if (!navOrder.length) {           // the code stopped the check (or nothing was judged): the message is the work
    sheetOpen = true;                // nothing to step through: the next step is the whole of the work
    setSide(`<div class="next pk-panel">${sideHead('The next step', false)}
      <h2>${esc(r.determination === 'NOT_COVERED' ? `Review with ${name}` : "This guideline can't decide this order")}</h2>
      <p class="pk-sub">${esc(r.reason || '')}</p>
      ${c.ask || d.ask ? `<div class="act"><button class="primary" id="msgBtn">Message ${esc(name)}</button><span class="hint" id="copyMsg"></span></div><div class="draft" id="draft"></div>` : ''}</div>`);
    const mb = $('#msgBtn');
    if (mb) mb.onclick = async () => { const t = c.ask || d.ask; $('#draft').textContent = t; $('#draft').classList.add('show');
      try { await navigator.clipboard.writeText(t); $('#copyMsg').textContent = 'Copied.'; } catch { $('#copyMsg').textContent = 'Shown below; select and copy.'; } };
    return;
  }
  const title = signed ? 'Signed off' : so.can_sign ? 'Ready to sign off' : 'Building the packet';
  const list = navOrder.map(id => { const q = reqById[id], [k, w] = stateOf(q);
    return `<li class="pk st-${k}"><a href="#" data-sel="${esc(id)}"><span class="dot" aria-hidden="true"></span><span class="pk-w">${esc(navWords(q))}</span><span class="pk-s">${esc(w)}</span></a></li>`; }).join('');
  const before = rec.by && (rec.withdrawn || so.stale)
    ? `<p class="stale">The sign-off by ${esc(rec.by)} on ${esc(fmtDate(rec.at))} no longer counts: ${rec.withdrawn && rec.withdrawn.why === 'withdrawn' ? 'it was taken back' : 'the case changed after it'}.</p>` : '';
  let act;
  if (signed) act = `<div class="hint">Signed off by <b>${esc(rec.by)}</b> on ${esc(fmtDate(rec.at))}. The accepted quotes are the packet.</div>
      <div class="act"><button class="primary" id="copyBtn">Copy packet</button><button id="unsignBtn">Take back the sign-off</button><span class="hint" id="copyMsg"></span></div>`;
  else if (so.can_sign) act = `${gapStrikes(d).length ? `<label class="gap-check"><input type="checkbox" id="gapCheck"> I've checked the removed requirements</label>` : ''}<div class="act"><input type="text" id="signName" placeholder="Your name" value="${esc(myName())}" maxlength="60"><button class="primary" id="signBtn">Sign off</button><button id="copyBtn">Preview the packet</button><span class="hint" id="copyMsg"></span></div>`;
  else act = `<div class="act"><button id="signBtn" aria-disabled="true" disabled>Sign off</button><button id="copyBtn">Preview the packet</button>${(p.asks || []).length ? `<button id="msgBtn">Message ${esc(name)}</button>` : ''}<span class="hint" id="copyMsg">${esc(signReason(d))}</span></div>`;
  setSide(`<div class="next pk-panel ${signed || so.can_sign ? 'ready' : ''}">${doneNote()}${sideHead('The packet', false)}
    <h2 id="pkHead" tabindex="-1" title="${esc(progWords(p, false))}">${esc(title)}</h2>
    ${gapStrikes(d).length ? `<div class="gap-strikes"><b>Removed while not in the case (${gapStrikes(d).length})</b>${gapStrikes(d).map(k => `<p><a href="#" data-sel="${esc(k.criterion)}">“${esc(trimDot(k.words))}”</a>: ${esc(whyText(k))} <span class="hint">${esc([k.by, fmtDate(k.at)].filter(Boolean).join(' · '))}</span></p>`).join('')}</div>` : ''}
    <ol class="pk-list">${list}</ol>${before}${act}<div class="draft" id="draft"></div>${changesHtml(so)}${auditHtml(d)}</div>`);
  syncHash();
  $('#copyBtn').onclick = async () => {
    // the case as it is now, not as this tab drew it: final only if it is signed off now
    let fresh;
    try { fresh = await api('/review/' + encodeURIComponent(d.chart_id)); }
    catch (e) { return failed(e, m => { $('#copyMsg').textContent = m; }); }
    if (docKey(fresh) !== docKey(d)) {
      showChanged(fresh);
      if (fresh.signoff && fresh.signoff.state === 'signed' && $('#copyMsg')) {
        try { await navigator.clipboard.writeText(packetText(fresh)); $('#copyMsg').textContent = 'Copied the packet as it is now.'; } catch {}
      } else if ($('#copyMsg')) $('#copyMsg').textContent = 'Nothing was copied: look at the case again first.';
      return;
    }
    const final = fresh.signoff && fresh.signoff.state === 'signed';
    const text = final ? packetText(fresh) : 'DRAFT — not signed off; do not send.\n' + packetText(fresh);
    $('#draft').textContent = text; $('#draft').classList.add('show');
    if (!final) { $('#copyMsg').textContent = (c.packet_accepted||[]).length ? 'A draft of the accepted items: sign off first to send it.' : 'Nothing accepted yet: accept requirements to build the packet.'; return; }
    try { await navigator.clipboard.writeText(text); $('#copyMsg').textContent = 'Copied.'; } catch { $('#copyMsg').textContent = 'Shown below; select and copy.'; }
  };
  const ab = $('#auditBtn');
  if (ab) ab.onclick = async () => {
    const text = auditText(d);
    $('#auditDraft').textContent = text; $('#auditDraft').classList.add('show');
    try { await navigator.clipboard.writeText(text); $('#auditMsg').textContent = 'Copied.'; } catch { $('#auditMsg').textContent = 'Shown below; select and copy.'; }
  };
  const mb = $('#msgBtn');
  if (mb) mb.onclick = async () => {
    const text = c.message || '';
    $('#draft').textContent = text || 'Nothing is in the ask yet: open a requirement that is not in the case and choose “Add to the ask”.';
    $('#draft').classList.add('show');
    if (text) { try { await navigator.clipboard.writeText(text); $('#copyMsg').textContent = 'Copied.'; } catch { $('#copyMsg').textContent = 'Shown below; select and copy.'; } }
  };
  const sb = $('#signBtn');
  if (sb && so.can_sign) sb.onclick = async () => {
    const by = ($('#signName').value || '').trim() || myName();
    if (!by) { $('#copyMsg').innerHTML = '<span class="err">Type your name to sign off.</span>'; $('#signName').focus(); return; }
    const gc = $('#gapCheck');
    if (gc && !gc.checked) { $('#copyMsg').innerHTML = `<span class="err">Read the removed requirements above, then tick “I've checked the removed requirements”.</span>`; gc.focus(); return; }
    keepName(by); sb.disabled = true; $('#copyMsg').textContent = 'Signing off…';
    try { const nd = await post('/review/' + encodeURIComponent(d.chart_id) + '/signoff', { by, version: d.version || null, gaps_checked: !!(gc && gc.checked) }); redraw(nd); }
    catch(e){ sb.disabled = false; failed(e, m => { $('#copyMsg').innerHTML = `<span class="err">${esc(m)}</span>`; }); }
  };
  const ub = $('#unsignBtn');
  if (ub) ub.onclick = async () => {
    ub.disabled = true;
    try { redraw(await api('/review/' + encodeURIComponent(d.chart_id) + '/signoff?by=' + encodeURIComponent(myName()), {method:'DELETE'})); }
    catch(e){ ub.disabled = false; failed(e, m => { $('#copyMsg').innerHTML = `<span class="err">${esc(m)}</span>`; }); }
  };
  marksRefresh();
}
// the internal audit note: what was removed (and whether the chart documented it), what was added, who signed off;
// for the practice's records, never part of the packet sent to the payer
function auditHtml(d){
  if (!auditText(d)) return '';
  return `<div class="audit"><div class="audit-h"><b>Audit note</b> <span class="hint">internal; not sent to the payer</span></div>
    <div class="act"><button id="auditBtn">Copy audit note</button><span class="hint" id="auditMsg"></span></div><div class="draft" id="auditDraft"></div></div>`;
}
// said once, at the top of the panel the page moves on to: what the last accept did, with Undo
function doneNote(){
  const j = justDone;              // cleared by redraw once the panel it belongs to is drawn
  if (!j) return '';
  return `<div class="sp-done" role="status"><b>${j.ask ? '→' : '✓'}</b><span>${j.ask ? 'Added to the ask' : j.outside ? 'Confirmed outside the case' : 'Accepted'}: “${esc(short(j.words, 48))}”</span><a href="#" class="unaccept" data-aid="${esc(j.aid)}" data-crit="${esc(j.crit)}">Undo</a></div>`;
}
// a requirement: its ruling, the chart's quotes, Accept
function showRequirement(id){
  id = cleadOf(id);
  const r0 = reqById[id]; if (!r0) return showPacket();
  panelMode = 'req';
  const i = stepOrder().indexOf(id), us = unitsOf(id);
  const where0 = r0.source ? '' : pagesWord(r0.refs || []);   // with a source, the page is said on its line
  let h = doneNote() + sideHead(`${i >= 0 ? `Requirement ${i + 1} of ${stepOrder().length}` : 'Requirement'}${where0 ? ' · ' + esc(where0) : ''}`, true);
  // a run of requirements on adjoining words is stacked, each with its own buttons; identical words are one card
  const card = (id, first) => {
  const r = reqById[id], ids = idsOf(id), grp = ids.length > 1, b = r.block ? blocks[r.block] : null;
  const ti = b ? (b.items||[]).find(x => x.criterion === id) : null;
  const [g, cls, say] = r.accepted && r.mark !== 'struck' ? ['✓', 'm-acc', r.mark === 'confirm' ? 'Confirmed outside the case' : isExcl(r) ? "Accepted: doesn't apply to this patient" : 'Accepted'] : ruling(r);  // in the ask keeps its own mark
  const seenEv = new Set(), evs = ids.flatMap(m => QUIET.includes(reqById[m].mark) ? [] : (reqById[m].evidence || []).map(e => ({ e, m }))).filter(x => { const k = x.e.span + x.e.side + x.m; return seenEv.has(k) ? false : seenEv.add(k); });
  const src = r.source;
  const bid = (first ? 'id="acceptBtn" ' : '') + `data-crit="${esc(id)}"`;
  const aids = ids.map(m => (reqById[m].accepted || reqById[m].in_ask || {}).id).filter(Boolean).join(' ');
  let h = '';
  h += `<blockquote class="sp-words">“${esc(trimDot(r.words))}”</blockquote>`;
  // the citation: the policy's own heading for the part and the page; a link to that line (a warm dot when it is
  // outside the confirmed indication, no commentary)
  const cited = src && src.pathway && pwLabels[src.pathway] ? `Cited: ${pwLabels[src.pathway]}${src.page != null ? `, p. ${src.page}` : ''}` : src && src.say;
  if (src) h += `<div class="sp-from${src.other ? ' other' : ''}">${src.line ? `<a href="#" class="sp-cite" data-line="${esc(src.line)}">${esc(short(cited, 110))}</a>` : esc(short(cited, 110))}</div>`;
  h += `${isExcl(r) ? '<div class="sp-kind">Must not apply</div>' : ''}<div class="sp-ruling ${cls}"><b>${g}</b>${esc(say)}</div>`;
  if (grp) h += `<div class="sp-also">${ids.length} requirements quote these same words. They are one item: what you decide applies to all of them.</div>`;
  if (r.route) h += `<div class="sp-route">Or: another route; needs its own evidence</div>`;
  for (const t of [...new Set((r.reasons || []).map(reqReason))]) h += `<div class="sp-reason">${esc(t)}</div>`;
  if (r.mark === 'struck') h += `<div class="ev it struck" data-crit="${esc(id)}">${struckHtml(r)}</div>`;
  else {
    h += `<div class="ev it" data-crit="${esc(id)}">`;
    h += evs.slice(0, 1).map(x => evqHtml(x.e, x.m)).join('');
    if (evs.length > 1) h += `<a class="evmore" href="#" data-n="${evs.length - 1}" aria-expanded="false">+ ${evs.length - 1} more</a><div class="evrest">${evs.slice(1).map(x => evqHtml(x.e, x.m)).join('')}</div>`;
    // one ruling line and, at most, one helpful sentence: for something not in the chart, what to ask for
    const gap = r.mark === 'missing' || r.mark === 'unclear';
    if (!QUIET.includes(r.mark) && !evs.length)
      h += gap ? `<p class="sp-help">${esc(isExcl(r) ? `Ask ${surgeonName((doc.case || {}).surgeon)} to confirm this does not apply.` : `Ask ${surgeonName((doc.case || {}).surgeon)} for a note that shows this.`)}</p>`
        : `<div class="nocite">No case lines were cited for this.</div>`;
    if (ti && ti.note && !gap && evs.length) h += `<span class="note">${esc(ti.note)}</span>`;
    if (r.mark === 'confirm' && r.why_outside) h += `<p class="sp-help">${esc(r.why_outside)}</p>`;
    h += `</div>`;
    if (r.counted && r.mark === 'confirm') {
      // no chart can show it: a person confirms it outside the chart (who and when, like an accept; it counts to sign off)
      const rec = r.accepted;
      h += rec ? `<div class="sp-acc">By <b>${esc(rec.by || 'a person')}</b>${rec.at ? ' on ' + esc(fmtDate(rec.at)) : ''}. <a href="#" class="unaccept" data-aid="${esc(aids)}">Undo</a></div>`
        : `<div class="sp-act"><button class="primary acceptBtn" ${bid}>Confirmed outside the case <kbd>${MOD}↵</kbd></button></div>`;
    } else if (r.counted) {
      // Accept means proof: only a documented requirement is accepted; one the chart does not show yet goes in the ask
      const rec = r.accepted || r.in_ask, k = `<kbd>${MOD}↵</kbd>`;
      h += rec ? `<div class="sp-acc">${r.accepted ? 'Accepted' : 'In the ask, added'} by <b>${esc(rec.by || 'a person')}</b>${rec.at ? ' on ' + esc(fmtDate(rec.at)) : ''}. <a href="#" class="unaccept" data-aid="${esc(aids)}">Undo</a></div>`
        : grp ? `<div class="sp-act"><button class="primary acceptBtn" ${bid}>Accept ${k}</button><button class="acceptBtn" data-crit="${esc(id)}" data-ask="1">Add to the ask</button><span class="hint">You decide: it applies to all ${ids.length}.</span></div>`
        : r.proof ? `<div class="sp-act"><button class="primary acceptBtn" ${bid}>Accept ${k}</button><span class="hint">${isExcl(r) ? "It goes into the packet: the case shows this doesn't apply." : 'It goes into the packet with its quote.'}</span></div>`
        : `<div class="sp-act"><button class="primary acceptBtn" ${bid}>Add to the ask ${k}</button><span class="hint">${isExcl(r)
            ? `${esc(surgeonName((doc.case || {}).surgeon))} is asked to confirm this does not apply to the patient.`
            : `It goes into the message to ${esc(surgeonName((doc.case || {}).surgeon))}; the case can be signed off once the case shows it.`}</span></div>`;
    } else h += `<div class="hint sp-note">Another option in the guideline is documented, so this one is not needed for the case.</div>`;
    h += `<div class="ev sp-more" data-crit="${esc(id)}">${changeCtl(r)}<a href="#" class="report" data-report="${esc(id)}">Report on this</a></div>`;
  }
  return h;
  };
  us.forEach((u, n) => { h += (us.length > 1 ? '<div class="sp-stack">' : '') + card(u, !n) + (us.length > 1 ? '</div>' : ''); });
  h += `<div class="sp-nav"><a href="#" class="sp-prev"><kbd>↑</kbd> Previous</a><a href="#" class="sp-next">Next <kbd>↓</kbd></a></div>`;
  setSide(`<div class="sp-req">${h}</div>`);
  renderFeedback();
}
function sideClick(e, d){
  const id = encodeURIComponent(d.chart_id);
  if (e.target.closest('.sp-x')) { e.preventDefault(); closeSide(); return; }
  if (e.target.closest('.sb-toggle')) { setSheet(!sheetOpen); return; }
  if (e.target.closest('.sb-prev')) { step(-1); return; }
  if (e.target.closest('.sb-next')) { step(1); return; }
  if (e.target.closest('.sp-prev')) { e.preventDefault(); step(-1); return; }
  if (e.target.closest('.sp-next')) { e.preventDefault(); step(1); return; }
  const sel = e.target.closest('[data-sel]'); if (sel) { e.preventDefault(); selectRequirement(sel.dataset.sel); return; }
  const gt = e.target.closest('[data-goto]'); if (gt) { e.preventDefault(); const ln = lineEl(gt.dataset.goto); if (ln) { scrollToEl(ln); setProbe([gt.dataset.goto], 'key'); } return; }
  const ab = e.target.closest('.acceptBtn'); if (ab) { acceptSelected(ab.dataset.crit, ab.dataset.ask); return; }
  const un = e.target.closest('.unaccept');
  if (un) { e.preventDefault(); un.textContent = 'Undoing…';
    const back = un.dataset.crit || (panelMode === 'req' ? selectedCrit : null);
    (async () => { let nd; for (const a of un.dataset.aid.split(' ').filter(Boolean)) nd = await api('/review/' + id + '/accepts/' + encodeURIComponent(a) + '?by=' + encodeURIComponent(myName()), {method:'DELETE'});   // identical requirements: all together
      redraw(nd, back, { advance: true }); })().catch(err => { un.textContent = 'Undo'; failed(err); }); return; }
  const rp = e.target.closest('.report');
  if (rp) { e.preventDefault(); const r = reqById[rp.dataset.report]; if (r && r.refs.length) { fbSel = null; pickLine(r.refs[0], false); pickLine(r.refs[r.refs.length - 1], true); } return; }
  if (e.target.closest('.fb-chip')) return;
  if (strikeClick(e, d)) return;
  const more = e.target.closest('.evmore');
  if (more) { e.preventDefault(); toggleMore(more.closest('.it'), more.getAttribute('aria-expanded') !== 'true'); return; }
  const q = e.target.closest('.evq[data-crit]');
  if (q) { pickEvidence(q); return; }
  if (e.target.closest('.ask-card')) cardClick(e, lastAsk);
}
function closeSide(){ if (probe || $('.ask-card')) closeCard(); else if (panelMode === 'notes' && selectedCrit) showRequirement(selectedCrit); else showPacket(); }
let accepting = false, justDone = null;          // one accept in flight; what the last one did, said once in the next panel
async function acceptSelected(crit, ask){
  hintDone();
  crit = typeof crit === 'string' && crit ? crit : selectedCrit;
  const r = crit && reqById[crit], ids = idsOf(crit), grp = ids.length > 1;
  if (accepting || !r || !r.counted || r.accepted || r.in_ask || r.mark === 'struck' || !doc) return;
  const redo = () => acceptSelected(crit, ask);
  const label = r.mark === 'confirm' ? 'Confirmed outside the case' : (grp ? !ask : r.proof) ? 'Accept' : 'Add to the ask';
  const why = r.mark === 'confirm' ? 'Type your name to confirm this.' : label === 'Accept' ? 'Type your name to accept this requirement.' : 'Type your name to add this to the ask.';
  if (needName(why, redo)) return;
  const bs = $$('.acceptBtn').filter(x => x.dataset.crit === crit), b = bs[0] || $('#acceptBtn');
  bs.forEach(x => { x.disabled = true; });
  if (b && !grp) b.textContent = r.mark === 'confirm' ? 'Confirming…' : r.proof ? 'Accepting…' : 'Adding…';
  const keep = crit; accepting = true;
  try {
    const nd = await post('/review/' + encodeURIComponent(doc.chart_id) + '/accepts', grp ? { criterion: keep, together: ids.slice(1), ask: !!ask, by: myName() || null } : { criterion: keep, by: myName() || null });
    // then on to the next requirement still open (this run first, then after it, else from the top); none left: the packet
    const open = q => q && q.counted && !q.accepted && !q.in_ask && q.mark !== 'struck';
    const reqs = Object.fromEntries(((nd.case || {}).requirements || []).map(q => [q.criterion, q]));
    const all = stepOrder(), cl = cleadOf(keep), i = all.indexOf(cl), order = [cl].concat(all.slice(i + 1), all.slice(0, i));
    const next = order.find(id => ((reqs[id] || {}).near || [id]).some(u => open(reqs[u]))) || null;
    const k = reqs[keep] || {}, recs = ids.map(m => reqs[m] && (reqs[m].accepted || reqs[m].in_ask)).filter(Boolean);
    justDone = recs.length ? { crit: keep, aid: recs.map(x => x.id).join(' '), ask: !k.accepted, outside: k.mark === 'confirm', words: k.words } : null;
    redraw(nd, next || '', { advance: true });
  } catch (e) {
    bs.forEach(x => { x.disabled = false; });
    if (b && !grp) b.innerHTML = esc(label) + ` <kbd>${MOD}↵</kbd>`;
    // the server needs a name (it was cleared in another tab): ask for it, then accept
    if (e.status === 400 && !myName() && needName(why, redo)) return;
    // already accepted elsewhere (another tab, another person): the case as it is now, with one calm line
    failed(e, m => { const h = b && b.parentElement && b.parentElement.querySelector('.hint'); if (h) h.innerHTML = `<span class="err">${esc(m)}</span>`; else calm(m); });
  }
  finally { accepting = false; }
}

// a new document after an accept, a strike, an addition or a sign-off: draw it where the page is and keep the focus
// where the person was working (the requirement's row in the navigator; the packet's heading when none is open).
// focus '' means "the packet"; opts.advance glides to the requirement when it is out of view.
function redraw(nd, focus, opts){
  opts = opts || {};
  const y = window.scrollY, was = focus != null ? focus : (panelMode === 'req' ? selectedCrit : null);
  const inSide = document.activeElement && document.activeElement.closest && document.activeElement.closest('#side, .rq-nav');
  doc = nd; hideFb();
  if (nd.nofit && nd.state === 'done') renderNoFit(nd);
  else if (nd.case) { renderCase(nd); if (was && reqById[was]) selectRequirement(was, true); }
  else load(nd.chart_id, true);
  window.scrollTo({ top: y, behavior: 'instant' });
  if (nd.case && (inSide || opts.advance)) {
    const nv = was && (curView() === 'tree' ? placeOf(was) : document.querySelector(`.nv[data-crit="${CSS.escape(was)}"]`));
    // nothing left open: the packet's heading, never Sign off itself (a stray Enter after the last accept must not sign)
    const t = nv && nv.getClientRects().length ? nv : was ? $('#acceptBtn') || $('#side .sp-x') : $('#pkHead');
    if (t) t.focus({ preventScroll: true });
  }
  justDone = null;
  // on a phone the note is a small toast over the page (it does not push the panel down); it goes after a while
  const toast = narrow() && $('#side .sp-done');
  if (toast) setTimeout(() => { if (toast.isConnected) toast.classList.add('gone'); }, 6000);
  if (opts.advance && !was && nd.case) setSheet(true);   // nothing left open: show the packet, Sign off in reach
  if (opts.advance && was) scrollToEl(placeOf(was));
  loadOrders().catch(() => {});
}
// "Not needed for this case" opens the form in the panel; "Remove for this case" needs a reason; "Put it back" and
// "Take it off" undo. True when the click was one of these.
function strikeClick(e, d){
  const id = encodeURIComponent(d.chart_id);
  const open = e.target.closest('.strike-btn');
  if (open) {
    e.preventDefault(); e.stopPropagation();
    $$('.strike-form').forEach(f => f.remove());
    open.insertAdjacentHTML('afterend', strikeForm(open.dataset.strike));
    const f = open.nextElementSibling; strikeHint(f);
    (f.querySelector('.chip[tabindex="0"]') || f).focus({ preventScroll: true });
    // inside the sheet on a phone (or the panel at a desk) the form is brought into view, its buttons included
    requestAnimationFrame(() => f.scrollIntoView({ block: 'nearest', behavior: reduceMotion() ? 'instant' : 'smooth' }));
    return true;
  }
  const form = e.target.closest('.strike-form');
  if (form) {
    e.stopPropagation();
    if (e.target.closest('.strike-cancel')) { form.remove(); return true; }
    const chip = e.target.closest('.chip');
    if (chip) { pickReason(form, chip.dataset.code); return true; }
    const go = e.target.closest('.strike-go');
    if (go) {
      const reason = (form.querySelector('.strike-why').value || '').trim(), code = form.dataset.code || '';
      const msg = form.querySelector('.strike-msg'), say = (t, el) => { msg.innerHTML = `<span class="err">${esc(t)}</span>`; (el || form.querySelector('.strike-why')).focus(); };
      if (!code) { say('Pick a reason first.', form.querySelector('.chip')); return true; }
      if (code === 'other' && !reason) { say('Say what the reason is.'); return true; }
      const gap = groupGap(form.dataset.crit);
      if (gap && !realSentence(reason)) { say('This requirement is not in the case: say in a sentence (three words or more) why it is not needed for this case.'); return true; }
      if (needName()) return true;
      go.disabled = true; msg.textContent = 'Removing…';
      (async () => { let nd; for (const m of idsOf(form.dataset.crit)) nd = await post('/review/' + id + '/strikes', { criterion: m, code, reason, by: myName() || null }); return nd; })()   // identical requirements: all together
        .then(nd => { delete drafts['strike:' + form.dataset.crit]; delete drafts['strikecode:' + form.dataset.crit]; redraw(nd, form.dataset.crit); }).catch(err => { go.disabled = false; msg.textContent = ''; failed(err, m => { msg.innerHTML = `<span class="err">${esc(m)}</span>`; }); });
    }
    return true;
  }
  const ua = e.target.closest('.unadd');
  if (ua) {
    e.preventDefault(); e.stopPropagation();
    ua.textContent = 'Taking it off…';
    api('/review/' + id + '/additions/' + encodeURIComponent(ua.dataset.aid) + '?by=' + encodeURIComponent(myName()), {method:'DELETE'})
      .then(nd => redraw(nd, null)).catch(err => { ua.textContent = 'Take it off'; failed(err); });
    return true;
  }
  const un = e.target.closest('.unstrike');
  if (un) {
    e.preventDefault(); e.stopPropagation();
    const crit = (un.closest('[data-crit]') || {}).dataset ? un.closest('[data-crit]').dataset.crit : null;
    un.textContent = 'Putting it back…';
    (async () => { let nd; for (const sid of un.dataset.sid.split(' ')) nd = await api('/review/' + id + '/strikes/' + encodeURIComponent(sid) + '?by=' + encodeURIComponent(myName()), {method:'DELETE'}); return nd; })()
      .then(nd => redraw(nd, crit)).catch(err => { un.textContent = 'Put it back'; failed(err); });
    return true;
  }
  return false;
}

// ------------------------------------------------------------------ selecting a requirement: its words in the guideline, its evidence beside them
// bring an element to a comfortable reading place, about a third down the part of the window the text shows (above
// the bottom sheet on a phone). Nothing moves when it is already comfortably in view, so stepping through
// requirements that sit close together does not make the page jump; when it must move it glides (instant with
// reduced motion, or when asked: a click that follows must land where the page already is).
const reduceMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
function viewBottom(){ const s = $('#side'); if (s && getComputedStyle(s).position === 'fixed') { const t = s.getBoundingClientRect().top; if (t > 120) return t; } return window.innerHeight; }
function scrollToEl(el, how, at){
  if (!el) return;
  const r = el.getBoundingClientRect(), vb = viewBottom();
  if (!/^force/.test(how || '') && r.top >= Math.max(56, vb * 0.12) && r.bottom <= vb * (at ? 0.96 : 0.78)) return;
  const top = r.top + window.scrollY - Math.max(at ? 24 : 72, vb * (at || 1 / 3));
  window.scrollTo({ top: Math.max(0, top), behavior: /instant/.test(how || '') || reduceMotion() ? 'instant' : 'smooth' });
}
// keep the open requirement visible in the navigator's own scroll, without ever scrolling the page
function revealInNav(nv){
  const box = nv && nv.closest('.rq-nav'); if (!box || box.scrollHeight <= box.clientHeight) return;
  const b = box.getBoundingClientRect(), r = nv.getBoundingClientRect(), pad = 24;
  if (r.top < b.top + pad) box.scrollTop += r.top - b.top - pad;
  else if (r.bottom > b.bottom - pad) box.scrollTop += r.bottom - b.bottom + pad;
}
// a citation's link: the guideline view at that exact line (the rest of the policy unfolded when it lies there),
// scrolled into view and marked briefly
function goToLine(id){
  if (!id) return;
  if (curView() === 'tree') setView('guideline');
  const ln = document.querySelector(`.gl .ln[data-id="${CSS.escape(id)}"]`); if (!ln) return;
  const rf = ln.closest('details:not([open])'); if (rf) rf.open = true;      // a line inside a closed gap opens it first
  scrollToEl(ln, 'force');
  ln.classList.remove('cited'); void ln.offsetWidth; ln.classList.add('cited');
  setTimeout(() => ln.classList.remove('cited'), 1600);
  marksRefresh();
}
// a gap opened or folded: remember it, and the highlighter re-measures
document.addEventListener('toggle', e => { const d = e.target; if (!d.matches || !d.matches('details.rest-fold')) return; d.open ? openGaps.add(d.dataset.gap) : openGaps.delete(d.dataset.gap); marksRefresh(); }, true);
document.addEventListener('click', e => {
  const a = e.target.closest && e.target.closest('a.gap-less, a.gl-all'); if (!a) return;
  e.preventDefault();
  if (a.matches('.gap-less')) { const d = a.closest('details'); d.open = false; d.scrollIntoView({ block: 'nearest' }); return; }
  const on = !wholeOn(); try { localStorage.setItem('review.whole', on ? '1' : ''); } catch {}
  a.textContent = on ? 'Show requirements only' : 'Show whole guideline';
  $$('#glDoc details.rest-fold').forEach(d => { d.open = on; });
});
document.addEventListener('click', e => { const a = e.target.closest && e.target.closest('a.sp-cite'); if (!a) return; e.preventDefault(); goToLine(a.dataset.line); });
function selectRequirement(id, noScroll){
  if (id) { hintDone(); id = cleadOf(id); }
  if (probe || $('.ask-card')) closeCard(true);
  selectedCrit = id || null;
  $$('.sel').forEach(x => x.classList.remove('sel'));
  $$('.nv[aria-current], .tl[aria-current]').forEach(x => x.removeAttribute('aria-current'));
  if (!id) return showPacket();
  const marks = $$(`mark.q[data-crit="${CSS.escape(id)}"]`);
  marks.forEach(m => { m.classList.add('sel'); const ln = m.closest('.ln'); if (ln) ln.classList.add('sel'); });
  const r = reqById[id] || {};
  if (!marks.length) for (const ref of (r.refs||[])) { const ln = document.querySelector(`.gl .ln[data-id="${CSS.escape(ref)}"]`); if (ln) ln.classList.add('sel'); }
  const nv = document.querySelector(`.nv[data-crit="${CSS.escape(id)}"]`);
  if (nv) { nv.setAttribute('aria-current', 'true'); revealInNav(nv); }
  const tl = document.querySelector(`#treeDoc .tl[data-crit="${CSS.escape(id)}"]`); if (tl) tl.setAttribute('aria-current', 'true');
  showRequirement(id);
  // a tap on a phone opens the sheet over the lower half: bring the words above it if they are now underneath
  if (!noScroll || narrow()) scrollToEl(placeOf(id));
  syncHash();
  marksRefresh();
}
function focusSelected(){ const nv = selectedCrit && (curView() === 'tree' ? placeOf(selectedCrit) : document.querySelector(`.nv[data-crit="${CSS.escape(selectedCrit)}"]`)); if (nv && nv.getClientRects().length) nv.focus({ preventScroll: true }); }
function step(n){
  const tree = curView() === 'tree' && treeOrder.length, order = stepOrder();
  if (!order.length) return;
  const i = order.indexOf(selectedCrit);
  const j = i < 0 ? (n > 0 ? 0 : order.length - 1) : Math.max(0, Math.min(order.length - 1, i + n));
  if (j === i && panelMode === 'req') return;          // already at the first / last: nothing to do
  selectRequirement(order[j]);
  const nv = tree ? document.querySelector(`#treeDoc .tl[data-crit="${CSS.escape(order[j])}"]`) : document.querySelector(`.nv[data-crit="${CSS.escape(order[j])}"]`);
  if (nv && nv.getClientRects().length) nv.focus({ preventScroll: true });
  else { const b = $(n > 0 ? '#side .sb-next' : '#side .sb-prev'); (b && !b.disabled ? b : $(n > 0 ? '#side .sb-prev' : '#side .sb-next') || b)?.focus({ preventScroll: true }); }
}

// ------------------------------------------------------------------ feedback
function pickLine(id, extend){
  $$('.fb-sel').forEach(x => x.classList.remove('fb-sel'));
  const anchor = (fbSel && fbSel.side === 'guideline' && fbSel.anchor) || (extend ? anchorLine : null);
  if (extend && anchor) {
    const order = visibleLines().map(el => el.dataset.id);
    const a = order.indexOf(anchor), b = order.indexOf(id);
    fbSel = a >= 0 && b >= 0 ? { side: 'guideline', anchor, ids: order.slice(Math.min(a, b), Math.max(a, b) + 1) } : { side: 'guideline', anchor: id, ids: [id] };
  } else fbSel = { side: 'guideline', anchor: id, ids: [id] };
  if (fbKind && !GL_KINDS.includes(fbKind)) fbKind = null;
  for (const x of fbSel.ids) { const ln = document.querySelector(`.gl .ln[data-id="${CSS.escape(x)}"]`); if (ln) ln.classList.add('fb-sel'); }
  renderFbBar();
}
function pickEvidence(q){
  $$('.fb-sel').forEach(x => x.classList.remove('fb-sel'));
  fbSel = { side: 'chart', crit: q.dataset.crit, span: q.dataset.span, sideWord: q.dataset.side, lines: (q.dataset.lines || '').split(' ').filter(Boolean) };
  if (fbKind && !CH_KINDS.includes(fbKind)) fbKind = null;
  q.classList.add('fb-sel');
  renderFbBar();
}
const fbKey = () => fbSel ? 'fb:' + (fbSel.side === 'guideline' ? fbSel.ids.join(' ') : fbSel.crit + ' ' + fbSel.span) : null;
function hideFb(){ fbSel = null; fbKind = null; $('#fbBar').classList.add('hidden'); $('#fbBar').innerHTML = ''; $$('.fb-sel').forEach(x => x.classList.remove('fb-sel')); }
const lineText = id => { const ln = document.querySelector(`.gl .ln[data-id="${CSS.escape(id)}"] .tx`); return ln ? ln.textContent.trim() : ''; };
// lines are named by where a person finds them, the page; never by their internal ids
const pagesWord = ids => { const ps = [...new Set((ids || []).map(i => linePage[i]).filter(x => x != null))].sort((a, b) => a - b);
  return ps.length ? (ps.length > 1 ? `pages ${ps[0]}–${ps[ps.length - 1]}` : `page ${ps[0]}`) : ''; };
const rangeLabel = ids => !(ids || []).length ? '' : `${ids.length > 1 ? ids.length + ' lines' : 'one line'}${pagesWord(ids) ? ' on ' + pagesWord(ids) : ''}`;
function reqsFor(ids){ const s = new Set(); for (const id of ids) for (const c of (lineCrits[id]||[])) s.add(c); return [...s]; }
function renderFbBar(){
  const bar = $('#fbBar');
  if (!fbSel || !doc || doc.state !== 'done') { bar.classList.add('hidden'); bar.innerHTML = ''; return; }
  const gl = fbSel.side === 'guideline', kinds = gl ? GL_KINDS : CH_KINDS;
  const reqs = gl ? reqsFor(fbSel.ids) : [fbSel.crit];
  let proposal = '';
  if (gl && fbKind === 'edit') {
    const one = reqs.length === 1 && reqById[reqs[0]] && fbSel.ids.every(x => (reqById[reqs[0]].refs||[]).includes(x));
    proposal = one ? (reqById[reqs[0]].words || '') : fbSel.ids.map(lineText).join(' ');
  }
  const dr = drafts[fbKey()] || {};
  const kept = { text: ($('#fbText')||{}).value || dr.fbText || '', proposal: ($('#fbProposal')||{}).value != null ? $('#fbProposal').value : dr.fbProposal };
  const head = gl ? `Report on the guideline, ${esc(rangeLabel(fbSel.ids))}` : 'Report on this evidence';
  const hint = gl ? `Shift-click another line to widen the range.${reqs.length ? ` Touches ${reqs.length} requirement${reqs.length>1?'s':''}.` : ''}`
                  : `${UNSURE.includes((reqById[fbSel.crit] || {}).mark) ? 'Quoted as related to' : fbSel.sideWord === 'for' ? 'Quoted as supporting' : 'Quoted as contradicting'} “${esc(trimDot((reqById[fbSel.crit]||{}).words || fbSel.crit))}”.`;
  bar.innerHTML = `<div class="fb-head"><b>${head}</b><span class="hint">${hint}</span><span class="x" id="fbClose">Close</span></div>
    <div class="kinds">${kinds.map(k => `<button type="button" data-kind="${k}" aria-pressed="${fbKind === k}">${esc(KINDS[k])}</button>`).join('')}</div>
    ${fbKind === 'edit' ? `<label class="lbl" for="fbProposal">Proposed wording</label><textarea id="fbProposal" placeholder="How the requirement should read">${esc(kept.proposal != null && kept.proposal !== '' ? kept.proposal : proposal)}</textarea>` : ''}
    <textarea id="fbText" placeholder="${gl ? 'Say why, in a sentence or two (optional)' : 'Say what the right evidence is, or what this is really about (optional)'}">${esc(kept.text)}</textarea>
    <div class="fb-act"><button class="primary" id="fbSend" ${fbKind ? '' : 'disabled'}>Send <kbd>${MOD}↵</kbd></button><span class="hint" id="fbMsg">${fbKind ? '' : 'Pick what this is about.'}</span></div>`;
  bar.classList.remove('hidden');
  $('#fbClose').onclick = hideFb;
  bar.querySelectorAll('[data-kind]').forEach(b => b.onclick = () => { fbKind = b.dataset.kind; renderFbBar(); });
  $('#fbSend').onclick = sendFeedback;
}
async function sendFeedback(){
  if (!fbSel || !fbKind || !doc) return;
  const gl = fbSel.side === 'guideline';
  const body = gl
    ? { kind: fbKind, side: 'guideline', text: ($('#fbText').value || '').trim(), spans: fbSel.ids, requirements: reqsFor(fbSel.ids), by: myName() || null }
    : { kind: fbKind, side: 'chart', text: ($('#fbText').value || '').trim(), spans: fbSel.lines, requirements: [fbSel.crit].filter(Boolean), by: myName() || null };
  if (fbKind === 'edit') body.proposal = ($('#fbProposal')||{}).value || '';
  const b = $('#fbSend'); b.disabled = true; $('#fbMsg').textContent = 'Sending…';
  try {
    const item = await post('/review/' + encodeURIComponent(doc.chart_id) + '/feedback', body);
    doc.feedback = [...(doc.feedback||[]), item];
    try { doc.feedback = await api('/review/' + encodeURIComponent(doc.chart_id) + '/feedback'); } catch {}
    delete drafts[fbKey()]; hideFb(); renderFeedback();
  } catch(e){ b.disabled = false; if (e.status === 404 || e.status === 409) hideFb(); failed(e, m => { $('#fbMsg').innerHTML = `<span class="err">${esc(m)}</span>`; }); }
}
async function removeFeedback(fid){
  try {
    await api('/review/' + encodeURIComponent(doc.chart_id) + '/feedback/' + encodeURIComponent(fid), {method:'DELETE'});
    doc.feedback = (doc.feedback||[]).filter(f => f.id !== fid);
    try { doc.feedback = await api('/review/' + encodeURIComponent(doc.chart_id) + '/feedback'); } catch {}
    renderFeedback();
  } catch(e){ failed(e); }
}
function toggleMore(it, open){
  if (!it) return;
  const a = it.querySelector('.evmore'); if (!a) return;
  it.classList.toggle('open', open);
  a.setAttribute('aria-expanded', String(open));
  a.textContent = open ? '– less' : `+ ${a.dataset.n} more`;
}
// where a feedback item sits: under its last guideline line (after the whole requirement), or inside the evidence
// quote in the side panel whose lines it names (only while that requirement is open)
function anchorFor(f){
  const ids = f.spans || [];
  if (f.side === 'chart') {
    const mine = new Set(ids), reqs = new Set(f.requirements || []);
    const qs = $$('#side .evq[data-lines]').filter(q => q.dataset.lines.split(' ').some(x => mine.has(x)));
    const q = qs.find(x => reqs.has(x.dataset.crit)) || null;
    if (q && q.closest('.evrest')) toggleMore(q.closest('.it'), true);
    return q;
  }
  const ln = ids[0] ? document.querySelector(`.gl .ln[data-id="${CSS.escape(ids[0])}"]`) : null;
  if (!ln || !ln.dataset.block) return ln;
  const same = $$(`.gl .ln[data-block="${CSS.escape(ln.dataset.block)}"]`);
  return same[same.length - 1] || ln;
}
// the notes on one paragraph, in the side panel (each can be removed there)
function showNotes(fids){
  panelMode = 'notes';
  const items = ((doc && doc.feedback) || []).filter(f => fids.includes(f.id));
  setSide(`<div class="sp-notes">${sideHead(`${items.length} note${items.length > 1 ? 's' : ''} on these lines`, true)}` +
    items.map(f => `<div class="fb-chip in-notes" data-fid="${esc(f.id)}"><span class="k">${esc(KINDS[f.kind] || f.kind)}</span><span class="t">${esc(f.proposal ? `“${f.proposal}”` : '')}${f.proposal && f.text ? ' — ' : ''}${esc(f.text || '')}<span class="hint"> · ${esc([rangeLabel(f.spans || []), f.by, fmtDate(f.at)].filter(Boolean).join(' · '))}</span></span><span class="rm">remove</span></div>`).join('') + '</div>');
  $$('#side .fb-chip .rm').forEach(x => x.onclick = async e => { e.stopPropagation(); await removeFeedback(x.closest('.fb-chip').dataset.fid);
    const left = fids.filter(id => ((doc && doc.feedback) || []).some(f => f.id === id)); if (left.length) showNotes(left); else showPacket(); });
}
function whereLabel(f){
  if (f.side === 'chart') { const r = reqById[(f.requirements||[])[0]]; return r ? `evidence for “${trimDot(r.words)}”` : `the case, ${rangeLabel(f.spans||[])}`; }
  return `the guideline, ${rangeLabel(f.spans||[])}`;
}
function renderFeedback(){
  $$('.fb-chip:not(.in-notes), .fb-notes').forEach(x => x.remove());
  const items = (doc && doc.feedback) || [];
  const list = $('#fbList'); if (!list) return;
  // where a paragraph flows as text (Marker), notes on its lines collapse to one quiet "N notes" link after it that
  // opens them in the side panel; Classic keeps one note under the lines it is about
  const flowing = document.documentElement.dataset.style !== 'classic';
  const byPara = new Map();
  for (const f of items) {
    if (f.strike || f.addition) continue;         // a removal or an addition: the requirement shows it in place
    const at = anchorFor(f);
    if (!at) continue;
    if (flowing && f.side !== 'chart' && at.parentElement && at.parentElement.classList.contains('para')) {
      const pa = at.parentElement; if (!byPara.has(pa)) byPara.set(pa, []); byPara.get(pa).push(f.id); continue;
    }
    const chip = document.createElement('div'); chip.className = 'fb-chip'; chip.dataset.fid = f.id;
    chip.innerHTML = `<span class="k">${esc(KINDS[f.kind] || f.kind)}</span><span class="t">${esc(f.proposal ? `“${f.proposal}”` : '')}${f.proposal && f.text ? ' — ' : ''}${esc(f.text || '')}${!f.proposal && !f.text ? `<span class="hint">${esc(f.side === 'chart' ? 'this quote' : rangeLabel(f.spans||[]))}</span>` : ''}</span><span class="rm">remove</span>`;
    chip.onclick = e => e.stopPropagation();
    chip.querySelector('.rm').onclick = e => { e.stopPropagation(); removeFeedback(f.id); };
    if (f.side === 'chart') at.appendChild(chip); else at.insertAdjacentElement('afterend', chip);
  }
  for (const [pa, fids] of byPara) {
    const a = document.createElement('a'); a.href = '#'; a.className = 'fb-notes'; a.dataset.fids = fids.join(' ');
    a.textContent = `${fids.length} note${fids.length > 1 ? 's' : ''}`;
    a.onclick = e => { e.preventDefault(); e.stopPropagation(); showNotes(fids); };
    pa.insertAdjacentElement('afterend', a);
  }
  const real = items.filter(f => !f.strike);          // a removal is shown as a removal, not as feedback
  list.innerHTML = `<h2>Feedback on this case</h2>` + (real.length ? real.map(f => `<div class="it" data-fid="${esc(f.id)}"><div><span class="k">${esc(KINDS[f.kind] || f.kind)}</span> · <span class="on">${esc(whereLabel(f))}${f.side !== 'chart' && (f.requirements||[]).length ? ` · ${f.requirements.length} requirement${f.requirements.length>1?'s':''}` : ''}${f.by ? ` · ${esc(f.by)}` : ''}${f.at ? ` · ${esc(fmtDate(f.at))}` : ''}</span>
      ${f.proposal ? `<div>Proposed: “${esc(f.proposal)}”</div>` : ''}${f.text ? `<div>${esc(f.text)}</div>` : ''}${f.strike ? '<div class="hint">Removed for this case; “Put it back” on the requirement undoes it.</div>' : ''}${f.addition ? '<div class="hint">Added for this case; “Take it off” on the requirement undoes it.</div>' : ''}</div>${f.strike || f.addition ? '<span></span>' : '<span class="rm">remove</span>'}</div>`).join('')
    : `<div class="none">None yet. Click a line of the guideline, or a quote from the case, to report on it.</div>`);
  list.querySelectorAll('.it .rm').forEach(x => x.onclick = () => removeFeedback(x.closest('.it').dataset.fid));
  marksRefresh();
}

// ------------------------------------------------------------------ highlight to ask: select lines, the chart's answer in the side panel
const lineEl = id => document.querySelector(`#glDoc .ln[data-id="${CSS.escape(id)}"]`);
// lines a person can see: not inside the folded "rest of the guideline" (a closed <details> may still lay out its
// content, so getClientRects alone does not say it is hidden)
const visibleLines = () => $$('#glDoc .ln[data-id]').filter(el => el.getClientRects().length && !el.closest('details:not([open])'));
// the DOM selection -> the guideline lines it touches, whole lines. A selection that ends at the very start of a
// line (a triple-click, a drag into the margin) or starts at the very end of one does not take that line.
function selectedLines(){
  const ws = window.getSelection();
  if (!ws || ws.isCollapsed || !ws.rangeCount) return null;
  const r = ws.getRangeAt(0), gl = $('#glDoc');
  if (!gl || !gl.contains(r.commonAncestorContainer)) return null;
  const anc = r.commonAncestorContainer.nodeType === 1 ? r.commonAncestorContainer : r.commonAncestorContainer.parentElement;
  if (anc.closest('.fb-chip, .strike-form')) return null;
  const els = $$('#glDoc .ln[data-id]').filter(el => r.intersectsNode(el) && !el.closest('details:not([open])'));
  const blank = (sc, so, ec, eo) => { const x = document.createRange(); try { x.setStart(sc, so); x.setEnd(ec, eo); } catch { return true; } return !x.toString().trim(); };
  const tx = el => el.querySelector('.tx') || el;
  while (els.length > 1 && blank(tx(els[els.length-1]), 0, r.endContainer, r.endOffset)) els.pop();
  while (els.length > 1 && blank(r.startContainer, r.startOffset, tx(els[0]), tx(els[0]).childNodes.length)) els.shift();
  const ids = els.filter(el => tx(el).textContent.trim()).map(el => el.dataset.id);
  return ids.length ? ids : null;
}
// after a drag: show the snapped lines for a moment, then ask
function takeSelection(){
  const ids = selectedLines();
  if (!ids) return;
  window.getSelection().removeAllRanges();
  hideFb();
  setProbe(ids, 'mouse');
  clearTimeout(askTimer);
  askTimer = setTimeout(askProbe, 120);          // long enough to see the lines snap, short enough to feel immediate
}
function setProbe(ids, how){
  askSeq++;
  probe = { ids, anchor: ids[0], head: ids[ids.length - 1], how, asked: false };
  paintProbe();
}
function paintProbe(){
  $$('#glDoc .ln.probe').forEach(x => x.classList.remove('probe', 'probe-a', 'probe-z'));
  $$('#glDoc .ask-pill').forEach(x => x.remove());
  if (probe) {
    const els = probe.ids.map(lineEl).filter(Boolean);
    if (els.length) {
      els.forEach(el => el.classList.add('probe'));
      els[0].classList.add('probe-a'); els[els.length - 1].classList.add('probe-z');
      if (probe.how !== 'mouse' && !probe.asked)
      { els[els.length - 1].insertAdjacentHTML('beforeend', `<span class="ask-pill" role="status">${els.length} line${els.length > 1 ? 's' : ''} · <b>Enter</b> to ask · <b>Esc</b> to clear</span>`);
        const g = $('#glDoc').getBoundingClientRect(); document.documentElement.style.setProperty('--pill-x', Math.round(g.left + g.width / 2) + 'px'); }
    }
  }
  marksRefresh();
}
// shift + arrows: from the snapped lines or the line last clicked
function extendProbe(stepN){
  const order = visibleLines().map(el => el.dataset.id);
  if (!probe) {
    const from = (fbSel && fbSel.side === 'guideline' ? fbSel.ids[fbSel.ids.length - 1] : null) || anchorLine;
    if (!from || !order.includes(from)) return false;
    hideFb();
    probe = { ids: [from], anchor: from, head: from, how: 'key', asked: false };
  }
  const a = order.indexOf(probe.anchor), h = order.indexOf(probe.head);
  if (a < 0 || h < 0) return false;
  const nh = Math.max(0, Math.min(order.length - 1, h + stepN));
  askSeq++;
  probe = { ids: order.slice(Math.min(a, nh), Math.max(a, nh) + 1), anchor: probe.anchor, head: order[nh], how: 'key', asked: false };
  paintProbe();
  const el = lineEl(probe.head); if (el) el.scrollIntoView({ block: 'nearest' });
  return true;
}
const AC_MARK = { documented:['•','m-ev'], missing:['–','m-q'], contradicted:['✗','m-n'], not_chart:['○','m-o'], clear:['•','m-ev'],
                  applies:['✗','m-n'], unclear:['?','m-q'], struck:['—','m-o'] };
const AC_SRC = { known: "Already on this case's checklist", added: "On this case's checklist", cached: 'Asked earlier', asked: '' };
// back from an ask: the requirement that was open, else the packet
function closeCard(quiet){
  clearTimeout(askTimer); askSeq++;
  probe = null; paintProbe();
  if (!quiet && $('.ask-card')) { if (selectedCrit && reqById[selectedCrit]) showRequirement(selectedCrit); else showPacket(); }
}
const rangeWords = ids => { const t = rangeLabel(ids); return t ? t[0].toUpperCase() + t.slice(1) : ''; };
const ASK_MAX = 40;
async function askProbe(){
  clearTimeout(askTimer); hintDone();
  if (!probe || !doc) return;
  probe.asked = true; paintProbe();
  const ids = probe.ids.slice(), id = doc.chart_id;
  panelMode = 'ask';
  if (ids.length > ASK_MAX) {           // the server's limit (app/ask.MAX_LINES), said here before anything is sent
    $$('.nv[aria-current], .tl[aria-current]').forEach(x => x.removeAttribute('aria-current'));
    setSide(`<div class="ask-card" role="region" aria-label="What the case shows for these lines">${sideHead(esc(rangeWords(ids)), true)}
      <div class="ac-body"><div class="ac-note">That is ${ids.length} lines. Select at most ${ASK_MAX} at a time: one requirement or one paragraph.</div></div></div>`);
    return;
  }
  $$('.nv[aria-current], .tl[aria-current]').forEach(x => x.removeAttribute('aria-current'));
  setSide(`<div class="ask-card" role="region" aria-label="What the case shows for these lines" aria-live="polite">
    ${sideHead(esc(rangeWords(ids)), true)}<div class="ac-body"></div></div>`);
  const seq = askSeq;
  // a known answer comes back at once; the "checking" line shows only when the chart is really being read
  const slow = setTimeout(() => { const b = $('.ask-card .ac-body'); if (seq === askSeq && b) b.innerHTML = '<div class="checking">Checking the case…</div>'; }, 140);
  let a;
  try { a = await post('/review/' + encodeURIComponent(id) + '/ask', { span_ids: ids, by: myName() || null }); }
  catch (e) {
    if (seq !== askSeq) return;
    failed(e, m => { const b = $('.ask-card .ac-body'); if (b) b.innerHTML = `<div class="err">${esc(m)}</div>`; });
    return;
  } finally { clearTimeout(slow); }
  if (seq !== askSeq || !doc || doc.chart_id !== id) return;
  doc.probes = [...(doc.probes || []), { spans: a.spans, source: a.source, mark: a.ruling.mark }];
  markProbes();
  lastAsk = a;
  fillCard(a);
}
function cardQuote(e, mark){
  const h = prettyHeading(e.heading), dt = e.date ? fmtDate(e.date) : '', forSide = e.side === 'for', rel = UNSURE.includes(mark);
  // an exclusion reads as on the side panel: its "against" lines show it does not apply (the calm style)
  const ex = isExcl(reqById[e.criterion]) || ['clear', 'applies'].includes(mark);
  return `<div class="evq still ${rel ? 'rel' : (ex ? !forSide : forSide) ? 'for' : 'against'}"><span class="side">${rel ? 'Related lines' : ex ? (forSide ? 'Shows it applies' : "Shows it doesn't apply") : forSide ? 'Supports' : 'Contradicts'}</span><q>${esc(tidy(e.text))}</q>
    <small>${esc([h, h.includes(dt) ? '' : dt, e.page != null ? 'page ' + e.page : ''].filter(Boolean).join(' · '))}</small></div>`;
}
// the logic as a small checklist: "A and either B or C" reads as A, then "One of these:" B, C
function logicHtml(t, top){
  if (t.criterion) {
    const [g, cls] = MARK[t.mark] || ['', ''];
    return `<li class="pt"><span class="st ${cls}">${g}</span><span class="pt-w">${t.other ? '<span class="pt-o">Another option on this checklist:</span> ' : ''}“${esc(trimDot(t.words))}”</span><span class="pt-s ${cls}">${esc(sayOf(t.mark, t.say))}</span></li>`;
  }
  const head = { all: 'All of these:', any: 'One of these:', not: 'None of this may apply:', at_least: `At least ${t.k} of these:` }[t.op];
  const kids = `<ul>${t.kids.map(k => logicHtml(k, false)).join('')}</ul>`;
  return top && t.op === 'all' ? kids : `${top ? '<ul>' : ''}<li class="grp"><span class="grp-h">${esc(head)}</span>${kids}</li>${top ? '</ul>' : ''}`;
}
function fillCard(a){
  const c = $('.ask-card'); if (!c) return;
  const [g, cls] = AC_MARK[a.ruling.mark] || ['', ''];
  const src = AC_SRC[a.source] || '';
  c.querySelector('.sp-head').innerHTML = `<span class="sp-kicker">${esc(rangeWords(a.spans))}${src ? ` · <span class="ac-src">${esc(src)}</span>` : ''}</span><a href="#" class="sp-x" title="Close (Esc)">Close <kbd>Esc</kbd></a>`;
  let h = '';
  if (a.where && a.where.say) h += `<div class="ac-where">${esc(a.where.say)}</div>`;
  h += `<div class="ac-ruling sp-ruling ${cls}"><b>${g}</b>${esc(sayOf(a.ruling.mark, a.ruling.say))}</div>`;
  if (a.why_not) h += `<div class="ac-why">${esc(a.why_not)}</div>`;
  if (a.logic && a.parts > 1) h += `<div class="ac-logic">${logicHtml(a.logic, true)}</div>`;
  if (a.lead) {
    h += cardQuote(a.lead, a.ruling.mark);
    if ((a.more || []).length) h += `<a href="#" class="ac-more" aria-expanded="false">+ ${a.more.length} more</a><div class="ac-rest">${a.more.map(q => cardQuote(q, a.ruling.mark)).join('')}</div>`;
  } else if (['missing', 'unclear'].includes(a.ruling.mark)) h += `<div class="none">Nothing in the case supports this yet.</div>`;
  if ((a.set_aside || []).length) h += `<div class="ac-note">${a.set_aside.length === 1 ? 'One selected line is' : a.set_aside.length + ' selected lines are'} a heading or lead-in, not something to document.</div>`;
  for (const k of (a.struck || [])) h += `<div class="ac-note">Removed for this case: “${esc(trimDot(k.words))}”${k.by ? ' by ' + esc(k.by) : ''}.</div>`;
  if ((a.problems || []).length) h += `<div class="ac-look">Worth a look: ${esc(a.problems.join(' '))}</div>`;
  if (a.added) h += `<div class="ac-added">Added to this case's checklist by <b>${esc(a.added.by || 'a person')}</b>${a.added.at ? ' on ' + esc(fmtDate(a.added.at)) : ''}. <a href="#" class="ac-undo" data-aid="${esc(a.added.id)}">Take it off</a></div>`;
  else if (a.can_add) h += `<div class="ac-act">${myName() ? '' : '<input type="text" class="ac-by" placeholder="Your name" maxlength="60">'}<button class="primary ac-add">Add to this case's checklist</button><span class="hint ac-msg">Only this case changes; the result is worked out again with it.</span></div>`;
  if ((a.requirements || []).length === 1 && reqById[a.requirements[0]]) h += `<div class="ac-open"><a href="#" data-sel="${esc(a.requirements[0])}">Open this requirement</a></div>`;
  c.querySelector('.ac-body').innerHTML = h;
  const add = c.querySelector('.ac-add'); if (add && probe && probe.how !== 'mouse') add.focus({ preventScroll: true });
}
function cardClick(e, a){
  if (!a) return;
  const more = e.target.closest('.ac-more');
  if (more) { e.preventDefault(); const open = more.getAttribute('aria-expanded') !== 'true'; more.setAttribute('aria-expanded', String(open));
    more.textContent = open ? '– less' : `+ ${a.more.length} more`; more.nextElementSibling.classList.toggle('open', open); return; }
  const id = encodeURIComponent(doc.chart_id);
  const add = e.target.closest('.ac-add');
  if (add) {
    const inp = $('.ask-card .ac-by'), by = ((inp && inp.value) || myName()).trim();
    if (inp && !by) { $('.ask-card .ac-msg').innerHTML = '<span class="err">Type your name; the person signing off reads it.</span>'; inp.focus(); return; }
    keepName(by); add.disabled = true; $('.ask-card .ac-msg').textContent = 'Adding and working out the result again…';
    post('/review/' + id + '/additions', { span_ids: a.spans, by: by || null })
      .then(nd => { redraw(nd, null); reopen(a.spans); })
      .catch(err => { add.disabled = false; failed(err, t => { const m = $('.ask-card .ac-msg'); if (m) m.innerHTML = `<span class="err">${esc(t)}</span>`; else calm(t); }); });
    return;
  }
  const un = e.target.closest('.ac-undo');
  if (un) {
    e.preventDefault(); un.textContent = 'Taking it off…';
    api('/review/' + id + '/additions/' + encodeURIComponent(un.dataset.aid) + '?by=' + encodeURIComponent(myName()), {method:'DELETE'})
      .then(nd => { redraw(nd, null); reopen(a.spans); }).catch(err => { un.textContent = 'Take it off'; failed(err); });
  }
}
// after the case is drawn again: the same lines, asked again (free: the answer is on file)
function reopen(ids){ if (!ids.every(lineEl)) return; setProbe(ids, 'key'); askProbe(); }
function markProbes(){
  $$('#glDoc .ln.probed').forEach(x => x.classList.remove('probed'));
  for (const p of ((doc && doc.probes) || [])) for (const i of (p.spans || [])) { const el = lineEl(i); if (el) el.classList.add('probed'); }
}

// ------------------------------------------------------------------ styles: the same page, drawn in one of several looks
// static/review-styles/<name>.css; ?style=<name> or the switcher at the foot of the case; remembered in this browser.
const STYLES = { plain: 'Plain', clinic: 'Clinic', marker: 'Marker', classic: 'Classic' };
function styleSwitchHtml(){
  const cur = document.documentElement.dataset.style;
  return `<div class="style-switch">Style: ${Object.entries(STYLES).map(([k, w]) => `<a href="#" data-style="${k}" ${k === cur ? 'aria-current="true"' : ''}>${w}</a>`).join(' · ')}</div>`;
}
function wireStyleSwitch(){
  $$('.style-switch [data-style]').forEach(a => a.onclick = e => {
    e.preventDefault();
    document.documentElement.dataset.style = a.dataset.style;
    try { localStorage.setItem('review.style', a.dataset.style); } catch {}
    $$('.style-switch [data-style]').forEach(x => x.toggleAttribute('aria-current', x === a));
    renderFeedback();
    if (window.ReviewMarks) ReviewMarks.restyle();
  });
}
// the highlighter (static/review-marks.js, the Marker style): measure again after anything moved
function marksRefresh(){ if (window.ReviewMarks) ReviewMarks.refresh(); }

// ------------------------------------------------------------------ add a chart: the dialog (as index.html), posting to the review flow
const dlg = { chart: null, glFile: null, busy: false };
const dlgChoice = () => dlg.glFile ? '__new__' : ($('#dlgGl').value || null);
function renderDlgGuidelines(){
  const keep = $('#dlgGl').value;
  $('#dlgGl').innerHTML = guidelines.map(g => `<option value="${esc(g.id)}">${esc(glTitle(g))}</option>`).join('');
  if (keep && guidelines.some(g => g.id === keep)) $('#dlgGl').value = keep;
  $('#dlgGl').onchange = dlgUpdate;
  dlgUpdate();
}
function dlgUpdate(){
  $('#dlgGlRow').hidden = !!dlg.glFile || !guidelines.length;
  $('#dlgGo').disabled = dlg.busy || !(dlg.chart && dlgChoice());
}
function openDlg(){
  dlg.chart = null; dlg.glFile = null; dlg.busy = false;
  $('#dlgMsg').textContent = ''; $('#dropFiles').value = ''; $('#dropGot').innerHTML = '';
  renderDlgGuidelines();
  $('#addDlg').classList.remove('hidden');
  $('#dropZone').focus();
}
function closeDlg(){ if (dlg.busy) return; const was = !$('#addDlg').classList.contains('hidden'); $('#addDlg').classList.add('hidden'); if (was && $('#addDlg').contains(document.activeElement || null)) $('#addBtn').focus({ preventScroll: true }); }
$('#addBtn').onclick = openDlg;
$('#dlgCancel').onclick = closeDlg;
$('#addDlg').onclick = e => { if (e.target === $('#addDlg')) closeDlg(); };
// What ⌘/Ctrl+Enter does where the person is: the function to run, a no-op when the key is ours but there is nothing
// to do (a disabled button, a request already in flight), or null when it is not ours. The sign-in name box (handled in the
// keydown listener) means "continue". Sign-off is never done by key: a gentle hint.
function modEnter(t, typing, dlgOpen){
  const noop = () => {}, vis = el => !!(el && el.getClientRects().length);
  const click = b => vis(b) && !b.disabled ? () => b.click() : noop;
  if (dlgOpen) return click($('#dlgGo'));
  const form = $$('.strike-form').find(vis);
  if (form && (!typing || t.closest('.strike-form'))) return click(form.querySelector('.strike-go'));
  if (t.closest('#fbBar')) return click($('#fbSend'));
  const card = $('.ask-card');
  if (vis(card) && (!typing || card.contains(t))) return click(card.querySelector('.ac-add'));
  if (t.id === 'signName') return signHint;     // the sign-off name box: the key never signs
  if (typing) return null;
  if (!doc) return null;
  if (probe && !probe.asked && doc.state === 'done') return () => askProbe();
  if (doc.state === 'paused' && gateKeys && $('.gcards')) return () => gateKeys.go();
  if (doc.state !== 'done' || !doc.case || doc.nofit) return null;
  if (panelMode === 'req') return click($('#acceptBtn'));
  if (panelMode === 'packet') return signHint;
  return noop;
}
function signHint(){
  const sb = $('#signBtn'), so = (doc && doc.signoff) || {};
  if (!sb || sb.disabled || !so.can_sign) return;
  if ($('#side').classList.contains('peek')) setSheet(true);
  const m = $('#copyMsg'); if (m) m.innerHTML = '<span class="err">Signing off is deliberate: click Sign off. The keyboard does not do it.</span>';
}
document.addEventListener('keydown', e => {
  if (document.documentElement.classList.contains('signin')) {          // the sign-in screen is up: the page behind it stays still
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && !e.altKey && !e.isComposing) {   // ⌘/Ctrl+Enter in the name box: continue
      e.preventDefault(); if (!e.repeat) $('#signinForm').requestSubmit();
    }
    return;
  }
  const t = e.target && e.target.closest ? e.target : document.body;
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || '') || t.isContentEditable;
  const dlgOpen = !$('#addDlg').classList.contains('hidden');
  const form = t.closest('.strike-form'), bar = t.closest('#fbBar'), card = t.closest('.ask-card');
  const shown = sel => [...document.querySelectorAll(sel)].find(el => el.getClientRects().length) || null;
  if (e.key === 'Escape') {
    if (e.isComposing) return;
    // the innermost thing first: the dialog, a form being filled in, the feedback bar, a field, then the panel
    if (dlgOpen) closeDlg();
    else if (form) { const btn = form.previousElementSibling; form.remove(); if (btn) btn.focus({ preventScroll: true }); }
    else if (fbSel) { hideFb(); if (bar) focusSelected(); }
    else if (typing && !card) t.blur();
    else if (shown('.evmore[aria-expanded="true"], .ac-more[aria-expanded="true"]')) { const m = shown('.evmore[aria-expanded="true"], .ac-more[aria-expanded="true"]'); m.click(); m.focus({ preventScroll: true }); }   // "+ N more" folds
    else if (shown('.draft.show')) { const d = shown('.draft.show'); d.classList.remove('show'); d.textContent = ''; const o = d.id === 'auditDraft' ? $('#auditBtn') : $('#copyBtn') || $('#msgBtn'); if (o) o.focus({ preventScroll: true }); }   // the packet preview / draft
    else if (probe || $('.ask-card')) closeCard();
    else if (panelMode === 'notes') closeSide();
    else if (panelMode === 'req') { const was = selectedCrit; showPacket(); const nv = was && (curView() === 'tree' ? placeOf(was) : document.querySelector(`.nv[data-crit="${CSS.escape(was)}"]`)); if (nv) nv.focus({ preventScroll: true }); }
    else if (panelMode === 'packet' && sheetOpen && shown('#side .sheet-bar')) { setSheet(false); const tg = $('#side .sb-toggle'); if (tg) tg.focus({ preventScroll: true }); }   // the phone sheet rests
    else if (doc && doc.state === 'paused' && $('#noneConfirm') && !$('#noneConfirm').hidden) $('#noneNo').click();   // the gate: "None of these" asked
    else if (doc && doc.state === 'paused' && gateKeys && gateKeys.fold && gateKeys.fold()) {}                    // the gate: the "more" list folds
    else return;
    e.preventDefault();
    return;
  }
  // ⌘/Ctrl+Enter is "do it" for whatever is being filled in or open; see modEnter. Key repeat is swallowed, never acted on.
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && !e.altKey) {
    if (e.isComposing) return;
    const act = modEnter(t, typing, dlgOpen);
    if (act) { e.preventDefault(); if (!e.repeat) act(); }
    return;
  }
  if (dlgOpen) return;                           // nothing behind the dialog moves while it is open
  if (form && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) {
    const chips = [...form.querySelectorAll('.chip')];
    const n = /^[1-9]$/.test(e.key) ? +e.key - 1 : -1;
    if (n >= 0 && n < chips.length) { e.preventDefault(); pickReason(form, chips[n].dataset.code); return; }
    const at = chips.indexOf(t.closest('.chip')), dir = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    if (at >= 0 && dir) { e.preventDefault(); chips[(at + dir + chips.length) % chips.length].focus(); return; }
    if (at >= 0 && (e.key === 'j' || e.key === 'k')) return;   // the page's own keys stay out of the form
  }
  if (doc && doc.state === 'paused' && gateKeys && $('.gcards')) { if (!typing) gateKey(e); return; }
  if (!doc || doc.state !== 'done' || !doc.case || doc.nofit) return;
  if (typing || e.altKey || e.metaKey || e.ctrlKey) return;
  if (e.shiftKey && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) { if (extendProbe(e.key === 'ArrowDown' ? 1 : -1)) e.preventDefault(); return; }
  if ((e.key === 'Enter' || e.key === ' ') && t.matches('mark.q[data-crit][tabindex]')) { e.preventDefault(); selectRequirement(t.dataset.crit, true); t.focus({ preventScroll: true }); return; }
  if (e.key === 'Enter' && probe && !probe.asked) { e.preventDefault(); askProbe(); return; }
  if (e.shiftKey) return;
  if ((e.key === 't' || e.key === 'T') && hasTree(doc.case)) { e.preventDefault(); setView(curView() === 'tree' ? 'guideline' : 'tree', 'switch'); return; }
  if (e.key === 'ArrowDown' || e.key === 'j') { e.preventDefault(); step(1); }
  else if (e.key === 'ArrowUp' || e.key === 'k') { e.preventDefault(); step(-1); }
});
// a click on nothing in particular (the desk, the page's margins, the guideline's blank space) lets go of the selected
// lines and their answer, as clicking away from a text selection does
document.addEventListener('click', e => {
  if (!(probe || $('.ask-card')) || e.button !== 0 || e.shiftKey) return;
  const t = e.target;
  if (!t.closest || t.closest('#side, #fbBar, .dlg, .ln[data-id], a, button, input, textarea, select, summary, label, .fb-notes, .fb-chip')) return;
  const ws = window.getSelection(); if (ws && !ws.isCollapsed) return;   // the end of a drag, not a click
  closeCard();
});
// on a touch screen a selection is made with a long press and its handles, with no mouseup: once it has rested
// for a moment (the handles let go), snap and ask as a drag would
let touchSelTimer = 0;
document.addEventListener('selectionchange', () => {
  if (!matchMedia('(pointer:coarse)').matches || !doc || doc.state !== 'done') return;
  clearTimeout(touchSelTimer);
  touchSelTimer = setTimeout(() => { if (selectedLines()) takeSelection(); }, 900);
});
// a drag over guideline lines, wherever the mouse is let go: snap to whole lines, then ask
document.addEventListener('mouseup', e => {
  if (doc && doc.state === 'done' && !(e.target.closest && e.target.closest('#side, .fb-bar, .dlg, .rq-nav'))) setTimeout(takeSelection, 0);
});
// one drop zone for the chart and, optionally, the payer's policy: a PDF whose name says guideline / policy /
// coverage / NCD / LCD is the guideline, anything else the chart; two charts by name: the first is the chart and
// the second the guideline (Swap puts them the other way round). Dropping anywhere on the page opens the dialog.
const GL_NAME = /guideline|policy|coverage|\bncd\b|\blcd\b|medical[-_ ]?policy|criteria/i;
function takeFiles(list){
  const pdfs = [...(list || [])].filter(f => /pdf$/i.test(f.type) || /\.pdf$/i.test(f.name));
  if (pdfs.length) {
    const gl = pdfs.filter(f => GL_NAME.test(f.name)), ch = pdfs.filter(f => !GL_NAME.test(f.name));
    const chart = ch[0] || null, glf = gl[0] || ch[1] || null;
    if (chart) dlg.chart = chart;
    if (glf) dlg.glFile = glf;
  }
  showFiles();
}
function showFiles(){
  $('#dropGot').innerHTML = [dlg.chart ? `Case: <b>${esc(dlg.chart.name)}</b>` : '', dlg.glFile ? `Guideline: <b>${esc(dlg.glFile.name)}</b>` : '']
    .filter(Boolean).join(' · ') + (dlg.chart && dlg.glFile ? ' <a href="#" id="dropSwap">Swap</a>' : '');
  const sw = $('#dropSwap'); if (sw) sw.onclick = e => { e.preventDefault(); e.stopPropagation(); [dlg.chart, dlg.glFile] = [dlg.glFile, dlg.chart]; showFiles(); };
  dlgUpdate();
}
$('#dropFiles').onchange = e => takeFiles(e.target.files);
for (const [el, open] of [[$('#dropZone'), false], [document.body, true]]) {
  el.addEventListener('dragover', e => { if ([...(e.dataTransfer.types || [])].includes('Files')) { e.preventDefault(); $('#dropZone').classList.add('over'); } });
  el.addEventListener('dragleave', () => $('#dropZone').classList.remove('over'));
  el.addEventListener('drop', e => { e.preventDefault(); e.stopPropagation(); $('#dropZone').classList.remove('over');
    if (open && $('#addDlg').classList.contains('hidden')) openDlg(); takeFiles(e.dataTransfer.files); });
}
$('#dlgGo').onclick = async () => {
  const choice = dlgChoice(); if (!dlg.chart || !choice) return;
  const fd = new FormData(); fd.append('file', dlg.chart);
  if (choice === '__new__') { if (!dlg.glFile) return; fd.append('guideline', dlg.glFile); $('#dlgMsg').textContent = `Reading ${dlg.glFile.name} and ${dlg.chart.name}…`; }
  else { fd.append('guideline_id', choice); $('#dlgMsg').textContent = `Reading ${dlg.chart.name}…`; }
  dlg.busy = true; dlgUpdate(); $('#dlgCancel').disabled = true;
  try { const d = await api('/review/charts', {method:'POST', body:fd});
    dlg.busy = false; $('#dlgCancel').disabled = false; closeDlg();
    await loadGuidelines(); await loadOrders(); go(d.chart_id); }
  catch(err){ dlg.busy = false; $('#dlgCancel').disabled = false; dlgUpdate(); $('#dlgMsg').innerHTML = `<span class="err">${esc(err.message)}</span>`; }
};

// ------------------------------------------------------------------ who is working: one remembered name for every record (confirm, accept, strike, add, sign off)
// the sign-in screen: a name, nothing else (no password; it names the person on every record). Shown before the app
// when no name is remembered in this browser (there is no Switch: the owner's call).
let afterSignin = null, signinY = 0;       // what to finish once a name is given (an accept asked for without one)
function showSignin(why, then){
  const f = $('#signinName'); f.value = myName(); f.classList.toggle('need', !!why);
  $('#signinNote').textContent = why || 'Shown on what you confirm, accept and sign off.';
  afterSignin = then || null; signinY = window.scrollY;
  closeDlg();
  document.documentElement.classList.add('signin');
  requestAnimationFrame(() => { f.focus({ preventScroll: true }); f.select(); });
}
function signedIn(){ const n = myName(); $('#meShown').textContent = n; }
$('#signinForm').onsubmit = e => {
  e.preventDefault();
  const v = ($('#signinName').value || '').trim().replace(/\s+/g, ' ').slice(0, NAME_MAX);
  if (!v) { $('#signinName').classList.add('need'); $('#signinNote').textContent = 'Type your name to continue.'; $('#signinName').focus(); return; }
  keepName(v); signedIn();
  document.documentElement.classList.remove('signin');
  const then = afterSignin; afterSignin = null;
  scrollTo(0, then ? signinY : 0);
  if (window.ReviewMarks) ReviewMarks.refresh();
  const a = $('#addBtn'); if (a && !doc) a.focus({ preventScroll: true });
  if (then) then();                               // finish what the name was asked for (the accept)
};
$('#signinName').oninput = () => { $('#signinName').classList.remove('need'); };
$('#glToggle').onclick = () => glOpen($('#glToggle').getAttribute('aria-expanded') !== 'true');
// signed in or out in another tab: the rail says who is signed in here
addEventListener('storage', e => { if (e.key === NAME_KEY && myName()) signedIn(); });
signedIn();
if (document.documentElement.classList.contains('signin')) showSignin();
// accepting and signing off are a person's acts: without a name (it was cleared in another tab), ask for it first
function needName(why, then){
  if (myName()) return false;
  showSignin(why || 'Type your name to continue.', then);
  return true;
}

// ------------------------------------------------------------------ start
window.Review = { select: selectRequirement, load, state: () => doc, go, probe: () => probe, panel: () => panelMode };
loadGuidelines().catch(() => {}).then(() => loadOrders()).catch(() => {}).then(() => { const id = idFromLocation(); if (id) load(id); else home(); });
})();

// the theme: Soft (a dimmed light, the default), Light or Dark; the button steps through them and is remembered
// in this browser (the head script applies it before drawing)
(function(){
  const b = document.getElementById('themeBtn'); if (!b) return;
  const ORDER = ['soft', 'light', 'dark'], NAME = { soft: 'Soft', light: 'Light', dark: 'Dark' };
  const cur = () => ORDER.includes(document.documentElement.dataset.theme) ? document.documentElement.dataset.theme : 'soft';
  const show = () => { const t = cur(), n = ORDER[(ORDER.indexOf(t) + 1) % ORDER.length];
    b.textContent = NAME[t]; b.setAttribute('aria-label', `Theme: ${NAME[t]}. Switch to ${NAME[n]}`); b.title = `Theme: ${NAME[t]} · click for ${NAME[n]}`; };
  b.onclick = () => { const t = ORDER[(ORDER.indexOf(cur()) + 1) % ORDER.length];
    document.documentElement.dataset.theme = t; try { localStorage.setItem('review.theme', t); } catch {}
    show(); if (window.ReviewMarks) ReviewMarks.restyle(); };
  show();
})();

// the rail folds to a slim strip (the toggle at its top, or "[" outside a field): "Check a chart" as an icon and one
// count per queue lane; the main area takes the width back. Remembered in this browser. On a phone the rail is
// already a bar, so the fold only applies on a desk-width screen (the CSS ignores it below 901px).
(function(){
  const b = document.getElementById('railBtn'), root = document.documentElement; if (!b) return;
  const folded = () => root.classList.contains('rail-min');
  const label = () => { const f = folded(); b.setAttribute('aria-expanded', String(!f));
    const w = f ? 'Expand the sidebar' : 'Collapse the sidebar'; b.setAttribute('aria-label', w); b.title = w + '  ['; };
  let t = 0;
  const set = min => {
    if (min === folded()) return;
    const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!still) { root.classList.add('rail-anim'); clearTimeout(t); t = setTimeout(() => { root.classList.remove('rail-anim'); if (window.ReviewMarks) ReviewMarks.refresh(); }, 200); }
    root.classList.toggle('rail-min', min);
    try { if (min) localStorage.setItem('review.rail', 'min'); else localStorage.removeItem('review.rail'); } catch (e) {}
    label(); lanes();
    if (window.ReviewMarks) ReviewMarks.refresh();      // measure again now, and once the width has settled (above)
  };
  // folded, each lane is its count: a focusable circle (Tab reaches it; its tooltip names the lane); open, a plain count
  const lanes = () => document.querySelectorAll('#groups .lane-n').forEach(n => n.tabIndex = folded() ? 0 : -1);
  window.ReviewRail = { toggle: () => set(!folded()), set, folded };
  b.onclick = () => set(!folded());
  // a lane's circle in the folded strip opens the rail at that lane: the lane in view, focus on its first case
  document.getElementById('groups').addEventListener('click', e => {
    const h = folded() && e.target.closest('.group h2'); if (!h) return;
    const lane = h.closest('.group'); set(false);
    const r = lane.querySelector('.row'); if (r) r.focus({ preventScroll: true });
    // once the width has settled (the rows wrap while it moves), bring the lane into view only if it is off screen
    setTimeout(() => { const box = lane.getBoundingClientRect(); if (box.top < 0 || box.top > innerHeight - 60) lane.scrollIntoView({ block: 'nearest' }); }, 220);
  });
  document.querySelector('.app').addEventListener('transitionend', e => { if (e.target.classList.contains('app') && window.ReviewMarks) ReviewMarks.refresh(); });
  document.addEventListener('keydown', e => {
    if (e.key !== '[' || e.metaKey || e.ctrlKey || e.altKey || e.isComposing || e.defaultPrevented) return;
    const t = e.target || document.body;
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || '') || t.isContentEditable) return;
    if (!document.getElementById('addDlg').classList.contains('hidden') || root.classList.contains('signin')) return;
    if (!matchMedia('(min-width:901px)').matches) return;
    e.preventDefault(); set(!folded());
  });
  label();
})();
