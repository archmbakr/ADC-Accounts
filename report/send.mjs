// ADC حسابات المواقع — تقرير التعديلات اليومي (يعمل على GitHub Actions)
// يقرأ البيانات من Supabase، ويرسل لكل مستخدم تعديلات مواقعه، وللمدير تعديلات كل المواقع،
// مع ملف Excel وملف PDF. لا يرسل شيئًا إذا لم توجد تعديلات.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { execFileSync } from 'node:child_process';
import { buildXlsx, buildHtml } from './statement.mjs';

const SB_URL = (process.env.SUPABASE_URL || '').replace(/\/$/, '');
const KEY = process.env.SUPABASE_SERVICE_KEY || '';
const FORCE = String(process.env.FORCE) === 'true';
const DRY = !!process.env.DRY_RUN;            // يكتب الملفات في مجلد out بدل الإرسال
const MOCK = process.env.MOCK_DATA || '';      // للاختبار المحلي فقط
const TZ = 'Africa/Cairo', HOUR = 22, REMIND_HOUR = 9, WEEKDAY = 4; // الخميس
const MODE = process.env.MODE || 'weekly';     // weekly = تقرير أسبوعي بالبريد · remind = تذكير الشيكات
const CUR = 'ج.م';
const HERE = path.dirname(new URL(import.meta.url).pathname);

const log = (...a) => console.log(...a);       // السجلات علنية: لا نطبع أي بيانات أو عناوين بريد
const die = m => { console.error(m); process.exit(1); };

/* ---------- الوقت بتوقيت القاهرة ---------- */
function cairo(d) {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })
    .formatToParts(d).filter(x => x.type !== 'literal').map(x => [x.type, x.value]));
  return { y: +p.year, m: +p.month, d: +p.day, h: +p.hour, mi: +p.minute, s: +p.second, day: `${p.year}-${p.month}-${p.day}`, hm: `${p.hour}:${p.minute}` };
}
function cairoInstant(y, m, d, h) {               // اللحظة التي تكون فيها الساعة h بتوقيت القاهرة
  let t = Date.UTC(y, m - 1, d, h);
  for (let i = 0; i < 2; i++) { const c = cairo(new Date(t)); const asUtc = Date.UTC(c.y, c.m - 1, c.d, c.h, c.mi, c.s); t += Date.UTC(y, m - 1, d, h) - asUtc; }
  return t;
}

