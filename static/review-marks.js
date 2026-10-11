/* The Marker style's highlighter (static/review-styles/marker.css), after the "Two Markers" study, made plain for a
   clinic. One fixed WebGL canvas sits under the page; the text above it stays real, transparent and selectable.
   Two pens:
     the check's     a pale, even, soft-edged wash over each requirement's own words (the <mark class="q"> runs the
                     page draws from the quote's position, never the whole list item): light blue when documented,
                     a quiet warm tint of the same pen when missing or contradicted (fuller once added to the ask), a deeper settled blue once a
                     person accepted it, a faint grey-blue for an option that was not needed, nothing when struck
     the person's    a warm chisel-tip stroke that follows the selection live while dragging (highlight to ask) and
                     stays on the snapped lines once let go
   Marks are measured with getClientRects (merged per visual line) in page coordinates and drawn each frame at the
   current scroll; measured again on resize, on layout changes, when fonts load and whenever the page calls
   ReviewMarks.refresh() (after a render, a selection, the side panel or a fold changing). No ambient motion: a frame
   is drawn only when something changed. Without WebGL (or in another style) nothing is drawn here and the style's
   CSS fallback (html.nogl) paints plain backgrounds instead. Colours are the style's tokens (--pen-*). */
(function () {
'use strict';
const root = document.documentElement;
const active = () => ['marker'].includes(root.dataset.style);
let cv = null, gl = null, buf = null, loc = {}, ok = false, tried = false;
let marks = [], human = [], draft = [], raf = 0, mq = 0, down = false;
const P = {};

const VS = `
attribute vec2 a_c; attribute vec4 a_r; attribute vec3 a_t; attribute vec2 a_p;
uniform vec2 u_view; uniform float u_scroll;
varying vec2 v_l; varying vec2 v_s; varying vec3 v_t; varying vec2 v_p;
const float PAD = 4.0;
void main(){
  vec2 size = a_r.zw; vec2 local = a_c * (size + 2.0 * PAD) - PAD;
  vec2 pos = a_r.xy + local; pos.y -= u_scroll;
  vec2 cl = pos / u_view * 2.0 - 1.0; gl_Position = vec4(cl.x, -cl.y, 0.0, 1.0);
  v_l = local; v_s = size; v_t = a_t; v_p = a_p;
}`;
// even washes with soft edges; the person's pen has slanted (chisel) ends. No grain, no wobble, no pooling.
const FS = `
precision mediump float;
varying vec2 v_l; varying vec2 v_s; varying vec3 v_t; varying vec2 v_p;
uniform float u_dark;
float sdBox(vec2 p, vec2 b, float r){ vec2 q = abs(p) - b + r; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r; }
void main(){
  float alpha = v_p.x, kind = v_p.y;
  vec2 c = v_l - v_s * 0.5;
  float a;
  if (kind < 0.5) {
    float h2 = v_s.y * 0.5;
    a = smoothstep(1.4, -1.4, sdBox(c, vec2(v_s.x * 0.5, h2), min(h2, 4.0)));
  } else {
    float x = c.x + c.y * 0.35;
    a = smoothstep(0.9, -0.9, max(abs(x) - v_s.x * 0.5, abs(c.y) - v_s.y * 0.5));
  }
  a = clamp(a * alpha, 0.0, 1.0);
  vec3 col = u_dark > 0.5 ? v_t * a : mix(vec3(1.0), v_t, a);
  gl_FragColor = vec4(col, 1.0);
}`;

function setup(){
  if (tried) return ok;
  tried = true;
  cv = document.createElement('canvas'); cv.id = 'marks'; cv.setAttribute('aria-hidden', 'true'); cv.style.visibility = 'hidden';
  document.body.prepend(cv);
  try {
    gl = cv.getContext('webgl', { alpha: false, antialias: false, premultipliedAlpha: false, preserveDrawingBuffer: true, powerPreference: 'low-power' });
    if (!gl) throw new Error('no webgl');
    const sh = (t, src) => { const s = gl.createShader(t); gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
    const prog = gl.createProgram();
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
    gl.useProgram(prog); buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    let off = 0;
    for (const [n, sz] of [['a_c', 2], ['a_r', 4], ['a_t', 3], ['a_p', 2]]) {
      const l = gl.getAttribLocation(prog, n); gl.enableVertexAttribArray(l); gl.vertexAttribPointer(l, sz, gl.FLOAT, false, 11 * 4, off); off += sz * 4;
    }
    loc.view = gl.getUniformLocation(prog, 'u_view'); loc.scroll = gl.getUniformLocation(prog, 'u_scroll'); loc.dark = gl.getUniformLocation(prog, 'u_dark');
    gl.enable(gl.BLEND); ok = true;
  } catch (e) { ok = false; root.classList.add('nogl'); }
  theme(); size();
  return ok;
}
function size(){ if (!cv) return; const dpr = Math.min(window.devicePixelRatio || 1, 2), w = Math.round(innerWidth * dpr), h = Math.round(innerHeight * dpr);
  if (cv.width === w && cv.height === h) return need();
  cv.width = w; cv.height = h;
  // resizing clears the buffer to black: draw again now, in the same task, so no black frame is ever shown
  if (ok && gl) { if (raf) { cancelAnimationFrame(raf); raf = 0; } frame(); } else need(); }
const dark = () => root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
function theme(){
  const cs = getComputedStyle(root);
  const rgb = n => cs.getPropertyValue(n).trim().split(/\s+/).map(Number).map(v => (v || 0) / 255);
  for (const k of ['doc', 'acc', 'miss', 'bad', 'alt', 'human']) P[k] = { c: rgb('--pen-' + k), a: parseFloat(cs.getPropertyValue('--pen-' + k + '-a')) || 1 };
  P.bg = rgb('--bg-rgb'); P.dark = dark(); P.over = cs.getPropertyValue('--marks-over').trim() === '1';
  // the wash's breathing room around a requirement's words (--mark-pad-x / -y in the theme; the old 2 / -1 without them)
  const num = (n, d) => { const v = parseFloat(cs.getPropertyValue(n)); return isNaN(v) ? d : v; };
  P.px = num('--mark-pad-x', 2); P.py = num('--mark-pad-y', -1);
  need();
}

// ---------------------------------------------------------------- measuring
function lineRects(list){
  const raw = [], sx = scrollX, sy = scrollY;
  for (const q of list) { if (q.width < 1 || q.height < 4) continue; raw.push({ l: q.left + sx, t: q.top + sy, r: q.right + sx, b: q.bottom + sy }); }
  raw.sort((p, q) => p.t - q.t || p.l - q.l);
  const out = [];
  for (const q of raw) {
    const last = out[out.length - 1];
    if (last && Math.abs((q.t + q.b) / 2 - (last.t + last.b) / 2) < (q.b - q.t) * 0.5) { last.l = Math.min(last.l, q.l); last.r = Math.max(last.r, q.r); last.t = Math.min(last.t, q.t); last.b = Math.max(last.b, q.b); }
    else out.push({ ...q });
  }
  return out.map(q => ({ x: q.l, y: q.t, w: q.r - q.l, h: q.b - q.t }));
}
// the text inside an element, not its padding (an indented line keeps its indent clear of the stroke)
function textRects(el){ const r = document.createRange(); r.selectNodeContents(el); return lineRects(Array.from(r.getClientRects())); }
function measure(){
  marks = []; human = [];
  if (!down) draft = [];        // the live stroke stays until the snapped one replaces it: no blank frame between them
  if (!active() || !ok) { need(); return; }
  const docEl = document.getElementById('glDoc'); if (!docEl) { need(); return; }
  if (docEl.dataset.view === 'tree') { draft = []; need(); return; }    // the tree view: no words of the guideline on screen, nothing to draw
  for (const m of docEl.querySelectorAll('mark.q[data-crit]')) {
    const tone = m.classList.contains('struck') ? null : m.closest('.preview-page') ? 'alt' : m.classList.contains('acc') ? 'acc'
      : m.classList.contains('t-miss') ? 'miss' : m.classList.contains('t-bad') ? 'bad' : m.classList.contains('t-alt') ? 'alt' : 'doc';
    if (!tone) continue;
    marks.push({ crit: m.dataset.crit, tone, sel: m.classList.contains('sel') || m.classList.contains('inask'), rects: textRects(m) });
  }
  // one requirement's words that run on from one PDF line to the next inside a flowing sentence are two <mark>s side
  // by side on one visual line: drawn as one wash, or their padded ends would overlap into a darker seam
  for (const m of marks) m.draw = m.rects.map(r => ({ ...r }));
  for (let i = 1; i < marks.length; i++) {
    const a = marks[i - 1], b = marks[i];
    if (a.crit !== b.crit || a.tone !== b.tone || a.sel !== b.sel || !a.draw.length || !b.draw.length) continue;
    const x = a.draw[a.draw.length - 1], y = b.draw[0];
    if (Math.abs((x.y + x.h / 2) - (y.y + y.h / 2)) < x.h * 0.5 && y.x - (x.x + x.w) < 8 && y.x >= x.x) {
      const top = Math.min(x.y, y.y), bot = Math.max(x.y + x.h, y.y + y.h);
      x.w = y.x + y.w - x.x; x.y = top; x.h = bot - top; b.draw.shift();
    }
  }
  // the snapped lines as one stroke per visual line: where two lines of the PDF meet inside a flowing sentence their
  // strokes join instead of overlapping (an overlap would show as a darker notch)
  const pr = [];
  for (const t of docEl.querySelectorAll('.ln.probe .tx')) { const r = document.createRange(); r.selectNodeContents(t); pr.push(...r.getClientRects()); }
  if (pr.length) human.push({ rects: lineRects(pr) });
  need();
}
function refresh(){ if (mq) return; mq = requestAnimationFrame(() => { mq = 0; if (active()) { setup(); theme(); } measure(); }); }

// ---------------------------------------------------------------- the live stroke while dragging
// the selected text's own boxes: a range's rects also include whole elements it spans (a page number in the gutter,
// a status dot), which would stretch the stroke into the margin
function textOnly(range, within){
  const out = [], root = range.commonAncestorContainer.nodeType === 3 ? range.commonAncestorContainer.parentNode : range.commonAncestorContainer;
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: n => range.intersectsNode(n) && n.parentElement.closest('.tx') && within.contains(n) ? 1 : 3 });
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    const r = document.createRange(); r.selectNodeContents(n);
    if (n === range.startContainer) r.setStart(n, range.startOffset);
    if (n === range.endContainer) r.setEnd(n, range.endOffset);
    out.push(...r.getClientRects());
  }
  return out;
}
function liveSelection(){
  if (!active() || !ok) return;
  const s = getSelection(), docEl = document.getElementById('glDoc');
  if (!down) return;            // let go: measure() hands over from the live stroke to the snapped lines
  if (!s || !s.rangeCount || s.isCollapsed || !docEl || !docEl.contains(s.getRangeAt(0).commonAncestorContainer)) { if (draft.length) { draft = []; need(); } return; }
  draft = lineRects(textOnly(s.getRangeAt(0), docEl));
  need();
}
document.addEventListener('selectionchange', liveSelection);
addEventListener('pointerdown', () => { down = true; }, true);
addEventListener('pointerup', () => { down = false; if (draft.length) setTimeout(refresh, 0); }, true);

