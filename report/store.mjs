import { RS, thCss, fontPx } from './style.mjs';
import { crVal, duesTable, invoices } from './dues.mjs';
// ADC حسابات المواقع — تقرير المخزن الأسبوعي (نفس حساب التطبيق: المنصرف يُحسب من الجرد)
const num = v => (+v || 0);
const r2 = v => Math.round(num(v) * 100) / 100;
const fmt = v => r2(v).toLocaleString('en-US', { maximumFractionDigits: 2 });
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const ts = m => m.created_at ? Date.parse(m.created_at) : num((m.data || {}).at);

function calc(moves, from, to) {
  const R = new Map(), g = id => { let r = R.get(id); if (!r) { r = { id, open: 0, inQ: 0, out: 0, bal: 0, known: false, started: false, last: null, counts: [], ins: [] }; R.set(id, r); } return r; };
  const start = (r, inP) => { if (inP && !r.started) { r.open = r.bal; r.started = true; } };
  const list = moves.filter(m => !m.deleted).sort((a, b) => (a.date || '').localeCompare(b.date || '') || (a.kind === b.kind ? 0 : a.kind === 'in' ? -1 : 1) || ts(a) - ts(b));
  for (const m of list) {
    if (to && m.date > to) break;
    const inP = !from || m.date >= from, d = m.data || {};
    if (m.kind === 'in') { if (!d.item) continue; const r = g(d.item), q = num(d.qty); start(r, inP); r.bal += q; if (inP) { r.inQ += q; r.ins.push(m); } }
    else if (m.kind === 'ret') { if (!d.item) continue; const r = g(d.item), q = num(d.qty); start(r, inP); r.bal -= q; if (inP) r.inQ -= q; }
    else if (m.kind !== 'count') continue;
    else for (const [id, v] of Object.entries(d.lines || {})) {
      if (v === '' || v == null || isNaN(+v)) continue;
      const r = g(id), c = +v, diff = r.bal - c; start(r, inP);
      let out = diff, adj = 0; if (!r.known && diff < 0) { adj = -diff; out = 0; }
      if (inP) { r.out += out; r.open += adj; r.counts.push({ date: m.date, book: r2(r.bal), actual: c, out: r2(out), adj: r2(adj) }); }
      r.bal = c; r.known = true; r.last = { date: m.date, qty: c };
    }
  }
  for (const r of R.values()) { if (!r.started) r.open = r.bal; for (const k of ['open', 'inQ', 'out', 'bal']) r[k] = r2(r[k]); }
  return R;
}


