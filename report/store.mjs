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

/* one section per site that has the store switched on; returns null when there is nothing to show */
export function storeReport({ sites, moves, items, from, to, since, until, siteName }) {
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
    secs.push(`<section class="st"><h2>مخزن: ${esc(siteName(s))}</h2>
    <table><thead><tr><th>الخامة</th><th>الوحدة</th><th>رصيد أول الأسبوع</th><th>توريد الأسبوع</th><th>منصرف الأسبوع</th><th>الرصيد الحالي</th><th>آخر جرد</th></tr></thead><tbody>
    ${groups.map(g => (g.subs ? `<tr class="grp"><td colspan="7" class="tl">${esc(g.name)}</td></tr>` : '') + g.rows.map(x => `<tr${x.r.bal < 0 ? ' class="bad"' : ''}><td class="tl">${esc(x.it.name)}</td><td>${esc(x.it.unit || '')}</td><td class="n">${fmt(x.r.open)}</td><td class="n">${fmt(x.r.inQ)}</td><td class="n">${fmt(x.r.out)}</td><td class="n b">${fmt(x.r.bal)}</td><td>${x.r.last ? esc(x.r.last.date) : '—'}</td></tr>`).join('')).join('')}
    </tbody></table>
    ${low.length ? `<p class="warn">رصيد بالسالب (يحتاج جرد أو مراجعة): ${low.map(x => esc(x.it.name)).join('، ')}</p>` : ''}
    ${ins.length ? `<h3>توريدات الأسبوع (${ins.length})</h3><table><thead><tr><th>التاريخ</th><th>الخامة</th><th>الكمية</th><th>الوحدة</th><th>المورد</th><th>ملاحظات</th><th>سجّله</th></tr></thead><tbody>${ins.map(m => { const d = m.data || {}; return `<tr><td class="n">${esc(m.date)}</td><td class="tl">${esc(label(d.item))}</td><td class="n">${fmt(d.qty)}</td><td>${esc(unit(d.item))}</td><td class="tl">${esc(d.supplier || '')}</td><td class="tl">${esc(d.notes || '')}</td><td>${esc(d.by || '')}</td></tr>`; }).join('')}</tbody></table>` : '<p>لا توجد توريدات هذا الأسبوع.</p>'}
    ${counts.length ? `<h3>جرد الأسبوع</h3><table><thead><tr><th>التاريخ</th><th>الخامة</th><th>الوحدة</th><th>الرصيد الدفتري</th><th>الموجود فعلًا</th><th>المنصرف</th></tr></thead><tbody>${counts.map(c => `<tr><td class="n">${esc(c.date)}</td><td class="tl">${esc(label(c.id))}</td><td>${esc(unit(c.id))}</td><td class="n">${fmt(c.book)}</td><td class="n b">${fmt(c.actual)}</td><td class="n">${c.adj ? 'رصيد افتتاحي' : fmt(c.out)}</td></tr>`).join('')}</tbody></table>` : '<p>لم يتم جرد هذا الأسبوع.</p>'}
    </section>`);
  }
  if (!secs.length) return null;
  return { nIn, nCount, changed, sections: secs.join('') };
}

export function storeHtml({ title, sub, sections, logo }) {
  return `<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>${esc(title)}</title><style>
  @page{size:A4 portrait;margin:12mm 10mm}*{box-sizing:border-box}
  body{margin:0;font-family:"Noto Naskh Arabic","Noto Sans Arabic","Amiri","DejaVu Sans",Tahoma,Arial,sans-serif;font-size:10.5px;color:#111}
  .hd{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid #111;padding-bottom:8px;margin-bottom:8px}.hd img{height:46px}
  h1{margin:0;font-size:18px}h2{font-size:13px;margin:14px 0 5px;padding:4px 8px;background:#e6e6e6;border-radius:4px}h3{font-size:11.5px;margin:10px 0 4px}.sub{margin:0 0 8px;color:#333}
  table{width:100%;border-collapse:collapse;margin-bottom:6px}thead{display:table-header-group}tr{page-break-inside:avoid}
  th,td{border:1px solid #999;padding:3px 5px;text-align:center;vertical-align:top}th{background:#e6e6e6;font-size:10px}
  td.tl{text-align:right}td.n{direction:ltr;white-space:nowrap}td.b{font-weight:bold}tr.grp td{background:#f2f2f2;font-weight:bold}tr.bad td{background:#f6dcdc}
  .warn{color:#b3261e;font-weight:bold}section.st+section.st{page-break-before:always}.foot{margin-top:12px;font-size:9px;color:#666}
  </style></head><body>
  <div class="hd"><div><h1>${esc(title)}</h1></div>${logo ? `<img src="${logo}" alt="ADC">` : ''}</div>
  <p class="sub">${esc(sub)}</p>
  ${sections}
  <p class="sub">المنصرف يُحسب عند كل جرد: الرصيد قبله + ما ورد − الموجود فعلًا. الرصيد الحالي = آخر جرد + ما ورد بعده.</p>
  <p class="foot">ADC CONSTRUCTION</p></body></html>`;
}
