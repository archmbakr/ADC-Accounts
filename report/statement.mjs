// الكشف الكامل: ملف Excel وصفحة HTML (تُطبع PDF) لمجموعة مواقع
import { XLSX_W } from './xlsx.mjs';

export const CUR = 'ج.م';
const METHOD = { cash: 'نقدي', bank: 'بنك', transfer: 'تحويل', deferred: 'آجل (شيك)', custody: 'من العهدة' };
const ACT = { add: 'إضافة', edit: 'تعديل', delete: 'حذف', import: 'استرجاع' };
const KIND = { expenses: 'مصروف', deposits: 'إيداع', counts: 'جرد', sites: 'موقع', files: 'من ملف', contractors: 'مقاول', items: 'بند' };
const ST = { none: 'لم يتم الجرد', ok: 'مطابق', short: 'عجز', over: 'زيادة' };
const num = v => (+v || 0);
export const fmt = v => (v == null || v === '') ? '' : num(v).toLocaleString('en-US', { maximumFractionDigits: 2 });
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const sum = l => l.reduce((a, x) => a + num(x.amount), 0);
const meth = x => METHOD[x.method] && x.method !== 'cash' ? x.method : 'cash';
const notDue = (x, d) => x.method === 'deferred' && (x.due || '') > d;
const mlabel = (x, today) => METHOD[meth(x)] + (['bank', 'transfer', 'deferred'].includes(x.method) && x.bank ? ' · ' + x.bank : '') + (x.method === 'deferred' && x.due ? ' · ' + (notDue(x, today) ? 'يستحق ' : 'استُحق ') + x.due + (x.chq ? ' · شيك ' + x.chq : '') : '');
const byDate = (a, b) => (a.date || '').localeCompare(b.date || '') || (a.created || 0) - (b.created || 0);

/* data = { sites, expenses, deposits, counts, log } كل موقع فيه owner (اسم المستخدم) اختياري */
export function computeSites(data, today) {
  return data.sites.map(s => {
    const e = data.expenses.filter(x => x.siteId === s.id), d = data.deposits.filter(x => x.siteId === s.id);
    const ec = sum(e.filter(x => meth(x) === 'cash')), ed = sum(e.filter(x => notDue(x, today))), eu = sum(e.filter(x => x.method === 'custody')), eb = sum(e) - ec - ed - eu;
    const cu = (data.custody || []).filter(r => r.site_id === s.id && r.kind !== 'claim');
    const iC = cu.filter(r => r.kind === 'issue' && (r.data || {}).source !== 'bank').reduce((a, r) => a + num(r.data.amount), 0), iB = cu.filter(r => r.kind === 'issue' && (r.data || {}).source === 'bank').reduce((a, r) => a + num(r.data.amount), 0), rt = cu.filter(r => r.kind === 'return').reduce((a, r) => a + num(r.data.amount), 0);
    const dc = sum(d.filter(x => meth(x) === 'cash')), dd = sum(d.filter(x => notDue(x, today))), db = sum(d) - dc - dd;
    const cs = data.counts.filter(c => c.siteId === s.id).sort((a, b) => (b.date || '').localeCompare(a.date || '') || (b.created || 0) - (a.created || 0));
    let rc = { st: 'none' };
    if (cs[0]) {
      const c = cs[0], dt = c.date || '';
      const e2 = e.filter(x => (x.date || '') <= dt), d2 = d.filter(x => (x.date || '') <= dt);
      const ec2 = sum(e2.filter(x => meth(x) === 'cash')), dc2 = sum(d2.filter(x => meth(x) === 'cash'));
      const ed2 = sum(e2.filter(x => notDue(x, dt))), dd2 = sum(d2.filter(x => notDue(x, dt)));
      const bookCash = dc2 - ec2, bookBank = (sum(d2) - dc2 - dd2) - (sum(e2) - ec2 - ed2);
      const diff = (num(c.cash) + num(c.bank)) - (bookCash + bookBank);
      rc = { st: Math.abs(diff) < 0.005 ? 'ok' : diff < 0 ? 'short' : 'over', date: dt, actual: num(c.cash) + num(c.bank), diff };
    }
    return { id: s.id, name: s.name || '', owner: s.owner || '', dep: dc + db + dd, exp: ec + eb + ed + eu, cash: dc - ec - iC + rt, bank: db - eb - iB, defer: dd - ed, cust: iC + iB - rt - eu, total: dc + db + dd - ec - eb - ed - eu, rc };
  }).sort((a, b) => (a.owner || '').localeCompare(b.owner || '', 'ar') || a.name.localeCompare(b.name, 'ar'));
}
const siteLabel = s => s.name + (s.owner ? ' (' + s.owner + ')' : '');

