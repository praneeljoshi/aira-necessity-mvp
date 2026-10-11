/* The decision read as the guideline: a view of the patient screen (static/index.html loads this and calls
   TreeView.render(d, prefixHtml) with GET /api/orders/{id}/tree's answer). Everything shown is resolved by code
   from stored lines; see app/tree.py. Vocabulary rule: requirement / documented / ask, never the internals'
   words, outside the "How this was decided" fold. */
(function () {
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let chartId = '';
const STATE = {
  MET:          { v:'v-ready', verdict:'Ready to submit.',                                        box:'ready' },
  INSUFFICIENT: { v:'v-needs', verdict:n=>`Ask ${n} for something first.`,                        box:'needs' },
  NOT_MET:      { v:'v-needs', verdict:n=>`Review with ${n} before submitting.`,                  box:'needs' },
  NOT_COVERED:  { v:'v-needs', verdict:n=>`Review with ${n}: the payer lists this as not covered.`, box:'no' },
  CANT_CHECK:   { v:'v-wait', verdict:"Can't check this one against this guideline.",             box:'' },
};
// marks: glyph + colour class for each thing a line can be
const MARK = {
  documented:['✓','m-y'], missing:['–','m-q'], contradicted:['✗','m-n'], not_needed:['○','m-o'], other_option:['○','m-o'],
  confirm:['?','m-q'], clear:['✓','m-y'], applies:['✗','m-n'], unclear:['?','m-q'], part_shown:['✗','m-n'], part_clear:['✓','m-y'],
  not_covered:['✗','m-n'], unchecked:['○','m-o'], struck:['—','m-o'],
};
const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const fmtDate = iso => { if (!iso) return ''; const [y,m,d] = iso.split('-').map(Number); return `${MONTHS[m-1]} ${d}, ${y}`; };
// "Visit Date: September 30, 2025 | Attending: Dr. … | Type: Follow-Up" -> "Follow-Up visit, September 30, 2025"
function prettyHeading(h){
  if (!h) return '';
  return h.split(' › ').map(part => {
    const m = part.match(/^Visit Date:\s*([^|]+?)\s*(?:\|.*?)?(?:\|\s*Type:\s*(.+))?$/i);
    if (m) return (m[2] ? m[2].trim() + ' visit, ' : 'Visit of ') + m[1].trim();
    return part.replace(/^\d+\.\s+/, '').replace(/\b([A-Z]{2,})(?=[\sA-Z&/-]*$)/g, w => w[0] + w.slice(1).toLowerCase());
  }).join(' › ');
}
const tidy = t => String(t).replace(/\s{3,}/g, ' · ').replace(/\s+/g, ' ').trim();
const surgeonName = s => s ? `Dr. ${s.replace(/^Dr\.?\s*/i,'').split(',')[0].trim().split(' ').pop()}` : 'the surgeon';

function renderTree(d, prefix){
  chartId = d.chart_id;
  const r = d.result, o = d.order || {}, t = d.tree || {}, s = STATE[r.determination] || STATE.CANT_CHECK;
  const name = surgeonName(d.surgeon);
  let verdict = typeof s.verdict === 'function' ? s.verdict(name) : s.verdict, vcls = s.v, box = s.box;
  if (r.determination === 'MET' && r.needs_review) { verdict = 'Looks ready; worth a second look first.'; vcls = 'v-needs'; box = 'needs'; }
  if (r.determination === 'MET' && !r.needs_review && d.signoff !== 'signed') verdict = 'Ready for sign-off.';   // signed on /review
  // the guideline by its own title and number (index.html's glTitle / glShort, from GET /api/guidelines), never its file name
  const gl = t.guideline || {}, glName = typeof glTitle === 'function' ? glTitle(gl) : [gl.payer, gl.title].filter(Boolean).join(' — ');
  const glSub = typeof glKicker === 'function' ? glKicker(gl) : '';
  const blocks = Object.fromEntries((t.blocks||[]).map(b => [b.id, b]));

  // what to do next: the missing items first, then the message or the packet
  const misses = t.misses || [];
  let next = '';
  if (r.determination === 'MET') {
    next = `<div class="next ready"><h2>Attach the packet with the request</h2><div class="hint">Every requirement below is documented; the quoted notes are the packet.</div>
      <div class="act"><button class="primary" id="copyBtn">Copy packet</button><span class="hint" id="copyMsg"></span></div><div class="draft" id="draft"></div></div>`;
  } else if (r.determination === 'NOT_COVERED') {
    next = `<div class="next no"><h2>Nothing to check: the guideline stops at the code</h2><div class="hint">${esc(r.reason)}</div>
      <div class="act"><button class="primary" id="copyBtn">Message ${esc(name)}</button><span class="hint" id="copyMsg"></span></div><div class="draft" id="draft"></div></div>`;
  } else if (r.determination === 'CANT_CHECK' || (t.candidates||[]).length) {
    next = `<div class="next needs"><h2>${(t.candidates||[]).length ? 'Which part of the guideline is this procedure for?' : "This guideline can't decide this order"}</h2>
      <div class="hint">${esc(r.reason)}</div>${candidatesHtml(t)}</div>`;
  } else {
    const items = misses.map(m => `<li><a href="#${esc(m.block)}">${esc(missLabel(m))}</a></li>`).join('');
    const bad = misses.filter(m => ['contradicted','applies','part_shown'].includes(m.mark)).length;
    const title = r.determination === 'NOT_MET' ? `The case says otherwise on ${bad === 1 ? 'one point' : (bad || 'some') + ' points'}; review with ${esc(name)}`
                : `${misses.length === 1 ? 'One thing' : misses.length + ' things'} the payer requires ${misses.length === 1 ? "isn't" : "aren't"} in the case yet`;
    next = `<div class="next needs"><h2>${title}</h2>${items ? `<ol>${items}</ol>` : ''}
      <div class="act"><button class="primary" id="copyBtn">Message ${esc(name)}</button><span class="hint" id="copyMsg"></span><span class="hint">Everything else the payer asks for is documented below.</span></div>
      <div class="draft" id="draft"></div></div>`;
  }
  const flag = r.needs_review && (r.review_reasons||[]).length ? `<p class="flag">Worth a second look before submitting: ${esc(r.review_reasons.join(' '))}</p>` : '';

  // legend: only the marks this page uses
  const used = new Set((t.blocks||[]).flatMap(b => [b.mark, ...b.items.map(i => i.mark)]).concat((t.codes||[]).length ? ['not_covered'] : []));
  const LEG = [['documented','Documented in the case'],['missing','Not in the case yet'],['contradicted','The case says otherwise'],['not_needed','Not needed: another option is documented'],['other_option','Another option, not the one being completed'],
               ['clear','Does not apply to this patient'],['applies','Applies: the case shows this'],['unclear',"Can't tell from the case"],['confirm','Confirm outside the case'],['not_covered','Listed as not covered']];
  const legend = LEG.filter(([k]) => used.has(k) || (k==='clear' && (used.has('part_clear'))) || (k==='applies' && used.has('part_shown')))
    .map(([k,w]) => `<span><b class="${MARK[k][1]}">${MARK[k][0]}</b>${esc(w)}</span>`).join('');

  // the guideline, line by line
  let doc = '';
  for (const sec of (t.sections||[])) {
    doc += `<div class="sec">${sec.label ? `<div class="sec-label">${esc(sec.label)}</div>` : ''}`;
    let page = null, prevBlock = null;
    for (let i = 0; i < sec.lines.length; i++) {
      const ln = sec.lines[i], b = ln.block ? blocks[ln.block] : null;
      if (ln.page !== page) { doc += `<div class="pg">page ${ln.page}</div>`; page = ln.page; }
      const mark = b ? (ln.block !== prevBlock ? MARK[b.mark] : ['','']) : ['',''];
      const first = b && ln.block !== prevBlock;
      const ind = (ln.text.match(/^\s*/) || [''])[0].length;      // the printed indent, kept as a margin so the ink covers only words
      doc += `<div class="ln ${ln.kind} ${b ? 'b-' + b.mark : ''} ${first ? 'first' : ''} ${ln.blank_before ? 'blank' : ''}" ${first ? `id="${esc(b.id)}"` : ''} style="--ind:${ind}">
        <span class="mk ${mark[1]}" title="${b ? esc(b.say) : ''}">${mark[0]}</span><span class="tx"><span class="w">${esc(ln.text.slice(ind))}</span></span></div>`;
      const nextLn = sec.lines[i+1];
      if (b && (!nextLn || nextLn.block !== ln.block)) doc += evidenceHtml(b);
      prevBlock = ln.block;
    }
    doc += '</div>';
  }
  for (const c of (t.codes||[])) {
    doc += `<div class="sec"><div class="sec-label">The code table</div>` + c.lines.map((l, i) =>
      `<div class="row-tbl b-contradicted"><span class="mk m-n">${i === 0 ? '✗' : ''}</span><span class="tx">${esc(l.text)}</span></div>`).join('') +
      `<div class="ev e-applies"><div class="it"><span class="st m-n">${esc(c.tag === 'investigational' ? 'Listed as investigational' : c.tag === 'not_addressed' ? 'Listed, but this guideline does not decide it' : 'Listed as not covered')}</span>
        <small>Code ${esc(c.code)}${c.mapped ? ', matched from the procedure name' : ', as written in the case'} · page ${esc(c.lines[0] ? c.lines[0].page : '')}</small></div></div></div>`;
  }
  if (!doc) doc = `<div class="sec"><div class="ln other"><span class="mk"></span><span class="tx">No part of the guideline was checked for this order.</span></div></div>`;

  const pages = [...new Set((t.sections||[]).flatMap(s => s.lines.map(l => l.page)))].sort((a,b)=>a-b);
  $('#main').innerHTML = prefix + `<div class="tv">
    <div class="who"><div><b>${esc(o.patient_name||'Unknown patient')}</b> &nbsp; ${esc(o.procedure_text||'')}${(o.cpt||[]).length?` (${esc(o.cpt.join(', '))})`:''}</div><div>${esc(o.payer||'')}</div></div>
    <p class="verdict ${vcls}">${esc(verdict)}</p>
    <p class="why">${esc(whyLine(r, name))}</p>
    <p class="rule">Checked against ${esc(glName)}${glSub ? ' · ' + esc(glSub) : ''}${pages.length ? `, page${pages.length>1?'s':''} ${esc(pages.join(', '))}` : ''}.</p>
    ${flag}
    ${next}
    <div class="legend">${legend}</div>
    <div class="doc"><div class="doc-head">${glSub ? `<span class="doc-kicker">${esc(glSub)}</span>` : ''}<b>${esc(glName)}</b><span>What the payer requires, in the guideline's own words. Lines in grey are not requirements.</span></div>${doc}</div>
    <details class="fold"><summary>How this was decided</summary>${foldHtml(d)}</details></div>`;

  const copyText = r.determination === 'MET' ? packetText(d) : (d.ask || '');
  const cb = $('#copyBtn');
  if (cb) cb.onclick = async () => {
    $('#draft').textContent = copyText; $('#draft').classList.add('show');
    try { await navigator.clipboard.writeText(copyText); $('#copyMsg').textContent = 'Copied.'; }
    catch { $('#copyMsg').textContent = 'Shown below; select and copy.'; }
  };
  document.querySelectorAll('.it .more').forEach(a => a.onclick = e => { e.preventDefault(); a.closest('.it').classList.add('open'); });
  const rb = $('#candGo');
  if (rb) rb.onclick = async () => {
    const pick = document.querySelector('input[name=cand]:checked'); const target = ($('#candTarget').value || (pick ? pick.value : '')).trim();
    if (!target) return; rb.disabled = true; $('#candMsg').textContent = 'Re-checking…';
    try { await api('/orders/' + encodeURIComponent(chartId) + '/recheck', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({target})}); loadOrders(chartId); }
    catch(e){ $('#candMsg').textContent = e.message; rb.disabled = false; }
  };
}

function missLabel(m){
  const w = m.words.replace(/\.$/, '');
  if (m.mark === 'applies' || m.mark === 'part_shown') return `The case shows “${w}”, which the guideline excludes`;
  if (m.mark === 'contradicted') return `The case says otherwise about “${w}”`;
  if (m.mark === 'unclear') return `Can't tell whether “${w}” applies`;
  return `“${w}” is not in the case yet`;
}

function evidenceHtml(b){
  const many = b.items.length > 1;
  let html = `<div class="ev e-${esc(b.mark)}">`;
  if (b.compound) {
    const shown = b.items.filter(i => i.mark === 'part_shown').map(i => i.words.replace(/\.$/,'')), clear = b.items.filter(i => i.mark === 'part_clear').map(i => i.words.replace(/\.$/,''));
    const line = b.mark === 'clear' ? `Does not apply here: it would need every part to be shown, and “${clear[0] || ''}” is ruled out.`
               : b.mark === 'applies' ? 'Applies: the case shows every part of this.'
               : b.mark === 'unclear' ? "Can't tell from the case whether this applies." : b.say;
    html += `<div class="cmp">${esc(line)}</div>`;
  }
  for (const it of b.items) {
    const [g, cls] = MARK[it.mark] || ['', ''];
    const qs = it.quotes || [], show = qs.slice(0, 2), rest = qs.slice(2);
    const quote = q => { const h = prettyHeading(q.heading), dt = q.date ? fmtDate(q.date) : '';
      return `<q>${esc(tidy(q.text))}</q><small>${esc([h, h.includes(dt) ? '' : dt, 'page ' + q.page].filter(Boolean).join(' · '))}</small>`; };
    html += `<div class="it"><span class="st ${cls}">${g ? `<i class="g">${g}</i> ` : ''}${esc(partWord(it))}</span>${many ? `<span class="wd">“${esc(it.words.replace(/\.$/,''))}”</span>` : ''}
      ${show.map(quote).join('')}${rest.length ? `<a href="#" class="more">${rest.length} more note${rest.length>1?'s':''}</a><div class="hid">${rest.map(quote).join('')}</div>` : ''}
      ${it.note ? `<span class="note">${esc(it.note)}</span>` : ''}</div>`;
  }
  return html + '</div>';
}
function partWord(it){
  if (it.role === 'part') return {part_shown:'The case shows this part', part_clear:'This part is ruled out', unclear:"Can't tell", not_needed:'Not needed', other_option:'Not needed'}[it.mark] || it.say;
  return it.say;
}
function candidatesHtml(t){
  const c = t.candidates || [];
  if (!c.length) return '';
  return `<div class="cands">${c.map((x, i) => `<label><input type="radio" name="cand" value="${esc(x.name)}" ${i===0?'checked':''}><div><b>${esc(x.name)}</b><small>${esc(x.lines.slice(1,4).map(l => l.text.trim()).join(' ').slice(0, 220))}…</small></div></label>`).join('')}
    <div class="act"><input type="text" id="candTarget" placeholder="Or say what the procedure treats, e.g. left great saphenous vein"><button class="primary" id="candGo">Re-check</button><span class="hint" id="candMsg"></span></div></div>`;
}
function whyLine(r, name){
  switch (r.determination) {
    case 'MET': return 'The case documents everything the payer asks for. Attach the packet with the request.';
    case 'INSUFFICIENT': return (r.misses||[]).length ? 'Below, the payer\'s requirements in its own words, with what the case shows beside each. The gaps are marked.' : (r.reason || '');
    case 'NOT_MET': return 'Something in the case conflicts with what the payer requires. A person decides how to proceed; nothing is denied automatically.';
    case 'NOT_COVERED': return 'A person should confirm the code and the intent before anything is told to the patient.';
    default: return r.reason || '';
  }
}
function packetText(d){
  const o = d.order || {};
  const head = `Prior authorization — ${o.patient_name||''}, ${o.procedure_text||''} (${(o.cpt||[]).join(', ')}), ${o.payer||''}\nSupporting documentation:\n`;
  return head + (d.packet||[]).filter(p => !p.missing && p.status !== 'contradicted').map((p,i) => `${i+1}. ${p.label}\n` + (p.quotes||[]).map(q => `   "${q.quote}"\n   — ${q.source||''}`).join('\n')).join('\n');
}
function foldHtml(d){
  const x = d.decided || {}, t = d.tree || {}, c = t.counts || {};
  const secs = (x.sections||[]).map(s => `<li>${esc(s.code)} → “${esc(s.name)}”${s.because ? `, chosen because the order says “${esc(s.because)}”` : ''}</li>`).join('');
  const counts = Object.entries(c).map(([k,v]) => `${v} ${k.replace('_',' ')}`).join(', ');
  return `${secs ? `<p>Guideline section</p><ul>${secs}</ul>` : ''}<p>Requirement rows: ${esc(counts || 'none')}. Each row's words are the guideline's own, checked against the cited lines; each quote is the case's own lines, resolved from the citation; dates shown were found written in the cited note or its heading.</p>
    <p><a href="/api/runs/${esc(x.run_id||'')}" target="_blank">Every model exchange</a> · <a href="/api/orders/${esc(chartId)}/tree" target="_blank">This page's data</a></p>`;
}
window.TreeView = { render: renderTree };
})();