/* توريدات الأسبوع متجمعة بالفاتورة (نفس التطبيق: الخصم مكتوب على كل سطر من الفاتورة idisc) */
const nrm = v => String(v || '').replace(/[أإآ]/g, 'ا').replace(/ة/g, 'ه').replace(/ى/g, 'ي').replace(/[ً-ْ]/g, '').replace(/\s+/g, ' ').trim().toLowerCase();
const invKey = m => { const d = m.data || {}; return d.bon ? 'b:' + d.bon : 'x:' + (m.date || '') + '|' + nrm(d.supplier) + '|' + nrm(d.inv); };
/* الرقم الداخلي: «فاتورة <بند التوريد> رقم (N)» بترتيب تاريخ التوريد في الموقع (نفس التطبيق) */
function invNos(moves) {
  const g = new Map();
  for (const m of moves) { if (m.deleted || m.kind !== 'in') continue; const d = m.data || {}, k = invKey(m); let x = g.get(k); if (!x) g.set(k, x = { k, date: m.date || '', sitem: '', at: ts(m) }); if (!x.sitem && d.sitem) x.sitem = d.sitem; }
  const by = new Map(); for (const x of g.values()) { if (!x.sitem) continue; const s = nrm(x.sitem); if (!by.has(s)) by.set(s, []); by.get(s).push(x); }
  const out = new Map(); for (const L of by.values()) { L.sort((a, b) => a.date.localeCompare(b.date) || a.at - b.at); L.forEach((x, i) => out.set(x.k, i + 1)); }
  return out;
}
function invTable(ins, label, unit, nos = new Map()) {
  const g = new Map();
  for (const m of ins) { const d = m.data || {}, k = invKey(m); let x = g.get(k);
    if (!x) g.set(k, x = { k, date: m.date, sup: d.supplier || '', inv: d.inv || '', sitem: d.sitem || '', by: d.by || '', lines: [], gross: 0, disc: 0, rate: 0, priced: false });
    x.lines.push(m); x.gross += num(d.price) * num(d.qty); if (num(d.price)) x.priced = true; if (num(d.idisc) > x.disc) x.disc = num(d.idisc); if (num(d.itax) > x.rate) x.rate = num(d.itax); if (!x.inv && d.inv) x.inv = d.inv; if (!x.sitem && d.sitem) x.sitem = d.sitem; }
  const invs = [...g.values()].sort((a, b) => (a.date || '').localeCompare(b.date || ''));
  const pr = invs.some(x => x.priced), cols = pr ? 6 : 4; let G = 0, D = 0, T = 0;
  const body = invs.map(x => { x.gross = r2(x.gross); G += x.gross; D += x.disc;
    const head = `<tr class="inv"><td colspan="${cols}" class="tl"><b>${x.sitem && nos.get(x.k) ? 'فاتورة ' + esc(x.sitem) + ' رقم ( ' + nos.get(x.k) + ' )' : x.inv ? 'فاتورة رقم ' + esc(x.inv) : 'بدون رقم فاتورة'}</b>${x.sitem && nos.get(x.k) && x.inv ? ' · فاتورة المورد ' + esc(x.inv) : ''} · المورد: <b>${esc(x.sup || '—')}</b> · تاريخ التوريد: <b>${esc(x.date)}</b>${x.by ? ' · سجّله: ' + esc(x.by) : ''}</td></tr>`;
    const ls = x.lines.map(m => { const d = m.data || {}, v = num(d.price) * num(d.qty); return `<tr><td class="tl">${esc(label(d.item))}</td><td class="n">${fmt(d.qty)}</td><td>${esc(unit(d.item))}</td>${pr ? `<td class="n">${num(d.price) ? fmt(d.price) : ''}</td><td class="n">${v ? fmt(v) : ''}</td>` : ''}<td class="tl">${esc(String(d.notes || '').replace(/^فاتورة رقم [^—]*(— )?/, ''))}</td></tr>`; }).join('');
    const net = r2(x.gross - x.disc), tax = x.rate ? r2(net * x.rate / 100) : 0; x.tax = tax; T += tax;
    const sm = (t, v) => `<tr class="sm"><td colspan="4" class="tl">${t}</td><td class="n">${fmt(v)}</td><td></td></tr>`;
    const foot = !pr ? '' : (x.disc || tax ? sm('إجمالي الأصناف', x.gross) : '') + (x.disc ? sm('الخصم', x.disc) : '') + (tax ? sm('صافي بعد الخصم', net) + sm('الضريبة ' + fmt(x.rate) + '%', tax) : '')
      + `<tr class="net"><td colspan="4" class="tl">${tax ? 'إجمالي الفاتورة بالضريبة' : 'صافي الفاتورة'}</td><td class="n">${fmt(net + tax)}</td><td></td></tr>`;
    return head + ls + foot; }).join('');
  const n = invs.length, nl = n === 1 ? 'فاتورة واحدة' : n === 2 ? 'فاتورتين' : n + ' فواتير';
  const tot = !pr ? '' : `<tr class="tot"><td colspan="4" class="tl">صافي توريدات الأسبوع (${nl}${D ? ' · خصومات ' + fmt(D) : ''}${T ? ' · ضريبة ' + fmt(T) : ''})</td><td class="n">${fmt(G - D + T)}</td><td></td></tr>`;
  return `<h3>توريدات الأسبوع (${nl})</h3><table><thead><tr><th>الخامة</th><th>الكمية</th><th>الوحدة</th>${pr ? '<th>السعر</th><th>القيمة</th>' : ''}<th>ملاحظات</th></tr></thead><tbody>${body}${tot}</tbody></table>`;
}
/* one section per site that has the store switched on; returns null when there is nothing to show */
export function storeReport({ sites, moves, items, from, to, since, until, siteName, duesFor = () => [] }) {
  const live = items.filter(i => !i.deleted), byId = new Map(items.map(i => [i.id, i]));
  const mains = live.filter(i => !i.parent).sort((a, b) => a.name.localeCompare(b.name, 'ar'));
  const subsOf = id => live.filter(i => i.parent === id).sort((a, b) => a.name.localeCompare(b.name, 'ar'));
  const label = id => { const i = byId.get(id); if (!i) return 'خامة غير معروفة'; const p = i.parent && byId.get(i.parent); return p ? p.name + ' — ' + i.name : i.name; };
  const unit = id => (byId.get(id) || {}).unit || '';
  let nIn = 0, nCount = 0, changed = 0;
  const secs = [];
  for (const s of sites) {
    const ms = moves.filter(m => m.site_id === s.site_id);
    changed += ms.filter(m => { const t = Date.parse(m.updated_at || m.created_at || 0); return t > since && t <= until; }).length;
    if (!ms.some(m => !m.deleted)) continue;
    const R = calc(ms, from, to), seen = new Set(), groups = [];
    for (const m of mains) {
      const rows = [];
      if (R.has(m.id)) { rows.push({ it: m, r: R.get(m.id) }); seen.add(m.id); }
      for (const x of subsOf(m.id)) if (R.has(x.id)) { rows.push({ it: x, r: R.get(x.id) }); seen.add(x.id); }
      if (rows.length) groups.push({ name: m.name, subs: subsOf(m.id).length > 0, rows });
    }
    const lost = [...R.keys()].filter(id => !seen.has(id));
    if (lost.length) groups.push({ name: 'خامات محذوفة من القائمة', subs: true, rows: lost.map(id => ({ it: byId.get(id) || { id, name: 'خامة غير معروفة', unit: '' }, r: R.get(id) })) });
    const ins = [], counts = [];
    for (const g of groups) for (const x of g.rows) { for (const m of x.r.ins) ins.push(m); for (const c of x.r.counts) counts.push({ ...c, id: x.it.id }); }
    ins.sort((a, b) => (a.date || '').localeCompare(b.date || '')); counts.sort((a, b) => a.date.localeCompare(b.date));
    nIn += ins.length; nCount += new Set(counts.map(c => c.date)).size;
    const low = groups.flatMap(g => g.rows).filter(x => x.r.bal < 0);
    const nm = siteName(s), dues = duesFor(s.site_id) || [];
    const html = `<section class="st"><h2>مخزن: ${esc(nm)}</h2>
    <table><thead><tr><th>الخامة</th><th>الوحدة</th><th>رصيد أول الأسبوع</th><th>توريد الأسبوع</th><th>منصرف الأسبوع</th><th>الرصيد الحالي</th><th>آخر جرد</th></tr></thead><tbody>
    ${groups.map(g => (g.subs ? `<tr class="grp"><td colspan="7" class="tl">${esc(g.name)}</td></tr>` : '') + g.rows.map(x => `<tr${x.r.bal < 0 ? ' class="bad"' : ''}><td class="tl">${esc(x.it.name)}</td><td>${esc(x.it.unit || '')}</td><td class="n">${fmt(x.r.open)}</td><td class="n">${fmt(x.r.inQ)}</td><td class="n">${fmt(x.r.out)}</td><td class="n b">${fmt(x.r.bal)}</td><td>${x.r.last ? esc(x.r.last.date) : '—'}</td></tr>`).join('')).join('')}
    </tbody></table>
    ${low.length ? `<p class="warn">رصيد بالسالب (يحتاج جرد أو مراجعة): ${low.map(x => esc(x.it.name)).join('، ')}</p>` : ''}
    ${ins.length ? invTable(ins, label, unit, invNos(ms)) : '<p>لا توجد توريدات هذا الأسبوع.</p>'}
    ${(() => { const cr = ms.filter(m => !m.deleted && (m.kind === 'ret' || m.kind === 'cn') && (!from || m.date >= from) && (!to || m.date <= to)).sort((a, b) => (a.date || '').localeCompare(b.date || '')); if (!cr.length) return ''; return `<h3>مرتجعات وإشعارات خصم الأسبوع</h3><table><thead><tr><th>التاريخ</th><th>النوع</th><th>المورد</th><th>البيان</th><th>القيمة</th></tr></thead><tbody>${cr.map(m => { const d = m.data || {}, v = crVal(m); return `<tr><td class="n">${esc(m.date)}</td><td>${m.kind === 'cn' ? 'إشعار خصم' : 'مرتجع'}</td><td class="tl">${esc(d.supplier || '')}${d.supPend ? ' (بانتظار التسجيل)' : ''}</td><td class="tl">${m.kind === 'cn' ? esc(d.notes || d.inv || '') : esc(label(d.item)) + ' · ' + fmt(num(d.qty)) + ' ' + esc(unit(d.item))}</td><td class="n">(${fmt(r2(v))})</td></tr>`; }).join('')}</tbody></table>`; })()}
    ${counts.length ? `<h3>جرد الأسبوع</h3><table><thead><tr><th>التاريخ</th><th>الخامة</th><th>الوحدة</th><th>الرصيد الدفتري</th><th>الموجود فعلًا</th><th>المنصرف</th></tr></thead><tbody>${counts.map(c => `<tr><td class="n">${esc(c.date)}</td><td class="tl">${esc(label(c.id))}</td><td>${esc(unit(c.id))}</td><td class="n">${fmt(c.book)}</td><td class="n b">${fmt(c.actual)}</td><td class="n">${c.adj ? 'رصيد افتتاحي' : fmt(c.out)}</td></tr>`).join('')}</tbody></table>` : '<p>لم يتم جرد هذا الأسبوع.</p>'}
    ${duesTable(dues, nm)}
    </section>`;
    /* ورقة Excel للموقع */
    const rows = [], st = [], add = (r, k = 0) => { rows.push(r); st.push(k); };
    add(['مخزن: ' + nm + ' — من ' + from + ' إلى ' + to], 3); add([]);
    add(['الخامة', 'الوحدة', 'رصيد أول الأسبوع', 'توريد الأسبوع', 'منصرف الأسبوع', 'الرصيد الحالي', 'آخر جرد'], 1);
    for (const g of groups) { if (g.subs) add([g.name], 3); for (const x of g.rows) add([x.it.name, x.it.unit || '', x.r.open, x.r.inQ, x.r.out, x.r.bal, x.r.last ? x.r.last.date : '—']); }
    const wk = invoices(ms).filter(x => (!from || x.date >= from) && (!to || x.date <= to)).sort((a, b) => a.date.localeCompare(b.date));
    if (wk.length) { add([]); add(['توريدات الأسبوع'], 3); add(['التاريخ', 'رقم فاتورة المورد', 'المورد', 'بند التوريد', 'إجمالي الأصناف', 'الخصم', 'الضريبة', 'الإجمالي'], 1);
      for (const x of wk) add([x.date, x.inv, x.sup + (x.pend ? ' (بانتظار التسجيل)' : ''), x.sitem, r2(x.gross), x.disc || '', x.tax || '', x.due]);
      add(['الإجمالي', '', '', '', r2(wk.reduce((a, x) => a + x.gross, 0)), r2(wk.reduce((a, x) => a + x.disc, 0)), r2(wk.reduce((a, x) => a + x.tax, 0)), r2(wk.reduce((a, x) => a + x.due, 0))], 3); }
    if (dues.length) { add([]); add(['المستحق للموردين والمقاولين'], 3); add(['الاسم', 'النوع', 'البند', 'المصدر', 'المستحق', 'المدفوع', 'المتبقي'], 1);
      for (const r of dues) add([r.name, r.kind, r.item || '', r.note, r.due, r.paid, r.left]);
      add(['الإجمالي', '', '', '', r2(dues.reduce((a, r) => a + r.due, 0)), r2(dues.reduce((a, r) => a + r.paid, 0)), r2(dues.reduce((a, r) => a + r.left, 0))], 3); }
    secs.push({ siteId: s.site_id, name: nm, html, sheet: { name: nm, rows, styles: st, widths: [26, 14, 16, 16, 16, 16, 14, 16], freeze: 0 } });
  }
  if (!secs.length) return null;
  return { nIn, nCount, changed, sites: secs, sections: secs.map(x => x.html).join('') };
}

