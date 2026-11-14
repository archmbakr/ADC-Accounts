#!/usr/bin/env python3
"""ADC CONSTRUCTION — ملف الاختبارات الثابت (الدفعة 4، 14 نوفمبر 2026)

بيفتح التطبيق (index.html) في Chromium ببيانات وهمية (tests/sbmock.js بدل Supabase)
ويجرّب كل الصفحات بأدوار مختلفة. أي خطأ JavaScript أو صفحة فاضية = فشل.

التشغيل (من جذر المستودع):
    pip install playwright && python -m playwright install chromium
    python tests/run.py                # كل الاختبارات
    python tests/run.py owner limits   # اختبارات بالاسم
متغيرات اختيارية: CHROME=/path/to/chrome  ·  APP=path/to/index.html
"""
import functools, http.server, json, os, sys, threading, time, traceback
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = os.environ.get('APP', 'index.html')
MOCK = (Path(__file__).resolve().parent / 'sbmock.js').read_text(encoding='utf-8')
SB_CDN = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.js'
TODAY = date.today()
d = lambda n: (TODAY - timedelta(days=n)).isoformat()

# ---------------- البيانات الوهمية ----------------
def doc(path, data):
    return {'path': path, 'col': path.rsplit('/', 1)[0], 'data': data, 'updated_at': '2026-11-01T00:00:00Z'}

def base_seed(n_cust=0, n_certs=0, eng='u-eng', tech='u-tech'):
    docs = [doc('sites/s1', {'name': 'موقع الاختبار 1', 'created': 1}), doc('sites/s2', {'name': 'موقع الاختبار 2', 'created': 2})]
    docs += [doc('contractors/c1', {'name': 'مقاول أحمد', 'kind': 'contractor', 'created': 1}), doc('contractors/c2', {'name': 'مورد الحديد', 'kind': 'supplier', 'created': 2})]
    docs += [doc('items/i1', {'name': 'أعمال السباكة', 'created': 1}), doc('items/i2', {'name': 'توريدات حديد', 'created': 2})]
    for i in range(60):
        docs.append(doc(f'expenses/e{i}', {'siteId': 's1' if i % 3 else 's2', 'amount': 1000 + i, 'date': d(i % 40 + 1), 'item': 'أعمال السباكة' if i % 2 else 'توريدات حديد',
                                           'contractor': 'مقاول أحمد' if i % 2 else 'مورد الحديد', 'method': 'cash', 'notes': f'مصروف {i}', 'created': 1000 + i}))
    for i in range(6):
        docs.append(doc(f'deposits/k{i}', {'siteId': 's1' if i % 2 else 's2', 'amount': 50000, 'date': d(i * 7 + 1), 'method': 'bank', 'notes': 'إيداع من المالك', 'created': 900 + i}))
    members = [
        {'id': eng, 'email': 'eng@test.local', 'name': 'م. محمود', 'role': 'engineer', 'approved': True, 'created_at': '2026-10-01T00:00:00Z'},
        {'id': tech, 'email': 'tech@test.local', 'name': 'م. سارة', 'role': 'tech', 'approved': True, 'created_at': '2026-10-01T00:00:00Z'},
        {'id': 'u-eng2', 'email': 'eng2@test.local', 'name': 'م. كريم', 'role': 'engineer', 'approved': True, 'created_at': '2026-10-01T00:00:00Z'},
    ]
    cust = []
    for i in range(n_cust):
        e, en = (eng, 'م. محمود') if i % 2 == 0 else ('u-eng2', 'م. كريم')
        s, sn = ('s1', 'موقع الاختبار 1') if i % 3 else ('s2', 'موقع الاختبار 2')
        kind = 'issue' if i % 10 == 0 else 'claim'
        cust.append({'id': f'c{i:05d}', 'kind': kind, 'engineer': e, 'manager': None, 'site_id': s, 'status': 'ok' if kind == 'issue' else ('approved' if i % 7 else 'rejected'),
                     'created_by': e, 'updated_at': f'2026-11-{1 + i % 13:02d}T{i % 24:02d}:00:00Z',
                     'data': {'amount': 500 + i, 'date': d(i % 60 + 1), 'notes': f'حركة عهدة {i}', 'siteName': sn, 'engName': en, 'item': 'أعمال السباكة', 'method': 'cash', 'at': 1000 + i}})
    certs = []
    for i in range(n_certs):
        certs.append({'id': f't{i:04d}', 'site_id': 's1' if i % 2 else 's2', 'contractor': 'مقاول أحمد', 'no': i + 1, 'status': 'approved' if i % 5 else 'submitted',
                      'created_by': tech, 'updated_at': '2026-11-01T00:00:00Z',
                      'data': {'date': d(i % 50 + 1), 'siteName': 'موقع الاختبار 1' if i % 2 else 'موقع الاختبار 2', 'item': f'بند {i % 4}', 'lines': [{'name': 'بند', 'unit': 'م2', 'qty': 10 + i, 'price': 100}]}})
    access = [{'engineer': eng, 'site_id': 's1', 'site_owner': None, 'site_name': 'موقع الاختبار 1'}, {'engineer': tech, 'site_id': 's1', 'site_owner': None, 'site_name': 'موقع الاختبار 1'},
              {'engineer': tech, 'site_id': 's2', 'site_owner': None, 'site_name': 'موقع الاختبار 2'}]
    return {'docs': docs, 'members': members, 'custody': cust, 'certs': certs, 'site_access': access, 'app_settings': [], 'adc_migrations': []}