/* ---------- Supabase ---------- */
const headers = () => KEY.startsWith('sb_') ? { apikey: KEY } : { apikey: KEY, Authorization: 'Bearer ' + KEY };
async function sbGet(q) {
  const out = [];
  for (let off = 0; ; off += 1000) {
    if (MOCK) break;
    const r = await fetch(`${SB_URL}/rest/v1/${q}${q.includes('?') ? '&' : '?'}offset=${off}&limit=1000`, { headers: headers() });
    if (!r.ok) die('قراءة البيانات فشلت: ' + r.status + ' ' + (await r.text()).slice(0, 200));
    const j = await r.json(); out.push(...j); if (j.length < 1000) break;
  }
  return out;
}
async function sbGetSoft(q) {
  const r = await fetch(`${SB_URL}/rest/v1/${q}`, { headers: headers() });
  return r.ok ? r.json() : [];
}
async function sbPut(pathKey, data) {
  const r = await fetch(`${SB_URL}/rest/v1/docs?on_conflict=path`, { method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json', Prefer: 'resolution=merge-duplicates' }, body: JSON.stringify({ path: pathKey, data }) });
  if (!r.ok) die('حفظ حالة الإرسال فشل: ' + r.status);
}
async function loadAll() {
  if (MOCK) return JSON.parse(fs.readFileSync(MOCK, 'utf8'));
  const [docs, members, owners] = await Promise.all([sbGet('docs?select=path,data&order=path'), sbGet('members?select=*'), sbGet('app_owner?select=email')]);
  let custody = [];
  try { custody = await sbGetSoft('custody?select=*'); } catch { }
  return { docs, members, owners, custody };
}

/* ---------- تجهيز البيانات ---------- */
const ACT = { add: 'إضافة', edit: 'تعديل', delete: 'حذف', import: 'استرجاع' };
const KIND = { expenses: 'مصروف', deposits: 'إيداع', counts: 'جرد', sites: 'موقع', files: 'من ملف', contractors: 'مقاول', items: 'بند' };
const num = v => (+v || 0);
const fmt = v => (v == null || v === '') ? '' : num(v).toLocaleString('en-US', { maximumFractionDigits: 2 });
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function group(docs) {
  const G = new Map();
  for (const { path: p, data } of docs) {
    const seg = p.split('/');
    let owner = '', rest = seg;
    if (seg[0] === 'u') { if (seg.length < 4) continue; owner = seg[1]; rest = seg.slice(2); }
    if (rest.length !== 2) continue;
    const [col, id] = rest;
    if (!G.has(owner)) G.set(owner, { sites: [], expenses: [], deposits: [], counts: [], log: [], push: [], contractors: [], items: [] });
    const g = G.get(owner);
    if (g[col]) g[col].push({ id, ...data });
  }
  return G;
}
function siteSummary(g) {
  return g.sites.map(s => {
    const dep = g.deposits.filter(x => x.siteId === s.id).reduce((a, x) => a + num(x.amount), 0);
    const exp = g.expenses.filter(x => x.siteId === s.id).reduce((a, x) => a + num(x.amount), 0);
    return { name: s.name || '', dep, exp, bal: dep - exp };
  }).sort((a, b) => a.name.localeCompare(b.name, 'ar'));
}
const rowOf = e => [cairo(new Date(e.at)).hm, ACT[e.action] || e.action || '', KIND[e.kind] || e.kind || '', e.siteName || '', e.amount == null ? '' : num(e.amount), e.date || '', e.details || '', e.by || ''];
const HEAD = ['الوقت', 'العملية', 'النوع', 'الموقع', 'المبلغ (' + CUR + ')', 'تاريخ الحركة', 'التفاصيل', 'بواسطة'];
function totals(list) {
  const t = { n: list.length, exp: 0, dep: 0 };
  for (const e of list) if (e.action === 'add') { if (e.kind === 'expenses') t.exp += num(e.amount); if (e.kind === 'deposits') t.dep += num(e.amount); }
  return t;
}

/* ---------- PDF (HTML يُطبع عبر Chrome) ---------- */
function logoUri() { try { return 'data:image/png;base64,' + fs.readFileSync(path.join(HERE, 'logo.png')).toString('base64'); } catch { return ''; } }
function chromeBin() {
  for (const c of [process.env.CHROME_BIN, 'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser'].filter(Boolean)) {
    try { execFileSync(c, ['--version'], { stdio: 'ignore' }); return c; } catch { }
  }
  die('لم أجد متصفح Chrome لإنشاء ملف PDF.');
}
function htmlToPdf(html) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'adc-'));
  const h = path.join(dir, 'r.html'), p = path.join(dir, 'r.pdf');
  fs.writeFileSync(h, html);
  execFileSync(chromeBin(), ['--headless=new', '--no-sandbox', '--disable-gpu', '--no-pdf-header-footer', '--print-to-pdf=' + p, 'file://' + h], { stdio: 'ignore', timeout: 90000 });
  return fs.readFileSync(p);
}