export function buildXlsx({ title, data, week, today, stampNow, lastMod }) {
  const sites = computeSites(data, today), names = new Map(data.sites.map(s => [s.id, siteLabel(s)]));
  const nm = id => names.get(id) || '';
  const sh = (name, widths) => ({ name, rows: [], styles: {}, widths, freeze: 1 });
  const H = (s, r) => { s.rows.push(r); s.styles[s.rows.length - 1] = 1; };
  const T = (s, r) => { s.rows.push(r); s.styles[s.rows.length - 1] = 3; };
  const dt = t => t ? new Date(t).toLocaleString('sv-SE', { timeZone: 'Africa/Cairo' }).slice(0, 16) : '';
  const s1 = { name: 'الملخص', rows: [], styles: {}, widths: [30, 14, 14, 14, 13, 13, 14, 13, 14, 14], freeze: 0 };
  s1.rows.push([title]); s1.styles[0] = 3; s1.rows.push(['آخر تعديل: ' + lastMod + ' · تاريخ الكشف: ' + stampNow]); s1.rows.push([]);
  H(s1, ['الموقع', 'الإيداعات', 'المصروفات', 'الرصيد الدفتري', 'نقدي', 'بنك وتحويلات', 'شيكات لم تُستحق', 'آخر جرد', 'الموجود فعلًا', 'الحالة']);
  for (const s of sites) s1.rows.push([siteLabel(s), s.dep, s.exp, s.total, s.cash, s.bank, s.defer, s.rc.date || '', s.rc.st === 'none' ? '' : s.rc.actual, ST[s.rc.st] + (s.rc.st === 'short' || s.rc.st === 'over' ? ' ' + fmt(Math.abs(s.rc.diff)) : '')]);
  if (sites.length > 1) T(s1, ['الإجمالي', ...['dep', 'exp', 'total', 'cash', 'bank', 'defer'].map(k => sites.reduce((a, s) => a + s[k], 0))]);
  const wk = sh('تعديلات الأسبوع', [17, 9, 9, 26, 13, 12, 50, 14]);
  H(wk, ['التاريخ والوقت', 'العملية', 'النوع', 'الموقع', 'المبلغ', 'تاريخ الحركة', 'التفاصيل', 'بواسطة']);
  for (const l of week) wk.rows.push([dt(l.at), ACT[l.action] || l.action || '', KIND[l.kind] || l.kind || '', l.siteName || '', l.amount == null ? '' : num(l.amount), l.date || '', l.details || '', l.by || '']);
  const rows = [...data.deposits.map(x => ({ ...x, k: 'dep' })), ...data.expenses.map(x => ({ ...x, k: 'exp' }))].sort(byDate);
  const jr = sh('دفتر اليومية', [12, 26, 10, 13, 13, 28, 18, 22, 22, 20, 14, 14]);
  H(jr, ['التاريخ', 'الموقع', 'النوع', 'وارد', 'منصرف', 'البيان', 'البند', 'المقاول', 'ملاحظات', 'طريقة الدفع', 'الرصيد', 'المسجل']);
  { let run = 0, ti = 0, to = 0; for (const r of rows) { const v = num(r.amount); if (r.k === 'dep') { run += v; ti += v; } else { run -= v; to += v; } jr.rows.push([r.date || '', nm(r.siteId), r.k === 'dep' ? 'إيداع' : 'مصروف', r.k === 'dep' ? v : '', r.k === 'exp' ? v : '', r.notes || (r.k === 'dep' ? 'إيداع من المالك' : ''), r.item || '', r.contractor || '', r.remarks || '', mlabel(r, today), run, r.by || '']); } T(jr, ['', '', 'الإجمالي', ti, to, '', '', '', '', '', run]); }
  const ex = sh('المصروفات', [13, 26, 12, 18, 22, 22, 22, 26, 14, 17]);
  H(ex, ['المبلغ', 'البيان', 'التاريخ', 'البند', 'المقاول', 'ملاحظات', 'طريقة الدفع', 'الموقع', 'المسجل', 'وقت التسجيل']);
  const el = data.expenses.slice().sort(byDate); for (const r of el) ex.rows.push([num(r.amount), r.notes || '', r.date || '', r.item || '', r.contractor || '', r.remarks || '', mlabel(r, today), nm(r.siteId), r.by || '', dt(r.created)]); T(ex, [sum(el), 'الإجمالي']);
  const dp = sh('الإيداعات', [13, 28, 12, 22, 24, 26, 14, 17]);
  H(dp, ['المبلغ', 'البيان', 'التاريخ', 'أُودع في', 'ملاحظات', 'الموقع', 'المسجل', 'وقت التسجيل']);
  const dl = data.deposits.slice().sort(byDate); for (const r of dl) dp.rows.push([num(r.amount), r.notes || 'إيداع من المالك', r.date || '', mlabel(r, today), r.remarks || '', nm(r.siteId), r.by || '', dt(r.created)]); T(dp, [sum(dl), 'الإجمالي']);
  const ct = sh('الجرد', [26, 12, 14, 14, 24, 17]);
  H(ct, ['الموقع', 'تاريخ الجرد', 'نقدي موجود', 'في البنك', 'ملاحظات', 'وقت التسجيل']);
  for (const c of data.counts.slice().sort(byDate)) ct.rows.push([nm(c.siteId), c.date || '', num(c.cash), num(c.bank), c.notes || '', dt(c.created)]);
  const lg = sh('سجل التعديلات', [17, 9, 9, 24, 13, 12, 50, 14]);
  H(lg, ['التاريخ والوقت', 'العملية', 'النوع', 'الموقع', 'المبلغ', 'تاريخ الحركة', 'التفاصيل', 'بواسطة']);
  for (const l of data.log.slice().sort((a, b) => (b.at || 0) - (a.at || 0))) lg.rows.push([dt(l.at), ACT[l.action] || l.action || '', KIND[l.kind] || l.kind || '', l.siteName || '', l.amount == null ? '' : num(l.amount), l.date || '', l.details || '', l.by || '']);
  return XLSX_W.build([s1, wk, jr, ex, dp, ct, lg]);
}