OWNER = {'id': 'u-owner', 'email': 'owner@test.local', 'name': 'المدير', 'owner': True}
ENG = {'id': 'u-eng', 'email': 'eng@test.local', 'name': 'م. محمود', 'owner': False}
TECH = {'id': 'u-tech', 'email': 'tech@test.local', 'name': 'م. سارة', 'owner': False}
PAGES = ['__all', 's1', '__journal', '__contractors', '__items', '__custody', '__certs', '__store', '__stmts', '__codes', '__trash', '__ocert', '__search', '__settings']

# ---------------- التشغيل ----------------
class Fail(Exception):
    pass

def serve():
    class H(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    h = functools.partial(H, directory=str(ROOT))
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv

class App:
    def __init__(self, browser, port, seed, user, rpc_js='', width=1280):
        self.errs = []
        self.ctx = browser.new_context(viewport={'width': width, 'height': 900}, service_workers='block', locale='ar-EG')
        init = f"window.__SEED={json.dumps(seed, ensure_ascii=False)};window.__USER={json.dumps(user, ensure_ascii=False)};window.__RPC={{{rpc_js}}};"
        self.ctx.add_init_script(init)
        self.ctx.route('**/*', self._route)
        self.p = self.ctx.new_page()
        self.p.on('pageerror', lambda e: self.errs.append('pageerror: ' + str(e)))
        self.p.on('console', lambda m: m.type == 'error' and not any(x in m.text for x in ('Failed to load resource', 'net::ERR', 'favicon')) and self.errs.append('console: ' + m.text))
        self.p.goto(f'http://127.0.0.1:{port}/{APP}')
        self.p.wait_for_function("typeof S!=='undefined'&&S.loaded&&S.mode==='live'&&typeof CU!=='undefined'&&CU.loaded&&typeof CT!=='undefined'&&CT.loaded", timeout=30000)
        self.p.wait_for_timeout(400)

    def _route(self, r):
        u = r.request.url
        if u.startswith(SB_CDN):
            return r.fulfill(status=200, content_type='application/javascript', body=MOCK)
        if u.startswith('http://127.0.0.1') or u.startswith('data:') or u.startswith('blob:'):
            return r.continue_()
        return r.abort()

    def ev(self, js):
        return self.p.evaluate(js)

    def go(self, sel):
        t = self.ev(f"(()=>{{const t=performance.now();S.sel={json.dumps(sel)};render();return Math.round(performance.now()-t)}})()")
        self.p.wait_for_timeout(250)
        return t

    def text(self):
        return self.p.inner_text('#pane')

    def check(self, what):
        if self.errs:
            raise Fail(what + ' — ' + ' | '.join(self.errs[:3]))

    def close(self):
        self.ctx.close()

def expect(cond, msg):
    if not cond:
        raise Fail(msg)

# ---------------- الاختبارات ----------------
def t_owner_pages(b, port):
    """المدير: كل الصفحات تفتح من غير أخطاء (كمبيوتر وموبايل)."""
    for w in (1280, 390):
        a = App(b, port, base_seed(n_cust=40, n_certs=10), OWNER, width=w)
        try:
            for pg in PAGES:
                ms = a.go(pg)
                a.check(f'صفحة {pg} ({w}px)')
                expect(len(a.text().strip()) > 20, f'صفحة {pg} فاضية ({w}px)')
                expect(ms < 3000, f'صفحة {pg} بطيئة: {ms}ms')
        finally:
            a.close()

def t_load_paging(b, port):
    """تحميل أكتر من 1000 صف (Supabase بيرجّع 1000 بالكتير في الطلب)."""
    a = App(b, port, base_seed(n_cust=2500, n_certs=1200), OWNER)
    try:
        n, m = a.ev('CU.rows.length'), a.ev('(CT.srv||[]).length')
        expect(n == 2500, f'العهد: اتحمّل {n} من 2500')
        expect(m == 1200, f'المستخلصات: اتحمّل {m} من 1200')
        ids = a.ev('new Set(CU.rows.map(r=>r.id)).size')
        expect(ids == 2500, f'العهد: فيه تكرار ({ids} مختلف)')
        a.check('تحميل على صفحات')
    finally:
        a.close()

def t_custody_pager(b, port):
    """صفحة العهد للمدير: 50 سطر في الصفحة + التالي + فلتر المهندس."""
    a = App(b, port, base_seed(n_cust=130), OWNER)
    try:
        a.go('__custody')
        txt = a.text()
        expect('حركات العُهد (130)' in txt, 'عنوان «حركات العُهد (130)» مش ظاهر')
        expect('صفحة 1 من 3' in txt, 'شريط الصفحات مش ظاهر')
        a.p.click('[data-pg^="cu_all"][data-to="2"] >> nth=0')
        a.p.wait_for_timeout(250)
        expect('صفحة 2 من 3' in a.text(), 'زرار «التالي» ما اشتغلش')
        a.p.select_option('#cu_feng', 'u-eng2')
        a.p.wait_for_timeout(250)
        txt = a.text()
        expect('حركات العُهد (65)' in txt and 'صفحة 1 من 2' in txt, 'فلتر المهندس ما اشتغلش')
        expect(a.ev("document.querySelectorAll('#pane .card')[document.querySelectorAll('#pane .card').length-1].querySelectorAll('tbody tr').length") <= 50, 'أكتر من 50 سطر في الصفحة')
        a.check('ترقيم العهد')
    finally:
        a.close()

def t_certs_pager(b, port):
    """المستخلصات: ترقيم + الوصول لمستخلص في صفحة تانية (من التنبيهات/البحث)."""
    a = App(b, port, base_seed(n_certs=130), OWNER)
    try:
        a.go('__certs')
        expect('كل المستخلصات (130)' in a.text() and 'صفحة 1 من 3' in a.text(), 'ترقيم «كل المستخلصات» مش ظاهر')
        target = a.ev("ctSort(CT.rows)[120].id")
        a.ev(f"CT.hl={json.dumps(target)};render()")
        a.p.wait_for_timeout(250)
        expect(a.ev(f"!!document.getElementById('ctr_'+{json.dumps(target)})"), 'المستخلص المطلوب ما ظهرش (الصفحة ما اتغيرتش)')
        a.check('ترقيم المستخلصات')
    finally:
        a.close()

def t_engineer(b, port):
    """مهندس الموقع: «عهدتي» بالصفحات."""
    a = App(b, port, base_seed(n_cust=240), ENG)
    try:
        txt = a.text()
        expect('حركات عهدتي (120)' in txt, 'عنوان «حركات عهدتي (120)» مش ظاهر')
        expect('صفحة 1 من 3' in txt, 'شريط الصفحات عند المهندس مش ظاهر')
        a.check('شاشة المهندس')
    finally:
        a.close()

def t_tech(b, port):
    """المكتب الفني: «مستخلصات مواقعي» بالصفحات."""
    a = App(b, port, base_seed(n_certs=75), TECH)
    try:
        a.ev("CT.tab='certs';render()")
        a.p.wait_for_timeout(250)
        txt = a.text()
        expect('مستخلصات مواقعي (75)' in txt and 'صفحة 1 من 2' in txt, 'ترقيم مستخلصات المكتب الفني مش ظاهر')
        a.check('شاشة المكتب الفني')
    finally:
        a.close()

LIM_RPC = """usage_detail:()=>{const L=[];for(let i=20;i>=0;i--){const t=new Date(Date.now()-i*864e5).toISOString().slice(0,10);L.push({day:t,db:(300+(20-i)*4)*1048576,files:100*1048576})}
  return {db:380*1048576,files:100*1048576,buckets:{},tables:[{name:'docs',rows:90000,bytes:250e6},{name:'audit_log',rows:40000,bytes:90e6}],log:L}},
  storage_usage:()=>({db:380*1048576,files:100*1048576,buckets:{}})"""

def t_limits(b, port):
    """تنبيه حدود Supabase: كارت أعلى الصفحة لما متوقع توصل 80٪ خلال شهرين + التفاصيل في الإعدادات."""
    a = App(b, port, base_seed(), OWNER, rpc_js=LIM_RPC)
    try:
        a.ev('admLoad(true).then(()=>render())')
        a.p.wait_for_timeout(600)
        a.go('__all')
        txt = a.text()
        expect('مساحة Supabase' in txt and 'متوقع تصل 80٪' in txt, 'كارت التنبيه مش ظاهر')
        a.p.click('[data-lim="go"]')
        a.p.wait_for_timeout(300)
        txt = a.text()
        if 'سرعة الزيادة' not in txt and os.environ.get('DEBUG'):
            print(txt[:3000])
        expect('سرعة الزيادة' in txt and 'أكبر الجداول' in txt, 'تفاصيل المساحة مش ظاهرة في الإعدادات')
        a.go('__all')
        a.p.click('[data-lim="hide"]')
        a.p.wait_for_timeout(250)
        expect('مساحة Supabase' not in a.text(), '«إخفاء لمدة أسبوع» ما اشتغلش')
        a.check('تنبيه الحدود')
    finally:
        a.close()

def t_limits_quiet(b, port):
    """من غير زيادة: مفيش كارت تنبيه."""
    a = App(b, port, base_seed(), OWNER)
    try:
        a.ev('admLoad(true).then(()=>render())')
        a.p.wait_for_timeout(600)
        a.go('__all')
        expect('مساحة Supabase' not in a.text(), 'كارت التنبيه ظاهر من غير سبب')
        a.check('تنبيه الحدود (عادي)')
    finally:
        a.close()

TESTS = [('owner', t_owner_pages), ('paging', t_load_paging), ('custody', t_custody_pager), ('certs', t_certs_pager),
         ('engineer', t_engineer), ('tech', t_tech), ('limits', t_limits), ('limits_quiet', t_limits_quiet)]

def main():
    from playwright.sync_api import sync_playwright
    want = set(sys.argv[1:])
    srv = serve()
    port = srv.server_address[1]
    ok = bad = 0
    with sync_playwright() as pw:
        kw = {'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}
        b = pw.chromium.launch(**kw)
        for name, fn in TESTS:
            if want and name not in want:
                continue
            t0 = time.time()
            try:
                fn(b, port)
                ok += 1
                print(f'✓ {name} — {fn.__doc__.strip()} ({time.time() - t0:.1f}s)')
            except Fail as e:
                bad += 1
                print(f'✗ {name} — {e}')
            except Exception as e:
                bad += 1
                print(f'✗ {name} — {type(e).__name__}: {str(e)[:300]}')
                if os.environ.get('DEBUG'):
                    traceback.print_exc()
        b.close()
    srv.shutdown()
    print(f'\nالنتيجة: {ok} ناجح، {bad} فاشل')
    sys.exit(1 if bad else 0)

if __name__ == '__main__':
    main()