export function storeHtml({ title, sub, sections, logo, note = true }) {
  return `<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>${esc(title)}</title><style>
  @page{size:A4 portrait;margin:12mm 10mm}*{box-sizing:border-box}
  body{margin:0;font-family:"Noto Naskh Arabic","Noto Sans Arabic","Amiri","DejaVu Sans",Tahoma,Arial,sans-serif;font-size:10.5px;color:#111}
  .hd{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid #111;padding-bottom:8px;margin-bottom:8px}.hd img{height:46px}
  h1{margin:0;font-size:18px}h2{font-size:13px;margin:14px 0 5px;padding:4px 8px;background:#e6e6e6;border-radius:4px}h3{font-size:11.5px;margin:10px 0 4px}.sub{margin:0 0 8px;color:#333}
  table{width:100%;border-collapse:collapse;margin-bottom:6px}thead{display:table-header-group}tr{page-break-inside:avoid}
  th,td{border:1px solid #999;padding:3px 5px;text-align:center;vertical-align:top}th{${thCss('background:#e6e6e6')};font-size:${fontPx(10)}px}
  td.tl{text-align:right}td.n{direction:ltr;white-space:nowrap}td.b{font-weight:bold}tr.grp td{background:#f2f2f2;font-weight:bold}tr.bad td{background:#f6dcdc}tr.inv td{background:#eef3f8;border-top:2px solid #555}tr.sm td{color:#444}tr.net td{font-weight:bold}tr.tot td{font-weight:bold;background:#f2f2f2;border-top:2px solid #111}
  .warn{color:#b3261e;font-weight:bold}section.st+section.st{page-break-before:always}h2,h3{page-break-after:avoid;break-after:avoid}h3{page-break-before:always;break-before:page}.stm h3,h3.dues{page-break-before:auto;break-before:auto}h3+table{page-break-before:avoid}.foot{margin-top:12px;font-size:9px;color:#666}
  </style></head><body>
  <div class="hd"><div><h1>${esc(title)}</h1>${RS.sub ? `<div style="font-size:10px;color:#555">${esc(RS.sub)}</div>` : ''}</div>${logo ? `<img src="${logo}" alt="ADC">` : ''}</div>
  <p class="sub">${esc(sub)}</p>
  ${sections}
  ${note ? '' : '<!--'}<p class="sub">المنصرف يُحسب عند كل جرد: الرصيد قبله + ما ورد − الموجود فعلًا. الرصيد الحالي = آخر جرد + ما ورد بعده.</p>${note ? '' : '-->'}
  <p class="foot">${esc(RS.footer || '')}</p></body></html>`;
}