export function buildHtml({ title, sub, data, week, today, logo }) {
  const sites = computeSites(data, today);
  const dt = t => new Date(t).toLocaleString('sv-SE', { timeZone: 'Africa/Cairo' }).slice(0, 16);
  const neg = v => v < -0.004 ? ' neg' : '';
  const sumT = `<table><thead><tr><th>الموقع</th><th>الإيداعات</th><th>المصروفات</th><th>الرصيد الدفتري</th><th>نقدي</th><th>بنك وتحويلات</th><th>شيكات لم تُستحق</th><th>آخر جرد</th><th>الحالة</th></tr></thead><tbody>
  ${sites.map(s => `<tr class="${s.rc.st === 'short' ? 'bad' : ''}"><td class="tl">${esc(siteLabel(s))}</td><td class="n">${fmt(s.dep)}</td><td class="n">${fmt(s.exp)}</td><td class="n b${neg(s.total)}">${fmt(s.total)}</td><td class="n${neg(s.cash)}">${fmt(s.cash)}</td><td class="n${neg(s.bank)}">${fmt(s.bank)}</td><td class="n">${s.defer ? fmt(s.defer) : '—'}</td><td>${esc(s.rc.date || '—')}</td><td>${ST[s.rc.st]}${s.rc.st === 'short' || s.rc.st === 'over' ? ' ' + fmt(Math.abs(s.rc.diff)) : ''}</td></tr>`).join('')}
  </tbody>${sites.length > 1 ? `<tfoot><tr><td>الإجمالي</td>${['dep', 'exp', 'total', 'cash', 'bank', 'defer'].map(k => `<td class="n">${fmt(sites.reduce((a, s) => a + s[k], 0))}</td>`).join('')}<td colspan="2"></td></tr></tfoot>` : ''}</table>`;
  const wkT = week.length ? `<h2>تعديلات الأسبوع (${week.length})</h2><table><thead><tr><th>الوقت</th><th>العملية</th><th>النوع</th><th>الموقع</th><th>المبلغ</th><th>تاريخ الحركة</th><th>التفاصيل</th><th>بواسطة</th></tr></thead><tbody>
  ${week.map(l => `<tr><td class="n">${esc(dt(l.at))}</td><td><span class="a a-${esc(l.action)}">${esc(ACT[l.action] || l.action || '')}</span></td><td>${esc(KIND[l.kind] || l.kind || '')}</td><td class="tl">${esc(l.siteName || '')}</td><td class="n">${l.amount == null ? '' : fmt(l.amount)}</td><td class="n">${esc(l.date || '')}</td><td class="tl d">${esc(l.details || '')}</td><td>${esc(l.by || '')}</td></tr>`).join('')}</tbody></table>` : '<h2>تعديلات الأسبوع</h2><p>لا توجد تعديلات هذا الأسبوع.</p>';
  const stmt = s => {
    const rows = [...data.deposits.filter(x => x.siteId === s.id).map(x => ({ ...x, k: 'dep' })), ...data.expenses.filter(x => x.siteId === s.id).map(x => ({ ...x, k: 'exp' }))].sort(byDate);
    let run = 0, ti = 0, to = 0;
    const tr = rows.map(r => { const v = num(r.amount); if (r.k === 'dep') { run += v; ti += v; } else { run -= v; to += v; }
      return `<tr><td class="n">${esc(r.date || '')}</td><td class="n in">${r.k === 'dep' ? fmt(v) : ''}</td><td class="n">${r.k === 'exp' ? fmt(v) : ''}</td><td class="tl">${esc(r.notes || (r.k === 'dep' ? 'إيداع من المالك' : ''))}</td><td>${esc(r.item || '')}</td><td class="tl">${esc(r.contractor || '')}</td><td class="d">${esc(mlabel(r, today))}</td><td class="n b${neg(run)}">${fmt(run)}</td></tr>`; }).join('');
    return `<section class="site"><h2>كشف حساب: ${esc(siteLabel(s))}</h2><table><thead><tr><th>التاريخ</th><th>وارد</th><th>منصرف</th><th>البيان</th><th>البند</th><th>المقاول</th><th>طريقة الدفع</th><th>الرصيد</th></tr></thead><tbody>${tr || '<tr><td colspan="8">لا توجد حركات</td></tr>'}</tbody><tfoot><tr><td>الإجمالي</td><td class="n">${fmt(ti)}</td><td class="n">${fmt(to)}</td><td colspan="4"></td><td class="n">${fmt(run)}</td></tr></tfoot></table></section>`;
  };
  return `<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>${esc(title)}</title><style>
  @page{size:A4 landscape;margin:12mm 10mm}*{box-sizing:border-box}
  body{margin:0;font-family:"Noto Naskh Arabic","Noto Sans Arabic","Amiri","DejaVu Sans",Tahoma,Arial,sans-serif;font-size:10.5px;color:#111}
  .hd{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid #111;padding-bottom:8px;margin-bottom:8px}.hd img{height:46px}
  h1{margin:0;font-size:18px}h2{font-size:13px;margin:14px 0 5px;padding:4px 8px;background:#e9ecef;border-radius:4px}.sub{margin:0 0 8px;color:#333}
  table{width:100%;border-collapse:collapse;margin-bottom:6px}thead{display:table-header-group}tfoot{display:table-row-group}tr{page-break-inside:avoid}
  th,td{border:1px solid #999;padding:3px 5px;text-align:center;vertical-align:top}th{background:#1d5c86;color:#fff;font-size:10px}
  td.tl{text-align:right}td.d{font-size:9.5px}td.n{direction:ltr;white-space:nowrap}td.b{font-weight:bold}td.in{color:#185c2e}.neg{color:#b3261e}
  tr.bad td{background:#f6dcdc}tfoot td{background:#eee;font-weight:bold}
  .a{padding:1px 6px;border-radius:8px;font-size:9.5px}.a-add{background:#dcefe0}.a-edit{background:#fff1cc}.a-delete{background:#f6dcdc}
  section.site{page-break-before:always}.foot{margin-top:12px;font-size:9px;color:#666}
  </style></head><body>
  <div class="hd"><div><h1>${esc(title)}</h1></div>${logo ? `<img src="${logo}" alt="ADC">` : ''}</div>
  <p class="sub">${esc(sub)} · المبالغ بالجنيه المصري</p>
  <h2>ملخص المواقع</h2>${sumT}${wkT}${sites.map(stmt).join('')}
  <p class="foot">ADC Construction · حسابات المواقع · كشف آلي</p></body></html>`;
}
