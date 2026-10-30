// ADC حسابات المواقع — مستحقات الموردين والمقاولين لكل موقع + كشف مختصر لكل اسم (نفس حساب التطبيق)
const num = v => (+v || 0);
const r2 = v => Math.round(num(v) * 100) / 100;
const fmt = v => r2(v).toLocaleString('en-US', { maximumFractionDigits: 2 });
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const norm = v => String(v ?? '').replace(/[ً-ْـ]/g, '').replace(/[أإآ]/g, 'ا').replace(/ة/g, 'ه').replace(/ى/g, 'ي').replace(/\s+/g, ' ').trim();
const ts = m => m.created_at ? Date.parse(m.created_at) : num((m.data || {}).at);
const taxV = (v, rate) => num(rate) > 0 ? r2(num(v) * num(rate) / 100) : 0;
export const crVal = m => { const d = m.data || {}, v = m.kind === 'cn' ? num(d.amount) : num(d.price) * num(d.qty); return r2(v + taxV(v, d.itax)); };
const invKey = m => { const d = m.data || {}; return (m.kind === 'ret' ? 'r' : '') + (d.bon ? 'b:' + d.bon : 'x:' + m.date + '|' + norm(d.supplier) + '|' + norm(d.inv)); };
/* فواتير المخزن (الصافي بعد الخصم + الضريبة) */
export function invoices(moves) {
  const g = new Map();
  for (const m of moves) { if (m.deleted || m.kind !== 'in') continue; const d = m.data || {}, k = m.site_id + '|' + invKey(m); let x = g.get(k);
    if (!x) g.set(k, x = { site: m.site_id, date: m.date, sup: d.supplier || '', inv: d.inv || '', sitem: d.sitem || '', pend: false, gross: 0, disc: 0, rate: 0, bad: 0, n: 0, at: ts(m) });
    x.n++; if (!(num(d.price) > 0)) x.bad++; x.gross += num(d.price) * num(d.qty); if (num(d.idisc) > x.disc) x.disc = num(d.idisc); if (num(d.itax) > x.rate) x.rate = num(d.itax); if (d.supPend) x.pend = true; if (!x.inv && d.inv) x.inv = d.inv; }
  return [...g.values()].map(x => { const net = r2(x.gross - x.disc), tax = taxV(net, x.rate); return { ...x, gross: r2(x.gross), net, tax, due: r2(net + tax) }; });
}
/* مستخلص المقاول: «إجمالي الأعمال بعد الخصومات» (نفس ctCalc في التطبيق) */
export function certAfter(c, all, boq) {
  const item = c => String((c.data || {}).item || '').trim(), key = c => c.site_id + '|' + c.contractor + '|' + item(c);
  const memo = new Map();
  const calc = c => {
    if (memo.has(c.id)) return memo.get(c.id);
    const d = c.data || {}, ch = all.filter(x => x.id !== c.id && key(x) === key(c) && x.no < c.no).sort((a, b) => a.no - b.no), prev = ch.length ? ch[ch.length - 1] : null;
    const pc = prev ? calc(prev) : { dedCum: 0, byId: {} }, pd = prev ? (prev.data || {}) : {};
    let lines = Array.isArray(d.boq) && d.boq.length ? d.boq : null;
    if (!lines) { const b = boq.find(b => b.site_id === c.site_id && b.contractor === c.contractor && (b.item || '') === item(c)); lines = b && Array.isArray((b.data || {}).lines) ? b.data.lines : []; }
    const L = d.lines || {}, PL = pd.lines || {}; let works = 0; const byId = {};
    for (const l of lines) { if (l.kind === 'sec') continue; const v = L[l.id] || {}, pv = PL[l.id] || {}, ptot = pc.byId[l.id] != null ? pc.byId[l.id] : 0, tot = v.tot === '' || v.tot == null ? ptot : +v.tot; byId[l.id] = tot;
      const pct = v.pct == null || v.pct === '' ? (pv.pct == null ? 100 : +pv.pct) : +v.pct; works += r2(tot * num(l.rate) * pct / 100); }
    if (!lines.length && d.cum) works = num(d.cum); works = r2(works);
    const pct = d.ret_pct == null ? 5 : +d.ret_pct, ret = d.final ? 0 : r2(works * pct / 100);
    const mine = (Array.isArray(d.deds) ? d.deds : []).filter(x => x && num(x.amount)).map(x => num(x.amount)); if (!d.deds && num(d.other)) mine.push(num(d.other));
    const dedCum = r2(pc.dedCum + mine.reduce((a, b) => a + b, 0)), r = { after: r2(works - ret - dedCum), dedCum, byId };
    memo.set(c.id, r); return r;
  };
  return calc(c).after;
}
/* مستحقات موقع واحد: الموردين من فواتير المخزن، والمقاولين من آخر مستخلص معتمد */
export function siteDues({ siteId, moves, exps, certs, boq, kindOf }) {
  const ms = moves.filter(m => m.site_id === siteId && !m.deleted), ex = exps.filter(e => e.siteId === siteId), rows = [];
  const sup = new Map();
  for (const x of invoices(ms)) { if (!x.sup || x.pend || x.bad) continue; const k = norm(x.sup); const y = sup.get(k) || { name: x.sup, due: 0, n: 0 }; y.due += x.due; y.n++; sup.set(k, y); }
  for (const m of ms) if ((m.kind === 'ret' || m.kind === 'cn') && !(m.data || {}).supPend) { const k = norm((m.data || {}).supplier); const y = sup.get(k); if (y) y.due -= crVal(m); }
  /* «مقاول ومورد»: دفعاته على بنود مستخلصاته في الموقع بتتحسب كمقاول مش كمورد */
  const certItems = new Map(); for (const c of certs) if (c.site_id === siteId && c.status === 'approved') { const k = norm(c.contractor); if (!certItems.has(k)) certItems.set(k, new Set()); certItems.get(k).add(norm((c.data || {}).item || '')); }
  for (const [k, y] of sup) { const ci = certItems.get(k) || new Set(); const paid = r2(ex.filter(e => norm(e.contractor) === k && !ci.has(norm(e.item || ''))).reduce((a, e) => a + num(e.amount), 0)); rows.push({ name: y.name, kind: 'مورد', item: '', due: r2(y.due), paid, left: r2(y.due - paid), note: y.n === 1 ? 'فاتورة واحدة' : y.n === 2 ? 'فاتورتان' : y.n + ' فواتير' }); }
  const site = certs.filter(c => c.site_id === siteId), g = new Map();
  for (const c of site) { const k = c.contractor + '|' + String((c.data || {}).item || '').trim(); if (!g.has(k)) g.set(k, []); g.get(k).push(c); }
  for (const [k, L] of g) { const ap = L.filter(c => c.status === 'approved').sort((a, b) => b.no - a.no)[0]; if (!ap) continue; const it = String((ap.data || {}).item || '').trim();
    const due = certAfter(ap, certs, boq), paid = r2(ex.filter(e => norm(e.contractor) === norm(ap.contractor) && String(e.item || '').trim() === it).reduce((a, e) => a + num(e.amount), 0));
    rows.push({ name: ap.contractor, kind: kindOf(ap.contractor) === 'supplier' ? 'مورد' : 'مقاول', item: it, due, paid, left: r2(due - paid), note: 'مستخلص رقم ' + ap.no }); }
  return rows.sort((a, b) => b.left - a.left);
}
export function duesTable(rows, siteName) {
  if (!rows.length) return '';
  const T = k => fmt(rows.reduce((a, r) => a + r[k], 0));
  return `<h3 class="dues">المستحق للموردين والمقاولين — ${esc(siteName)}</h3><table><thead><tr><th>الاسم</th><th>النوع</th><th>البند</th><th>المصدر</th><th>المستحق</th><th>المدفوع</th><th>المتبقي</th></tr></thead><tbody>
  ${rows.map(r => `<tr><td class="tl b">${esc(r.name)}</td><td>${r.kind}</td><td class="tl">${esc(r.item || '—')}</td><td class="tl">${esc(r.note)}</td><td class="n">${fmt(r.due)}</td><td class="n">${fmt(r.paid)}</td><td class="n b">${r.left < 0 ? '(' + fmt(-r.left) + ') مقدم' : fmt(r.left)}</td></tr>`).join('')}
  <tr class="tot"><td colspan="4" class="tl">الإجمالي</td><td class="n">${T('due')}</td><td class="n">${T('paid')}</td><td class="n">${T('left')}</td></tr></tbody></table>`;
}
/* كشف مختصر لاسم واحد في مواقع معيّنة: الفواتير/المستخلصات والدفعات بالترتيب ورصيد متراكم */
export function shortStatement({ name, sites, moves, exps, certs, boq, siteName }) {
  const k = norm(name), ids = new Set(sites), rows = [];
  for (const x of invoices(moves.filter(m => ids.has(m.site_id)))) if (norm(x.sup) === k && !x.pend && !x.bad) rows.push({ d: x.date, t: (x.inv ? 'فاتورة رقم ' + x.inv : 'فاتورة مخزن') + (x.disc ? ' (خصم ' + fmt(x.disc) + ')' : '') + (x.tax ? ' (ضريبة ' + fmt(x.rate) + '%)' : ''), s: x.site, due: x.due, paid: 0 });
  for (const m of moves) if (ids.has(m.site_id) && !m.deleted && (m.kind === 'ret' || m.kind === 'cn') && norm((m.data || {}).supplier) === k) rows.push({ d: m.date, t: m.kind === 'ret' ? '↩ مرتجع' : '− إشعار خصم', s: m.site_id, due: -crVal(m), paid: 0 });
  const g = new Map(); for (const c of certs) if (ids.has(c.site_id) && norm(c.contractor) === k && c.status === 'approved') { const kk = c.site_id + '|' + String((c.data || {}).item || '').trim(); const o = g.get(kk); if (!o || c.no > o.no) g.set(kk, c); }
  for (const c of g.values()) rows.push({ d: (c.data || {}).date || '', t: 'آخر مستخلص معتمد رقم ' + c.no + ' — ' + String((c.data || {}).item || ''), s: c.site_id, due: certAfter(c, certs, boq), paid: 0 });
  for (const e of exps) if (ids.has(e.siteId) && norm(e.contractor) === k) rows.push({ d: e.date || '', t: 'دفعة' + (e.item ? ' — ' + e.item : '') + (e.notes ? ' · ' + e.notes : ''), s: e.siteId, due: 0, paid: num(e.amount) });
  if (!rows.length) return null;
  rows.sort((a, b) => a.d.localeCompare(b.d) || (b.due - a.due));
  let run = 0; const TD = r2(rows.reduce((a, r) => a + r.due, 0)), TP = r2(rows.reduce((a, r) => a + r.paid, 0));
  const body = `<table><thead><tr><th>التاريخ</th><th>البيان</th><th>الموقع</th><th>المستحق</th><th>المدفوع</th><th>الرصيد</th></tr></thead><tbody>${rows.map(r => { run = r2(run + r.due - r.paid); return `<tr><td class="n">${esc(r.d)}</td><td class="tl">${esc(r.t)}</td><td class="tl">${esc(siteName(r.s))}</td><td class="n">${r.due ? (r.due < 0 ? '(' + fmt(-r.due) + ')' : fmt(r.due)) : ''}</td><td class="n">${r.paid ? fmt(r.paid) : ''}</td><td class="n b">${fmt(run)}</td></tr>`; }).join('')}
  <tr class="tot"><td colspan="3" class="tl">الإجمالي</td><td class="n">${fmt(TD)}</td><td class="n">${fmt(TP)}</td><td class="n">${fmt(r2(TD - TP))}</td></tr></tbody></table>
  <p class="sub">المستحق للمقاول = «إجمالي الأعمال بعد الخصومات» في آخر مستخلص معتمد لكل بند. المستحق للمورد = صافي فواتير المخزن بالضريبة ناقص المرتجعات وإشعارات الخصم. المدفوع = المصروفات المسجّلة باسمه في الموقع.</p>`;
  return { body, due: TD, paid: TP, left: r2(TD - TP) };
}