// ---------------------------------------------------------------- drawing (only when something changed)
function need(){ if (!raf) raf = requestAnimationFrame(frame); }
function frame(){
  raf = 0;
  if (!cv) return;
  cv.style.display = active() && ok ? 'block' : 'none';
  if (!active() || !ok) return;
  const W = innerWidth, H = innerHeight, sy = scrollY;
  gl.viewport(0, 0, cv.width, cv.height);
  const bg = P.over ? (P.dark ? [0, 0, 0] : [1, 1, 1]) : P.bg; gl.clearColor(bg[0], bg[1], bg[2], 1); gl.clear(gl.COLOR_BUFFER_BIT);
  if (P.dark) gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_COLOR); else gl.blendFunc(gl.DST_COLOR, gl.ZERO);
  const data = [], C = [[0, 0], [1, 0], [0, 1], [1, 0], [1, 1], [0, 1]];
  const put = (r, pen, alpha, kind, grow, py = -1) => {
    if (r.y + r.h < sy - 20 || r.y > sy + H + 20) return;
    const x = r.x - grow, w = r.w + 2 * grow, y = kind ? r.y + r.h * 0.1 : r.y - py, h = kind ? r.h * 0.8 : r.h + 2 * py;
    for (const c of C) data.push(c[0], c[1], x, y, w, h, pen.c[0], pen.c[1], pen.c[2], alpha, kind);
  };
  for (const m of marks) { const pen = P[m.tone]; for (const r of m.draw || m.rects) put(r, pen, pen.a * (m.sel ? 1 : 0.86), 0, P.px, P.py); }
  for (const m of human) for (const r of m.rects) put(r, P.human, P.human.a, 1, 3);
  for (const r of draft) put(r, P.human, P.human.a, 1, 2);
  gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(data), gl.DYNAMIC_DRAW);
  gl.uniform2f(loc.view, W, H); gl.uniform1f(loc.scroll, sy); gl.uniform1f(loc.dark, P.dark ? 1 : 0);
  if (data.length) gl.drawArrays(gl.TRIANGLES, 0, data.length / 11);
  if (cv.style.visibility) cv.style.visibility = '';
}
addEventListener('scroll', need, { passive: true });
addEventListener('resize', () => { size(); refresh(); });
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { theme(); refresh(); });
if (window.ResizeObserver) document.addEventListener('DOMContentLoaded', () => { const m = document.getElementById('main'); if (m) new ResizeObserver(refresh).observe(m); });
if (document.fonts && document.fonts.ready) document.fonts.ready.then(refresh);
// a face first used after load (the guideline's serif, an italic) swaps in later and reflows the text under the washes
if (document.fonts && document.fonts.addEventListener) document.fonts.addEventListener('loadingdone', refresh);

window.ReviewMarks = {
  refresh,
  restyle(){ theme(); refresh(); need(); },
  state: () => ({ ok, active: active(), marks: marks.length, human: human.length, draft: draft.length }),
  rects: () => marks.map(m => m.rects),          // what is drawn, in page coordinates (for checking alignment)
};
})();