/* ---------- البريد ---------- */
let transport = null;
async function send(to, subject, html, files) {
  if (DRY) {
    const out = path.join(HERE, 'out'); fs.mkdirSync(out, { recursive: true });
    const tag = to.replace(/[^a-z0-9]/gi, '_');
    fs.writeFileSync(path.join(out, tag + '.html'), `<p>To: ${esc(to)}<br>Subject: ${esc(subject)}</p>` + html);
    for (const f of files) fs.writeFileSync(path.join(out, tag + '-' + f.filename), f.content);
    return;
  }
  if (!transport) {
    const nodemailer = (await import('nodemailer')).default;
    transport = nodemailer.createTransport({ host: process.env.SMTP_HOST || 'smtp.gmail.com', port: +(process.env.SMTP_PORT || 465), secure: true, auth: { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS } });
  }
  await transport.sendMail({ from: { name: 'ADC حسابات المواقع', address: process.env.SMTP_USER }, to, subject, html, attachments: files });
}
function mailBody(title, sub, week, lastMod) {
  const t = totals(week);
  return `<div dir="rtl" style="font-family:Tahoma,Arial,sans-serif;font-size:14px;color:#111;line-height:1.7">
  <h2 style="margin:0 0 6px">${esc(title)}</h2><p style="margin:0 0 10px;color:#444">${esc(sub)}</p>
  <p>تعديلات هذا الأسبوع: <b>${t.n}</b> · مصروفات أُضيفت: <b>${fmt(t.exp)} ${CUR}</b> · إيداعات أُضيفت: <b>${fmt(t.dep)} ${CUR}</b></p>
  <p>مرفق الكشف الكامل (Excel و PDF) حتى آخر تعديل بتاريخ <b dir="ltr">${esc(lastMod)}</b>، ومعه ملف نسخة احتياطية (JSON) يمكن استرجاع البيانات منه من «الإعدادات» ← «استرجاع من ملف».</p>
  <p style="color:#777;font-size:12px">رسالة آلية من تطبيق ADC حسابات المواقع.</p></div>`;
}
async function upload(key, buf, type) {
  if (MOCK || DRY) return;
  const r = await fetch(`${SB_URL}/storage/v1/object/reports/${key}`, { method: 'POST', headers: { ...headers(), 'Content-Type': type, 'x-upsert': 'true' }, body: buf });
  if (!r.ok) log('تعذّر حفظ نسخة الكشف للتطبيق: ' + r.status);
}
/* ---------- تذكير الشيكات الآجلة (إشعار على الهاتف قبل الاستحقاق بيوم) ---------- */
async function sbDel(pathKey) {
  if (MOCK || DRY) return;
  await fetch(`${SB_URL}/rest/v1/docs?path=eq.${encodeURIComponent(pathKey)}`, { method: 'DELETE', headers: headers() });
}
function addDaysStr(d, n) { const t = new Date(d + 'T12:00:00Z'); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(0, 10); }
async function remind(now, c) {
  if (!FORCE && c.h < REMIND_HOUR) { log('ليس وقت التذكير بعد.'); return; }
  const { docs, members, owners } = await loadAll();
  const state = docs.find(d => d.path === 'sys/remind');
  if (!FORCE && state && state.data && state.data.day === c.day) { log('تذكير اليوم أُرسل بالفعل.'); return; }
  const tomorrow = addDaysStr(c.day, 1), last = FORCE ? addDaysStr(c.day, 7) : tomorrow;
  const G = group(docs.filter(d => !d.path.startsWith('sys/')));
  const mem = new Map(members.map(m => [m.id, m]));
  const pushPaths = new Map();
  for (const d of docs) { const seg = d.path.split('/'); const i = seg.indexOf('push'); if (i >= 0 && i === seg.length - 2) pushPaths.set(d.data && d.data.sub && d.data.sub.endpoint, d.path); }
  const dueOf = g => {
    const sites = new Map(g.sites.map(s => [s.id, s.name]));
    return [...g.expenses.map(x => ({ ...x, k: 'exp' })), ...g.deposits.map(x => ({ ...x, k: 'dep' }))]
      .filter(x => x.method === 'deferred' && x.due && x.due >= tomorrow && x.due <= last)
      .map(x => ({ ...x, site: sites.get(x.siteId) || '' })).sort((a, b) => a.due.localeCompare(b.due));
  };
  const msgOf = (list, who) => {
    const tot = list.filter(x => x.k === 'exp').reduce((a, x) => a + num(x.amount), 0);
    const lines = list.slice(0, 4).map(x => `${x.site}: ${fmt(x.amount)} ${CUR}${x.k === 'dep' ? ' (وارد)' : ''}${x.contractor ? ' — ' + x.contractor : ''}${x.chq ? ' · شيك ' + x.chq : ''}`);
    if (list.length > 4) lines.push(`و${list.length - 4} شيكات أخرى`);
    return {
      title: (FORCE ? '[تجربة] ' : '') + (list.length === 1 ? 'تذكير: شيك يستحق ' : `تذكير: ${list.length} شيكات تستحق `) + (FORCE ? 'قريبًا' : 'غدًا ' + tomorrow),
      body: (who ? who + ' — ' : '') + lines.join('\n') + (tot ? `\nإجمالي المدفوع: ${fmt(tot)} ${CUR}` : ''),
      tag: 'adc-due-' + tomorrow, url: './'
    };
  };
  let wp = null;
  const push = async (subs, payload) => {
    for (const sub of subs) {
      if (!sub || !sub.endpoint) continue;
      if (DRY || MOCK) { const out = path.join(HERE, 'out'); fs.mkdirSync(out, { recursive: true }); fs.appendFileSync(path.join(out, 'push.log'), JSON.stringify({ to: sub.endpoint.slice(0, 40), ...payload }) + '\n'); sent++; continue; }
      if (!wp) {
        wp = (await import('web-push')).default;
        const ownerMail = (owners[0] && owners[0].email) || 'admin@example.com';
        wp.setVapidDetails('mailto:' + ownerMail, process.env.VAPID_PUBLIC_KEY, process.env.VAPID_PRIVATE_KEY);
      }
      try { await wp.sendNotification(sub, JSON.stringify(payload), { TTL: 86400 }); sent++; }
      catch (e) { if (e && (e.statusCode === 404 || e.statusCode === 410)) await sbDel(pushPaths.get(sub.endpoint)); else log('تعذّر إرسال إشعار: ' + (e && e.statusCode)); }
    }
  };
  let sent = 0, ownerAll = [];
  for (const [uid, g] of G) {
    const list = dueOf(g); if (!list.length) continue;
    const name = uid ? ((mem.get(uid) || {}).name || 'مستخدم') : '';
    ownerAll.push(...list.map(x => ({ ...x, site: x.site + (name ? ' (' + name + ')' : '') })));
    if (uid) { const m = mem.get(uid); if (m && m.approved) await push(g.push.map(p => p.sub), msgOf(list)); }
  }
  if (ownerAll.length) { ownerAll.sort((a, b) => a.due.localeCompare(b.due)); await push((G.get('') || { push: [] }).push.map(p => p.sub), msgOf(ownerAll)); }
  else log('لا توجد شيكات تستحق غدًا.');
  if (!FORCE && !MOCK) await sbPut('sys/remind', { day: c.day, at: Date.now(), sent });
  log('تم. عدد الإشعارات المرسلة: ' + sent);
}

