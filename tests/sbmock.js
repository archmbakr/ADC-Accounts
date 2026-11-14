/* ADC CONSTRUCTION — نسخة وهمية من Supabase للاختبارات (الدفعة 4، 14 نوفمبر 2026)
   بتتحط مكان مكتبة supabase-js وقت الاختبار بس (run.py بيبدّلها). البيانات في الذاكرة.
   الإعدادات قبل تحميل الصفحة (من run.py):
     window.__SEED   = { table: [rows...] }       البيانات الأولية
     window.__USER   = { id, email, name, owner }  المستخدم الداخل (owner = مدير)
     window.__RPC    = { name: (args, db) => data } دوال إضافية أو بديلة
     window.__MISSING= ['table', ...]               جداول تتعامل كأنها مش موجودة
   زي Supabase الحقيقي: أي طلب قراءة بيرجّع 1000 صف بالكتير (MAX_ROWS). */
(function () {
  'use strict';
  const MAX_ROWS = 1000;
  const PK = {
    docs: ['path'], members: ['id'], app_settings: ['key'], site_access: ['engineer', 'site_id'], cert_ret: ['owner_key', 'contractor'],
    store_sites: ['site_id'], store_access: ['person', 'site_id'], acct_sites: ['acct', 'site_id'], private_items: ['key'],
    notice_ignores: ['key'], edit_quota: ['uid', 'day'], entry_sites: ['site_id'], item_types: ['key'], adc_codes: ['key'],
    member_devices: ['user_id', 'device_id'], adc_migrations: ['name'], adc_usage_log: ['day']
  };
  const pkOf = t => PK[t] || ['id'];
  const clone = x => x == null ? x : JSON.parse(JSON.stringify(x));
  const DB = {};
  const seed = window.__SEED || {};
  for (const t in seed) DB[t] = clone(seed[t]);
  const tbl = t => (DB[t] = DB[t] || []);
  const LOG = window.__SBLOG = [];
  window.__DB = DB;
  const now = () => new Date().toISOString();
  const colOf = p => p.slice(0, p.lastIndexOf('/'));
  const get = (row, c) => {
    if (c.includes('->')) { const [a, ...rest] = c.split(/->>?/); let v = row[a]; for (const k of rest) v = v == null ? v : v[k]; return v; }
    return row[c];
  };
  const cmp = (a, b) => (a == null && b == null) ? 0 : a == null ? -1 : b == null ? 1 : (typeof a === 'number' && typeof b === 'number') ? a - b : String(a).localeCompare(String(b));
  const likeRe = (p, i) => new RegExp('^' + String(p).replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/%/g, '.*').replace(/_/g, '.') + '$', i ? 'i' : '');
  const OPS = {
    eq: (v, x) => String(v) === String(x), neq: (v, x) => String(v) !== String(x), gt: (v, x) => cmp(v, x) > 0, gte: (v, x) => cmp(v, x) >= 0,
    lt: (v, x) => cmp(v, x) < 0, lte: (v, x) => cmp(v, x) <= 0, like: (v, x) => likeRe(x).test(String(v ?? '')), ilike: (v, x) => likeRe(x, 1).test(String(v ?? '')),
    is: (v, x) => x === null ? v == null : v === x, in: (v, x) => (Array.isArray(x) ? x : String(x).replace(/^\(|\)$/g, '').split(',')).map(String).includes(String(v))
  };
  function err(message, code) { return { data: null, error: { message, code: code || 'PGRST000', details: '', hint: '' }, status: 400 }; }

  class Q {
    constructor(t) { this.t = t; this.op = 'select'; this.f = []; this.o = []; this.rg = null; this.lim = null; this.one = 0; this.ret = false; }
    select(cols, opt) { if (this.op === 'select') { this.cols = cols; this.cnt = opt && opt.count; } else this.ret = true; return this; }
    insert(rows, opt) { this.op = 'insert'; this.p = rows; this.opt = opt || {}; return this; }
    upsert(rows, opt) { this.op = 'upsert'; this.p = rows; this.opt = opt || {}; return this; }
    update(v) { this.op = 'update'; this.p = v; return this; }
    delete() { this.op = 'delete'; return this; }
    _f(c, op, v) { this.f.push([c, op, v]); return this; }
    eq(c, v) { return this._f(c, 'eq', v); } neq(c, v) { return this._f(c, 'neq', v); } gt(c, v) { return this._f(c, 'gt', v); } gte(c, v) { return this._f(c, 'gte', v); }
    lt(c, v) { return this._f(c, 'lt', v); } lte(c, v) { return this._f(c, 'lte', v); } like(c, v) { return this._f(c, 'like', v); } ilike(c, v) { return this._f(c, 'ilike', v); }
    is(c, v) { return this._f(c, 'is', v); } in(c, v) { return this._f(c, 'in', v); }
    filter(c, op, v) { return this._f(c, op, v); }
    not(c, op, v) { this.f.push([c, op, v, true]); return this; }
    match(o) { for (const k in o) this.eq(k, o[k]); return this; }
    or() { return this; } contains() { return this; } textSearch() { return this; }
    order(c, o) { this.o.push([c, !o || o.ascending !== false]); return this; }
    range(a, b) { this.rg = [a, b]; return this; }
    limit(n) { this.lim = n; return this; }
    single() { this.one = 1; return this; }
    maybeSingle() { this.one = 2; return this; }
    abortSignal() { return this; }
    _match(r) { return this.f.every(([c, op, v, neg]) => { const fn = OPS[op]; const ok = fn ? fn(get(r, c), v) : true; return neg ? !ok : ok; }); }
    _key(r) { return pkOf(this.t).map(k => String(r[k])).join('|'); }
    _run() {
      const t = this.t; LOG.push({ t, op: this.op, f: this.f.map(x => x.slice(0, 3)), rg: this.rg, lim: this.lim });
      if ((window.__MISSING || []).includes(t)) return err('relation "public.' + t + '" does not exist', '42P01');
      const T = tbl(t);
      if (this.op === 'select') {
        let L = T.filter(r => this._match(r));
        for (const [c, asc] of this.o.slice().reverse()) L = L.slice().sort((a, b) => (asc ? 1 : -1) * cmp(get(a, c), get(b, c)));
        const count = L.length;
        if (this.rg) L = L.slice(this.rg[0], this.rg[1] + 1);
        if (this.lim != null) L = L.slice(0, this.lim);
        L = L.slice(0, MAX_ROWS).map(clone);
        if (this.one) { if (L.length > 1 && this.one === 1) return err('multiple rows'); if (!L.length && this.one === 1) return err('no rows', 'PGRST116'); return { data: L[0] || null, error: null, status: 200 }; }
        return { data: L, error: null, count: this.cnt ? count : null, status: 200 };
      }
      if (this.op === 'insert' || this.op === 'upsert') {
        const rows = (Array.isArray(this.p) ? this.p : [this.p]).map(clone), out = [];
        const keys = this.op === 'upsert' && this.opt.onConflict ? this.opt.onConflict.split(',').map(s => s.trim()) : pkOf(t);
        for (const r of rows) {
          if (t === 'docs' && r.path && r.col == null) r.col = colOf(r.path);
          if (!('updated_at' in r)) r.updated_at = now();
          if (pkOf(t)[0] === 'id' && r.id == null) r.id = 'm' + Math.random().toString(36).slice(2, 10);
          const k = keys.map(x => String(r[x])).join('|'), i = T.findIndex(x => keys.map(y => String(x[y])).join('|') === k);
          if (i >= 0) { if (this.op === 'insert') return err('duplicate key value violates unique constraint', '23505'); if (this.opt.ignoreDuplicates) continue; T[i] = { ...T[i], ...r }; out.push(clone(T[i])); }
          else { T.push(r); out.push(clone(r)); }
        }
        return { data: this.ret ? (this.one ? out[0] : out) : null, error: null, status: 201 };
      }
      if (this.op === 'update') {
        const out = [];
        for (let i = 0; i < T.length; i++) if (this._match(T[i])) { T[i] = { ...T[i], ...clone(this.p), updated_at: now() }; out.push(clone(T[i])); }
        return { data: this.ret ? (this.one ? out[0] || null : out) : null, error: null, status: 200 };
      }
      if (this.op === 'delete') {
        const out = T.filter(r => this._match(r)); DB[t] = T.filter(r => !this._match(r));
        return { data: this.ret ? out.map(clone) : null, error: null, status: 200 };
      }
      return err('unknown op');
    }
    then(res, rej) { return new Promise(r => setTimeout(r, window.__SBDELAY || 0)).then(() => this._run()).then(res, rej); }
  }

  const U = window.__USER || { id: 'u-owner', email: 'owner@test.local', name: 'المدير', owner: true };
  const session = { access_token: 'test', user: { id: U.id, email: U.email, user_metadata: { name: U.name } } };
  const day = () => new Date(Date.now() + 2 * 3600e3).toISOString().slice(0, 10);
  const RPC = {
    am_owner: () => !!U.owner,
    device_hello: () => 'ok',
    owners_list: () => (window.__OWNERS || [U.owner ? U.email : 'owner@test.local']),
    storage_usage: () => ({ db: 40 * 1048576, files: 120 * 1048576, buckets: { receipts: 100 * 1048576 } }),
    usage_detail: () => ({ db: 40 * 1048576, files: 120 * 1048576, buckets: {}, tables: [{ name: 'docs', rows: 1200, bytes: 9e6 }, { name: 'custody', rows: 300, bytes: 2e6 }], log: [{ day: day(), db: 40 * 1048576, files: 120 * 1048576 }], day: day() }),
    quota_left: () => 10,
    cert_paid_rows: () => [], site_items: () => [], site_regs: () => [], tech_item_groups: () => [], acct_private_totals: () => [],
    codes_alloc: () => null, custody_sync: () => null
  };
  const auth = {
    getSession: async () => ({ data: { session }, error: null }),
    getUser: async () => ({ data: { user: session.user }, error: null }),
    onAuthStateChange: () => ({ data: { subscription: { unsubscribe() { } } } }),
    signInWithPassword: async () => ({ data: { session, user: session.user }, error: null }),
    signUp: async () => ({ data: { session, user: session.user }, error: null }),
    signOut: async () => ({ error: null }), updateUser: async () => ({ data: { user: session.user }, error: null }),
    resetPasswordForEmail: async () => ({ data: {}, error: null })
  };
  const storage = { from: b => ({
    upload: async p => ({ data: { path: p }, error: null }), download: async () => ({ data: new Blob(['x'], { type: 'image/png' }), error: null }),
    createSignedUrl: async () => ({ data: { signedUrl: 'data:image/png;base64,' }, error: null }), list: async () => ({ data: [], error: null }), remove: async () => ({ data: [], error: null })
  }) };
  function createClient(url, key, opts) {
    window.__SBOPTS = opts || {};
    return {
      from: t => new Q(t), auth, storage,
      rpc: (name, args) => ({ then(res, rej) { return Promise.resolve().then(() => {
        LOG.push({ rpc: name, args });
        const fn = (window.__RPC || {})[name] || RPC[name];
        if (!fn) return err('Could not find the function public.' + name + ' in the schema cache', 'PGRST202');
        try { return { data: fn(args || {}, DB), error: null, status: 200 }; } catch (e) { return err(String(e && e.message || e)); }
      }).then(res, rej); } }),
      channel: () => { const ch = { on() { return ch; }, subscribe(cb) { if (cb) setTimeout(() => cb('SUBSCRIBED'), 0); return ch; }, unsubscribe() { return Promise.resolve('ok'); }, send() { return Promise.resolve('ok'); } }; return ch; },
      removeChannel: () => Promise.resolve('ok'), removeAllChannels: () => Promise.resolve([]),
      functions: { invoke: async () => ({ data: null, error: null }) }
    };
  }
  window.supabase = { createClient };
})();