/* ---------- التشغيل ---------- */
(async () => {
  if (!MOCK && (!SB_URL || !KEY)) die('بيانات Supabase غير موجودة في الإعدادات (Secrets).');
  if (MODE !== 'remind' && !DRY && (!process.env.SMTP_USER || !process.env.SMTP_PASS)) die('بيانات البريد غير موجودة في الإعدادات (Secrets).');
  const now = new Date(), c = cairo(now);
  let start, end, day = c.day;
  if (MODE === 'remind') return remind(now, c);
  const WEEK = 7 * 864e5;
  if (FORCE) { end = now.getTime(); start = end - WEEK; }
  else {
    const wd = new Date(Date.UTC(c.y, c.m - 1, c.d)).getUTCDay();
    if (wd !== WEEKDAY || c.h < HOUR) { log('ليس وقت التقرير الأسبوعي (' + c.hm + ' بتوقيت القاهرة).'); return; }
    end = cairoInstant(c.y, c.m, c.d, HOUR); start = end - WEEK;
  }
  const { docs, members, owners, custody = [] } = await loadAll();
  const state = docs.find(d => d.path === 'sys/report');
  if (!FORCE && state && state.data && state.data.day === day) { log('تقرير اليوم أُرسل بالفعل.'); return; }

  const G = group(docs.filter(d => !d.path.startsWith('sys/')));
  const mem = new Map(members.map(m => [m.id, m]));
  const uname = uid => uid ? ((mem.get(uid) || {}).name || 'مستخدم') : '';
  const today = c.day, stampNow = c.day + ' ' + c.hm;
  const inWeek = l => l.at > start && l.at <= end;
  const lastModOf = data => { let t = 0; for (const k of ['sites', 'expenses', 'deposits', 'counts']) for (const x of data[k]) t = Math.max(t, x.updated || 0, x.created || 0); for (const l of data.log) t = Math.max(t, l.at || 0); return t; };
  const stampOf = t => { const z = cairo(new Date(t)); return z.day + '_' + z.hm.replace(':', '-'); };
  const merge = (uids, tag) => {
    const out = { sites: [], expenses: [], deposits: [], counts: [], log: [], custody };
    for (const uid of uids) { const g = G.get(uid); if (!g) continue; const nm = tag ? uname(uid) : '';
      out.sites.push(...g.sites.map(s => ({ ...s, owner: nm }))); for (const k of ['expenses', 'deposits', 'counts', 'log']) out[k].push(...g[k]); }
    return out;
  };
  const sub = 'من ' + cairo(new Date(start)).day + ' إلى ' + cairo(new Date(end)).day + ' (بتوقيت القاهرة)';
  let sent = 0;
  const bakOf = (uid, at) => {                       // نسخة احتياطية بنفس صيغة «استرجاع من ملف» في التطبيق
    const g = G.get(uid) || {}, root = G.get('') || {}, L = k => g[k] || [];
    const shared = k => uid ? [...(root[k] || []), ...L(k)] : L(k);
    return Buffer.from(JSON.stringify({ app: 'ADC-site-accounts', version: 2, exportedAt: at, source: 'weekly-report', account: uid || 'owner', sites: L('sites'), expenses: L('expenses'), deposits: L('deposits'), counts: L('counts'), log: L('log'), contractors: shared('contractors'), items: shared('items') }));
  };
  const dumpOf = at => Buffer.from(JSON.stringify({ app: 'ADC-db-dump', version: 1, exportedAt: at, docs: docs.filter(d => !/(^|\/)push\//.test(d.path)), members, custody }));
  const deliver = async (to, folder, who, data, extra = []) => {
    const week = data.log.filter(inWeek).sort((a, b) => a.at - b.at);
    const lm = lastModOf(data), lastMod = lm ? stampOf(lm) : stampNow.replace(' ', '_').replace(':', '-');
    const title = 'كشف حساب كامل' + (who ? ' — ' + who : '');
    const html = buildHtml({ title, sub: sub + ' · آخر تعديل: ' + lastMod.replace('_', ' ').replace(/-(\d\d)$/, ':$1'), data, week, today, logo: logoUri() });
    const xlsx = Buffer.from(await buildXlsx({ title, data, week, today, stampNow, lastMod }).arrayBuffer());
    const pdf = htmlToPdf(html);
    const base = 'ADC-كشف-كامل-' + lastMod;
    await upload(`${folder}/${lastMod}.xlsx`, xlsx, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    await upload(`${folder}/${lastMod}.pdf`, pdf, 'application/pdf');
    const more = extra.map(x => ({ filename: x.name(lastMod), content: x.buf }));
    for (const x of extra) await upload(`${folder}/${lastMod}${x.suffix}`, x.buf, 'application/json');
    if (!week.length) return;                       // لا تعديلات هذا الأسبوع: لا يُرسل بريد
    await send(to, `${title} — ${week.length} تعديل هذا الأسبوع`, mailBody(title, sub, week, lastMod), [{ filename: base + '.xlsx', content: xlsx }, { filename: base + '.pdf', content: pdf }, ...more]);
    sent++;
  };
  const anyWeek = [...G.values()].some(g => g.log.some(inWeek));
  if (!anyWeek) log('لا توجد تعديلات هذا الأسبوع، لن يُرسل شيء.');
  else {
    for (const [uid] of G) {
      if (!uid) continue;
      const m = mem.get(uid);
      if (m && m.approved && m.email && m.role !== 'engineer') await deliver(m.email, uid, '', merge([uid], false), [{ suffix: '.json', buf: bakOf(uid, end), name: lm => 'ADC-نسخة-احتياطية-' + lm + '.json' }]);
    }
    for (const o of owners) if (o.email) await deliver(o.email, 'owner', 'كل المواقع', merge([...G.keys()], true), [
      { suffix: '.json', buf: bakOf('', end), name: lm => 'ADC-نسخة-احتياطية-' + lm + '.json' },
      { suffix: '-db.json', buf: dumpOf(end), name: lm => 'ADC-قاعدة-البيانات-كاملة-' + lm + '.json' }]);
  }
  if (!FORCE && !MOCK) await sbPut('sys/report', { day, at: Date.now(), sent });
  log('تم. عدد الرسائل المرسلة: ' + sent);
})().catch(e => die('حدث خطأ: ' + (e && e.message || e)));
