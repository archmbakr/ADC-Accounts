#!/usr/bin/env python3
"""ADC CONSTRUCTION — ملف الاختبارات الثابت (الدفعة 4، 14 نوفمبر 2026؛ + الدفعة 5)

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
PAGES = ['__all', 's1', '__journal', '__contractors', '__items', '__custody', '__certs', '__store', '__stmts', '__codes', '__trash', '__ocert', '__cost', '__search', '__settings']

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

def t_journal(b, port):
    """اليومية (موبايل): الفورم ورا «+ قيد جديد»، و50 قيد في الشهر + «عرض المزيد»."""
    seed = base_seed()
    m = TODAY.replace(day=1)
    for i in range(120):
        dd = (m + timedelta(days=i % 27)).isoformat() if (m + timedelta(days=i % 27)) <= TODAY else m.isoformat()
        seed['docs'].append(doc(f'expenses/j{i}', {'siteId': 's1', 'amount': 100 + i, 'date': dd, 'item': 'أعمال السباكة', 'contractor': 'مقاول أحمد', 'method': 'cash', 'notes': f'قيد {i}', 'created': 9000 + i, 'by': 'المدير', 'byId': 'u-owner'}))
    a = App(b, port, seed, OWNER, width=390)
    try:
        a.go('__journal')
        expect(a.ev("!document.getElementById('jForm')") and '+ قيد جديد' in a.text(), 'الفورم مش متقفل على الموبايل')
        a.p.click('[data-jform="open"]'); a.p.wait_for_timeout(250)
        expect(a.ev("!!document.getElementById('jForm')"), 'زرار «+ قيد جديد» ما فتحش الفورم')
        a.p.click('[data-jform="close"]'); a.p.wait_for_timeout(250)
        expect(a.ev("!document.getElementById('jForm')"), 'زرار «إغلاق» ما قفلش الفورم')
        n0 = a.ev("document.querySelectorAll('.j-cards .j-cd').length")
        expect(n0 == 50, f'المفروض 50 قيد في الشهر المفتوح، ظهر {n0}')
        expect(a.ev("!!document.querySelector('[data-jmore]')"), 'زرار «عرض المزيد» مش ظاهر')
        a.p.click('[data-jmore] >> nth=0'); a.p.wait_for_timeout(250)
        n1 = a.ev("document.querySelectorAll('.j-cards .j-cd').length")
        expect(n1 == 100, f'«عرض المزيد» المفروض يوصل 100، ظهر {n1}')
        a.check('اليومية')
    finally:
        a.close()
    a = App(b, port, seed, OWNER, width=1280)
    try:
        a.go('__journal')
        expect(a.ev("!!document.getElementById('jForm')"), 'على الكمبيوتر الفورم المفروض مفتوح')
        a.check('اليومية (كمبيوتر)')
    finally:
        a.close()

def t_reports(b, port):
    """التقارير: 4 أساسية + «تقارير أخرى»، وبتتفتح لوحدها لو المختار منهم."""
    a = App(b, port, base_seed(), OWNER)
    try:
        a.go('__stmts')
        vis = a.ev("[...document.querySelectorAll('.sp-s')].map(x=>x.dataset.v)")
        expect(vis == ['site', 'con', 'sup', 'pay'] or sorted(vis) == sorted(['site', 'con', 'sup', 'pay']), f'المربعات الظاهرة: {vis}')
        a.p.click('[data-spmore="1"]'); a.p.wait_for_timeout(250)
        n = a.ev("document.querySelectorAll('.sp-s').length")
        expect(n > 4, '«تقارير أخرى» ما فتحتش')
        a.p.click('.sp-s[data-v="journal"]'); a.p.wait_for_timeout(300)
        a.ev("SP.more=undefined;render()"); a.p.wait_for_timeout(200)
        expect(a.ev("!!document.querySelector('.sp-s[data-v=\"journal\"]')"), 'التقرير المختار من «الأخرى» اختفى')
        a.p.click('[data-spmore="0"]'); a.p.wait_for_timeout(200)
        expect(a.ev("document.querySelectorAll('.sp-s').length") == 4, '«إخفاء التقارير الأخرى» ما اشتغلش')
        a.check('التقارير')
    finally:
        a.close()

def t_mobile_ui(b, port):
    """الموبايل: «خروج» مش في الهيدر، «القائمة» ظاهرة كاملة، التاب المفتوح متعلّم، والثيم الغامق أزراره بيضا."""
    a = App(b, port, base_seed(), OWNER, width=390)
    try:
        a.go('s1')
        expect(a.ev("getComputedStyle(document.getElementById('hdrLock')).display==='none'"), 'زرار «خروج» لسه في الهيدر')
        full = a.ev("(()=>{const b=document.getElementById('menuBtn');const t=b.querySelector('.ml')||b;return t.scrollWidth<=t.clientWidth+1})()")
        expect(full, '«القائمة» لسه مقطوعة')
        expect(a.ev("!!document.querySelector('.bnav button[aria-current=\"true\"]')"), 'مفيش تاب متعلّم تحت')
        a.ev("document.documentElement.setAttribute('data-theme','dark')"); a.p.wait_for_timeout(100)
        col = a.ev("getComputedStyle(document.getElementById('addBtn')).color")
        expect(col.replace(' ', '') in ('rgb(255,255,255)',), f'لون كتابة الزرار في الغامق: {col}')
        a.check('واجهة الموبايل')
    finally:
        a.close()

def t_errors(b, port):
    """رسايل الخطأ بالعربي بالسبب."""
    a = App(b, port, base_seed(), OWNER)
    try:
        cases = {'new row violates row-level security policy for table "custody"': 'صلاحية', 'quota exceeded': 'حد التعديلات',
                 'locked period': 'فترة مقفولة', 'duplicate key value violates unique constraint': 'مكررة', 'JWT expired': 'جلسة الدخول',
                 'canceling statement due to statement timeout': 'لم يرد', 'TypeError: Failed to fetch': 'اتصال', 'something new xyz': 'something new xyz'}
        for m, want in cases.items():
            got = a.ev(f"errMsg({{message:{json.dumps(m)}}},120)")
            expect(want in got, f'«{m}» ← «{got}»')
        a.check('رسايل الخطأ')
    finally:
        a.close()

def t_resync(b, port):
    """تغيير من جهاز تاني (من غير ما يوصل لحظيًا): بيظهر لما التطبيق يرجع من الخلفية، ومن زرار «تحديث»."""
    seed = base_seed(n_cust=10)
    for r in seed['custody']:
        if r['kind'] == 'claim':
            r['status'] = 'pending'
    a = App(b, port, seed, OWNER)
    try:
        pend = "custMine().filter(r=>r.kind==='claim'&&r.status==='pending').length"
        n0 = a.ev(pend)
        expect(n0 > 0, 'مفيش مصروفات قيد المراجعة في البداية')
        a.ev("for(const r of window.__DB.custody)if(r.kind==='claim')r.status='approved'")
        a.ev("Object.defineProperty(document,'visibilityState',{value:'visible',configurable:true});appSideAt=0;document.dispatchEvent(new Event('visibilitychange'))")
        a.p.wait_for_timeout(800)
        expect(a.ev(pend) == 0, 'الرجوع من الخلفية ما حدّثش العهد')
        a.ev("for(const r of window.__DB.custody)if(r.kind==='claim')r.status='pending'")
        a.p.click('#hdrNet')
        a.p.wait_for_function("!document.getElementById('hdrSync').disabled", timeout=15000)
        expect(a.ev(pend) == n0, 'زرار «تحديث» ما جابش آخر بيانات العهد')
        a.check('التحديث')
    finally:
        a.close()

def t_stuck_queue(b, port):
    """طابور العهد: الخانات الداخلية ما تتبعتش، خطأ السيرفر (400) يظهر في كارت ومايوقفش اللي وراه، والنسخة اللي زي السيرفر تتشال."""
    seed = base_seed(n_cust=10)
    for r in seed['custody']:
        if r['kind'] == 'claim':
            r['status'] = 'pending'
    a = App(b, port, seed, OWNER)
    try:
        ids = a.ev("custMerged().filter(r=>r.kind==='claim').map(r=>r.id).slice(0,3)")
        # (1) حركة فيها خانة داخلية (_err) زي اللي حصلت 16 نوفمبر — لازم تتبعت عادي
        a.ev(f"""(()=>{{const r=CU.rows.find(x=>x.id==={json.dumps(ids[0])});appLs(LS_CUSTQ,[{{qid:'q1',op:'put',id:r.id,row:{{...r,status:'approved',_err:'قديم',_local:true}}}}]);}})()""")
        a.ev("custFlush()"); a.p.wait_for_timeout(800)
        st = a.ev(f"window.__DB.custody.find(x=>x.id==={json.dumps(ids[0])}).status")
        expect(st == 'approved', f'الحركة اللي فيها خانة داخلية ما اتبعتتش (الحالة {st})')
        expect(a.ev('custQ().length') == 0, 'الطابور ما فضيش بعد الإرسال')
        # (2) خطأ 400 على أول حركة: يظهر في الكارت، والتانية تتبعت
        a.ev(f"""window.__FAIL={{custody:(op,p,f)=>f.some(x=>x[2]==={json.dumps(ids[1])})?{{message:'new value violates something odd',code:'XX000'}}:null}}""")
        a.ev(f"""(()=>{{const g=id=>CU.rows.find(x=>x.id===id);appLs(LS_CUSTQ,[{{qid:'q2',op:'put',id:{json.dumps(ids[1])},row:{{...g({json.dumps(ids[1])}),status:'approved'}}}},{{qid:'q3',op:'put',id:{json.dumps(ids[2])},row:{{...g({json.dumps(ids[2])}),status:'approved'}}}}])}})()""")
        a.ev("custFlush()"); a.p.wait_for_timeout(800)
        expect(a.ev(f"window.__DB.custody.find(x=>x.id==={json.dumps(ids[2])}).status") == 'approved', 'الحركة اللي ورا الحركة الفاشلة اتوقفت')
        expect(a.ev("custQ().length===1&&!!custQ()[0].err"), 'الحركة الفاشلة ما اتعلّمش عليها خطأ')
        a.go('__custody')
        expect('لم تُحفظ على السيرفر' in a.text(), 'كارت «لم تُحفظ» ما ظهرش')
        # (3) نسخة محلية زي السيرفر بالظبط تتشال لوحدها بعد التحميل
        a.ev("window.__FAIL=null;appLs(LS_CUSTQ,[]);const r=CU.rows[0];appLs(LS_CUSTQ,[{qid:'q4',op:'put',id:r.id,row:JSON.parse(JSON.stringify(r)),err:'قديم'}])")
        a.ev("custLoad().then(()=>render())"); a.p.wait_for_timeout(600)
        expect(a.ev('custQ().length') == 0, 'النسخة المحلية اللي زي السيرفر ما اتشالتش')
        a.errs = [e for e in a.errs if '400' not in e]
        a.check('طابور العهد')
    finally:
        a.close()

def t_cert_retention(b, port):
    """تأمين الأعمال جوه المستخلص: المقترح من آخر مستخلص للمقاول، ويتشال أو يتغير لكل مستخلص."""
    seed = base_seed(n_certs=0)
    seed['cert_boq'] = [{'id': 'bq1', 'site_id': 's1', 'contractor': 'مقاول أحمد', 'item': 'بند 1', 'data': {'lines': [{'id': 'l1', 'kind': 'line', 'desc': 'نجارة', 'unit': 'م2', 'qty': 100, 'rate': 200}]}}]
    seed['certs'] = [{'id': 'old1', 'site_id': 's1', 'contractor': 'مقاول أحمد', 'no': 1, 'status': 'approved', 'updated_at': '2026-11-01T00:00:00Z',
                      'data': {'date': d(20), 'item': 'بند 1', 'ret_pct': 0, 'lines': {'l1': {'tot': 10}}}}]
    a = App(b, port, seed, OWNER)
    try:
        a.go('__certs')
        a.ev("CT.form={site:'s1',con:'مقاول أحمد',item:'بند 1',date:today(),lines:{},deds:[]};render()")
        a.p.wait_for_timeout(300)
        expect(a.ev("!!document.getElementById('ct_reton')"), 'خانة «تأمين أعمال» مش ظاهرة في فورم المستخلص')
        expect(a.ev("!document.getElementById('ct_reton').checked"), 'المقترح المفروض «بدون تأمين» زي آخر مستخلص للمقاول')
        a.p.click('#ct_reton'); a.p.fill('#ct_retp', '7'); a.p.wait_for_timeout(200)
        expect(a.ev("ctReadForm(),ctFormCert(CT.form).data.ret_pct") == 7, 'النسبة 7٪ ما اتسجلتش في المستخلص')
        expect(a.ev("ctRetDef('s2','مقاول أحمد',null,'')") == 0, 'المقترح من موقع تاني المفروض ياخد آخر مستخلص للمقاول')
        expect(a.ev("ctRetDef('s1','مقاول جديد',null,'')") == 5, 'مقاول جديد المفروض 5٪')
        expect(a.ev("!document.getElementById('ctRetBox')"), 'كارت نسبة التأمين على مستوى الصفحة لسه موجود')
        a.check('تأمين الأعمال')
    finally:
        a.close()

def t_site_groups(b, port):
    """البنود العامة لكل موقع: تقسيم خاص بيبدأ بنسخة من المشترك، والتعديل مايأثرش على موقع تاني، و«بدون»."""
    seed = base_seed()
    seed['docs'].append(doc('items/g1', {'name': 'الأعمال الصحية', 'kind': 'group', 'items': ['أعمال السباكة'], 'created': 5}))
    a = App(b, port, seed, OWNER)
    try:
        a.ev("S.siteTab='sum';CK.igsite=true"); a.go('s1')
        expect('البنود العامة لهذا الموقع' in a.text(), 'كارت البنود العامة مش ظاهر في ملخص الموقع')
        a.p.click('[data-igs="mode"][data-v="own"]'); a.p.wait_for_timeout(500)
        expect(a.ev("S.sites.find(x=>x.id==='s1').igMode") == 'own', 'الموقع ما اتحولش لتقسيم خاص')
        expect(a.ev("igOf('أعمال السباكة',igPfOfSite('s1'))") == 'الأعمال الصحية', 'التقسيم الخاص ما اتنسخش من المشترك')
        a.p.click('[data-igs="rmitem"] >> nth=0'); a.p.wait_for_timeout(400)
        expect(a.ev("igOf('أعمال السباكة',igPfOfSite('s1'))") == '', 'شيل البند من التقسيم الخاص ما اشتغلش')
        expect(a.ev("igOf('أعمال السباكة',igPfOfSite('s2'))") == 'الأعمال الصحية', 'التعديل في موقع أثّر على موقع تاني')
        a.p.click('[data-igs="mode"][data-v="off"]'); a.p.wait_for_timeout(400)
        expect(a.ev("igGroups(igPfOfSite('s1')).length") == 0, '«بدون بنود عامة» ما اشتغلش')
        a.check('البنود العامة لكل موقع')
    finally:
        a.close()

def cost_seed():
    seed = base_seed()
    seed['owner_docs'] = [
        {'id': 'pj1', 'kind': 'proj', 'site_id': 's1', 'data': {'secs': [{'id': 'sc1', 'title': 'الأعمال الصحية', 'g': ''}],
            'boq': [{'id': 'b1', 's': 'sc1', 'desc': 'أعمال السباكة', 'unit': 'مقطوعية', 'cq': 1, 'rate': 100000},
                    {'id': 'b2', 's': 'sc1', 'desc': 'توريدات حديد', 'unit': 'طن', 'cq': 20, 'rate': 40000}]}},
        {'id': 'oc1', 'kind': 'cert', 'site_id': 's1', 'data': {'no': 1, 'date': d(30), 'status': 'approved', 'lines': [{'id': 'l1', 's': 'sc1', 'boq': 'b1', 'desc': 'أعمال السباكة', 'unit': 'مقطوعية', 'cq': 1, 'rate': 100000, 'totQ': 0.5, 'pct': 100}]}},
        {'id': 'oc2', 'kind': 'cert', 'site_id': 's1', 'data': {'no': 2, 'date': d(5), 'status': 'approved', 'lines': [{'id': 'l1', 's': 'sc1', 'boq': 'b1', 'desc': 'أعمال السباكة', 'unit': 'مقطوعية', 'cq': 1, 'rate': 100000, 'totQ': 1, 'pct': 80},
                                                                                                         {'id': 'l2', 's': 'sc1', 'boq': 'b2', 'desc': 'توريدات حديد', 'unit': 'طن', 'cq': 20, 'rate': 40000, 'totQ': 10, 'pct': 50}]}}]
    return seed

def b12_seed():
    seed = cost_seed()
    for x in seed['owner_docs']:
        if x['kind'] == 'proj':
            x['data']['tpl'] = 'tb'
    seed['owner_docs'].append({'id': 'tb', 'kind': 'tpl', 'data': {'name': 'نموذج بالمقايسة', 'type': 'boq'}})
    seed['docs'] += [doc('expenses/t1', {'siteId': 's1', 'amount': 30000, 'date': d(10), 'item': 'أعمال السباكة', 'contractor': 'مقاول أحمد', 'method': 'cash', 'notes': 'على البند', 'boq': 'b1', 'created': 5000}),
                     doc('expenses/t2', {'siteId': 's1', 'amount': 50000, 'date': d(3), 'item': 'توريدات حديد', 'contractor': 'مورد الحديد', 'method': 'cash', 'notes': 'حديد مشترك', 'boq': 'sh:steel', 'created': 5001}),
                     doc('expenses/t3', {'siteId': 's1', 'amount': 2000, 'date': d(3), 'item': 'أعمال السباكة', 'contractor': 'مقاول أحمد', 'method': 'cash', 'notes': 'مكتب', 'boq': 'co', 'created': 5002}),
                     doc('expenses/t4', {'siteId': 's1', 'amount': 1000, 'date': d(3), 'item': 'أعمال السباكة', 'contractor': 'مقاول أحمد', 'method': 'cash', 'notes': 'يوميات صب', 'boq': 'sh:misc', 'created': 5003})]
    seed['cost_items'] = [{'id': 'ci1', 'site_id': 's1', 'data': {'boq': 'b1', 'name': 'أعمال السباكة', 'deds': [], 'links': [], 'parts': [
                              {'id': 'p1', 'name': 'حديد تسليح', 'type': 'mat', 'per': 0.1, 'price': 40000}, {'id': 'p2', 'name': 'Over Head', 'type': 'oh', 'per': 1, 'price': 1000},
                              {'id': 'p3', 'name': 'أرباح', 'type': 'oth', 'per': 1, 'price': 500}]}},
                          {'id': 'ci2', 'site_id': 's1', 'data': {'boq': 'b2', 'name': 'توريدات حديد', 'deds': [], 'links': [], 'parts': [{'id': 'p4', 'name': 'حديد', 'type': 'mat', 'per': 1, 'price': 30000}]}}]
    seed['members'].append({'id': 'u-acct', 'email': 'acct@test.local', 'name': 'Taha elsayed', 'role': 'acct', 'approved': True, 'created_at': '2026-10-01T00:00:00Z'})
    return seed

def qty_seed():
    seed = b12_seed()
    for x in seed['owner_docs']:
        if x['kind'] == 'proj':
            x['data']['boq'] = [{'id': 'b1', 's': 'sc1', 'code': '10', 'desc': 'خرسانة مسلحة للأسقف', 'unit': 'م3', 'cq': 100, 'rate': 5000},
                                {'id': 'b2', 's': 'sc1', 'code': '5', 'desc': 'دكة خرسانة عادية', 'unit': 'م2', 'cq': 1000, 'rate': 300}]
            x['data']['shared'] = [{'id': 'conc', 'n': 'خرسانة', 'm': 'qty', 'kw': 'خرسان', 'price': '2000', 'sc': '', 'ws': '', 'th': '', 'left': 'pend'}]
            x['data']['sharedV'] = 2
        if x['kind'] == 'cert' and x['data']['no'] == 2:
            x['data']['lines'] = [{'id': 'l1', 's': 'sc1', 'boq': 'b1', 'desc': 'خرسانة مسلحة للأسقف', 'unit': 'م3', 'cq': 100, 'rate': 5000, 'totQ': 40, 'pct': 100},
                                  {'id': 'l2', 's': 'sc1', 'boq': 'b2', 'desc': 'دكة خرسانة عادية', 'unit': 'م2', 'cq': 1000, 'rate': 300, 'totQ': 200, 'pct': 100}]
    seed['docs'] = [x for x in seed['docs'] if x['path'] not in ('expenses/t1', 'expenses/t2', 'expenses/t4')]
    seed['docs'] += [doc('expenses/q1', {'siteId': 's1', 'amount': 50000, 'date': d(20), 'item': 'خرسانة', 'contractor': 'مقاول أحمد', 'method': 'cash', 'notes': 'صبة سقف', 'boq': 'b1', 'created': 6000}),
                     doc('expenses/q2', {'siteId': 's1', 'amount': 99999, 'date': d(20), 'item': 'توريدات حديد', 'contractor': 'مورد الحديد', 'method': 'cash', 'notes': 'حديد سقف', 'boq': 'b1', 'created': 6001}),
                     doc('expenses/q3', {'siteId': 's1', 'amount': 100000, 'date': d(1), 'item': 'خرسانة', 'contractor': 'مقاول أحمد', 'method': 'cash', 'notes': 'صبة مشتركة', 'boq': 'sh:conc', 'created': 6002})]
    seed['cost_items'] = [{'id': 'ci1', 'site_id': 's1', 'data': {'boq': 'b1', 'name': 'أسقف', 'deds': [], 'links': [], 'parts': []}},
                          {'id': 'ci2', 'site_id': 's1', 'data': {'boq': 'b2', 'name': 'دكة', 'deds': [], 'links': [], 'parts': []}}]
    return seed

def t_qtyconc(b, port):
    """التوزيع «بكميات المستخلص»: م3 من المستخلص × السعر، المتعلّم مباشرة الأول، الفائض معلّق أو هالك."""
    a = App(b, port, qty_seed(), OWNER)
    try:
        a.go('__cost'); a.p.wait_for_timeout(700)
        if a.ev("CR.site") != 's1':
            a.p.select_option('#cr_site', 's1'); a.p.wait_for_timeout(400)
        a.check('مراجعة التكاليف بكميات المستخلص')
        q = "(()=>{const K=crK('s1',crCert('s1'));const b=K.SH.B.find(x=>x.x.id==='conc');return {paid:b.paid,left:b.left,waste:b.waste,after:b.after,needT:b.theoT,rows:Object.fromEntries(b.rows.map(r=>[r.id,{m3:r.m3,need:r.need,dir:r.dir,alloc:r.alloc,waste:r.waste,tot:r.tot}])),sha1:K.K.find(x=>x.r.id==='ci1').k.sha,act1:K.K.find(x=>x.r.id==='ci1').k.act,actTo1:K.K.find(x=>x.r.id==='ci1').k.actTo}})()"
        r = a.ev(q); R = r['rows']
        expect(abs(R['ci1']['m3'] - 40) < 0.01 and abs(R['ci2']['m3'] - 20) < 0.01, f'م3 غلط (م2 × 0.10): {R}')
        expect(abs(R['ci1']['need'] - 80000) < 0.01 and abs(R['ci1']['dir'] - 50000) < 0.01, f'المفروض/المتعلّم مباشرة غلط (الحديد اتحسب؟): {R}')
        expect(abs(R['ci1']['alloc'] - 30000) < 0.01 and abs(R['ci2']['alloc'] - 40000) < 0.01, f'التسكين غلط: {R}')
        expect(abs(r['paid'] - 100000) < 0.01 and abs(r['left'] - 30000) < 0.01 and abs(r['after'] - 100000) < 0.01, f'الفائض/بعد تاريخ المستخلص غلط: {r}')
        expect(abs(r['sha1'] - 30000) < 0.01 and abs(r['act1'] - (50000 + 99999 + 30000)) < 0.01, f'نصيب البند ما اتضافش للمصروف: {r}')
        a.p.click('tr[data-cr="shtog"][data-id="conc"]'); a.p.wait_for_timeout(300)
        t = a.text()
        expect('متعلّم مباشرة' in t and 'لسه منزلتش في مستخلص' in t and 'بكميات المستخلص' in t, 'جدول التسكين ما ظهرش')
        a.p.click('[data-cr="shleft"][data-v="waste"]'); a.p.wait_for_timeout(600)
        r = a.ev(q); R = r['rows']
        expect(abs(r['waste'] - 30000) < 0.05 and abs(r['left']) < 0.05 and abs(R['ci1']['waste'] - 20000) < 0.05 and abs(R['ci2']['waste'] - 10000) < 0.05, f'الهالك ما اتحمّلش بنسبة المفروض: {r}')
        expect(a.ev("ocProj('s1').data.shared.find(x=>x.id==='conc').left") == 'waste', 'اختيار الفائض ما اتحفظش في ملف المشروع')
        a.ev("ocProj('s1').data.shared[0].th='1.1=0.3 ; 1.2=0.15'")
        dbg = a.ev("(()=>{const x=bqShared('s1')[0];return {th:x.th,code:crInfo('s1',CR.rows.find(r=>r.id==='ci2').data),t:bqThick(x,crInfo('s1',CR.rows.find(r=>r.id==='ci2').data))}})()")
        expect(abs(a.ev(q)['rows']['ci2']['m3'] - 30) < 0.01, f'التخانة المكتوبة ما اتطبقتش {dbg}')
        a.ev("ocProj('s1').data.shared[0].price=''")
        r = a.ev(q)
        expect(abs(r['left'] - 100000) < 0.05 or r['waste'] > 0, f'من غير سعر المفروض ميتوزعش: {r}')
        # السعر من التحليل لما الخانة فاضية — وعنصر المصنعيات «…الخرسانة» يروح للمصنعيات مش للخرسانة
        an = a.ev("""(()=>{const P=ocProj('s1');P.data.shared=[{id:'conc',n:'خرسانة',m:'qty',kw:'خرسان',price:'',sc:'',left:'pend'},{id:'lab',n:'مصنعيات أعمال الخرسانة',m:'qty',kw:'مصن',price:'',sc:'',left:'pend'}];
          const r=CR.rows.find(x=>x.id==='ci1');r.data.parts=[{id:'a1',name:'سعر الخرسانة محتوي 400',type:'mat',per:1,price:2500},{id:'a2',name:'هالك الخرسانة 3%',type:'mat',per:0.03,price:2500},{id:'a3',name:'مصناعيات أعمال الخرسانة',type:'lab',per:1,price:1500}];
          const K=crK('s1',crCert('s1'));const c=K.SH.B.find(b=>b.x.id==='conc'),l=K.SH.B.find(b=>b.x.id==='lab');
          return {cu:c.rows.find(y=>y.id==='ci1').uP,cs:c.rows.find(y=>y.id==='ci1').src,lu:l.rows.find(y=>y.id==='ci1').uP,c2:c.rows.find(y=>y.id==='ci2').uP,lsh:bqPartSh('s1',r.data.parts[2])}})()""")
        expect(abs(an['cu'] - 2575) < 0.01 and an['cs'] == 'an' and abs(an['lu'] - 1500) < 0.01 and an['c2'] == 0 and an['lsh'] == 'lab', f'السعر من التحليل غلط: {an}')
        a.ev("CR.rows.find(x=>x.id==='ci1').data.parts=[];ocProj('s1').data.shared=[{id:'conc',n:'خرسانة',m:'qty',kw:'خرسان',price:'2000',sc:'',ws:'',th:'',left:'pend'}]")
        # ثبات الشاشة: الرسم بيستنى والقايمة مفتوحة، وبيتجمّع
        a.go('s1'); a.p.wait_for_timeout(300)
        hold = a.ev("""(async()=>{const sel=document.querySelector('#pane select');if(!sel)return {skip:1};
          const mk=()=>{const d=document.createElement('i');d.id='__mk';document.getElementById('pane').appendChild(d)};mk();
          sel.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));for(let i=0;i<10;i++)renderSoon();await new Promise(r=>setTimeout(r,400));const held=!!document.getElementById('__mk');
          sel.dispatchEvent(new Event('change',{bubbles:true}));await new Promise(r=>setTimeout(r,400));const after=!document.getElementById('__mk');return {held,after}})()""")
        expect(hold.get('skip') or (hold['held'] and hold['after']), f'الرسم ما استناش القايمة المفتوحة: {hold}')
        cnt = a.ev("(async()=>{await new Promise(r=>setTimeout(r,400));let n=0,st=[];const o=render;window.render=function(){n++;st.push((new Error().stack||'').split('\\n').slice(2,4).join('|'));return o.apply(this,arguments)};for(let i=0;i<30;i++)renderSoon();await new Promise(r=>setTimeout(r,500));window.render=o;return [n,st]})()")
        expect(cnt[0] == 1, f'الرسمات ما اتجمّعتش: {cnt}')
        a.go('__cost'); a.p.wait_for_timeout(300)
        a.ev("ocProj('s1').data.shared[0].price='2000';ocProj('s1').data.shared[0].th='';ocProj('s1').data.shared[0].left='pend'")
        v = a.ev("crVarRows('s1').rows.map(x=>x.ovs.map(o=>o.t||'').join('|')).join('#')")
        expect(isinstance(v, str), 'تقرير الفروق اتكسر')
        a.check('بعد التسكين والهالك')
    finally:
        a.close()

def t_batch14(b, port):
    """دفعة 27 نوفمبر بالليل: فورم البند لحد تاريخ المستخلص، تحذير «بنسبة المنفذ» من غير بنود، إجمالي قيمة المنفذ، فواتير المستخلص سطر واحد في الطباعة، الدخول من غير نت."""
    a = App(b, port, b12_seed(), OWNER)
    try:
        a.go('__cost'); a.p.wait_for_timeout(700)
        if a.ev("CR.site") != 's1':
            a.p.select_option('#cr_site', 's1'); a.p.wait_for_timeout(400)
        a.check('مراجعة التكاليف')
        x = a.ev("(()=>{const r=CR.rows.find(z=>z.id==='ci1');const k=crCalc('s1',r.data);const x=crFormTwo(S.sites.find(s=>s.id==='s1'),{...r.data,id:r.id},k);const K=crK('s1',crCert('s1')).K.find(z=>z.r.id==='ci1').k;return {act:x.act,actTo:x.actTo,kact:K.act,kto:K.actTo,toDate:x.toDate}})()")
        expect(x['actTo'] is not None and abs(x['act'] - x['kact']) < 0.01 and abs(x['actTo'] - x['kto']) < 0.01 and x['toDate'], f'فورم البند مش بيحسب لحد تاريخ المستخلص زي الصفحة: {x}')
        a.ev("ocProj('s1').data.shared=[{id:'lab',n:'مصنعيات',m:'exe',kw:'',price:'',sc:''}];ocProj('s1').data.sharedV=2;CR.shOpen=new Set(['lab']);render()")
        a.ev("S.exp.push({id:'zz',siteId:'s1',amount:500,date:today(),boq:'sh:lab',item:'x'});render()")
        t = a.text()
        expect('بيتوزع على كل بنود المقايسة' in t, 'تحذير «بنسبة المنفذ» من غير بنود مش ظاهر')
        expect('100٪' in t, 'إجمالي قيمة المنفذ مش ظاهر في جدول «بنسبة المنفذ»')
        expect(a.ev("BQ_SH_DEF.find(x=>x.id==='form').sc") == '4-13', 'الافتراضي للشدات مش 4-13')
        # فواتير مستخلص المالك سطر واحد
        o = a.ev("(()=>{const L=ocOutLines([{id:'a',desc:'شغل',rate:10,totQ:2,prevQ:0,pct:100},{id:'b',src:'i:1',desc:'فاتورة 1',rate:100,totQ:1,pct:100},{id:'c',src:'e:2',desc:'مصروف',rate:50,totQ:1,pct:100}]);return {n:L.length,agg:L.find(l=>l.agg)?L.find(l=>l.agg)._v:null,tot:L.reduce((s,l)=>s+(l.agg?l._v:ocV(l)),0)}})()")
        expect(o['n'] == 2 and abs(o['agg'] - 150) < 0.01 and abs(o['tot'] - 170) < 0.01, f'تجميع الفواتير في الطباعة غلط: {o}')
        a.check('بعد التعديلات')
        # الدخول من غير نت
        ok = a.ev("(async()=>{await appOffPwSave('owner@test.local','Pass1234!','u-owner');return [await appOffPwOk('owner@test.local','Pass1234!','u-owner'),await appOffPwOk('owner@test.local','wrong','u-owner'),await appOffPwOk('x@test.local','Pass1234!','u-owner')]})()")
        expect(ok == [True, False, False], f'التحقق من كلمة المرور من غير نت غلط: {ok}')
    finally:
        a.close()

def t_simplify(b, port):
    """التبسيط: أيقونة الاتصال، الإعدادات والخروج في القائمة، الفلاتر ورا «فلتر»، «⋯» في السطر، الرئيسية من غير متابعة، الإعدادات أقسام."""
    a = App(b, port, base_seed(), OWNER)
    try:
        a.go('s1'); a.p.wait_for_timeout(400)
        expect(a.ev("getComputedStyle(document.getElementById('hdrNet')).display!=='none'&&getComputedStyle(document.getElementById('setBtn')).display==='none'"), 'أيقونة الاتصال مش ظاهرة أو الإعدادات لسه في الهيدر')
        a.p.click('#menuBtn'); a.p.wait_for_timeout(200)
        expect(a.ev("!!document.querySelector('#toolMenu [data-hsync]')&&!!document.querySelector('#toolMenu [data-hlock]')&&!!document.querySelector('#toolMenu [data-site=\"__settings\"]')"), 'الحساب مش في آخر القائمة')
        a.p.mouse.click(5, 700)
        expect(a.ev("document.querySelector('.fl-more').hidden"), 'الفلاتر الإضافية ظاهرة من الأول')
        a.p.click('[data-fopen]'); a.p.wait_for_timeout(200)
        a.p.select_option('#f_i', 'أعمال السباكة'); a.p.wait_for_timeout(300)
        expect('البند: أعمال السباكة' in a.text(), 'علامة الفلتر مش ظاهرة')
        a.p.click('[data-fclr="i"]'); a.p.wait_for_timeout(300)
        expect(a.ev("S.filt.i") == '', '✕ ما شالش الفلتر')
        a.p.click('[data-rmenu] >> nth=0'); a.p.wait_for_timeout(150)
        a.p.click('.rm-pop:not([hidden]) [data-del]'); a.p.wait_for_timeout(300)
        expect('تأكيد الحذف' in a.text(), 'الحذف من «⋯» ما اشتغلش')
        a.ev("S.confirmDel=null;render()")
        a.go('__all'); a.p.wait_for_timeout(300)
        expect('متابعة موقع' not in a.text(), 'متابعة موقع لسه في الرئيسية')
        a.go('__settings'); a.p.wait_for_timeout(400)
        g = a.ev("[...document.querySelectorAll('.set-grp')].map(x=>x.dataset.grp)")
        expect('me' in g and 'sys' in g and 'log' in g, f'أقسام الإعدادات: {g}')
        a.check('التبسيط')
    finally:
        a.close()

def t_cost_new(b, port):
    """مراجعة التكاليف الجديدة: الجدول بالحالة، المسجّل/الموزّع، بطاقة البند، بعد تاريخ المستخلص «تبع المستخلص»، صحة البيانات، التقرير."""
    a = App(b, port, b12_seed(), OWNER)
    try:
        a.go('__cost'); a.p.wait_for_timeout(700)
        if a.ev("CR.site") != 's1':
            a.p.select_option('#cr_site', 's1'); a.p.wait_for_timeout(400)
        a.check('مراجعة التكاليف الجديدة')
        t = a.text()
        expect('المفروض يتصرف' in t and 'المسجّل' in t and 'الموزّع' in t and 'الضريبة المستحقة' in t, 'كروت/أعمدة الجدول الجديد ناقصة')
        R = a.ev("(()=>{const c=crCert('s1'),CK=crK('s1',c);return crRowsNew('s1',CK,c).map(R=>({id:R.x.r.id,reg:R.reg,dist:R.dist,tot:R.tot,plan:R.plan,st:R.st.c,tax:R.tax,exeV:R.exeV}))})()")
        r1 = [x for x in R if x['id'] == 'ci1'][0]
        expect(abs(r1['reg'] + r1['dist'] - r1['tot']) < 0.01 and r1['st'] in ('g', 'y', 'r'), f'المسجّل + الموزّع ≠ الإجمالي: {r1}')
        expect(abs(r1['tax'] - r1['exeV'] * 0.045) < 0.01, f'الضريبة المستحقة غلط: {r1}')
        a.p.click('tr.crr[data-id="ci1"]'); a.p.wait_for_timeout(300)
        t = a.text()
        expect('الدراسة مقابل الفعلي' in t and 'الضريبة المستحقة على البند' in t and 'المتوقع عند نهاية البند' in t, 'بطاقة البند ما اتفتحتش')
        # بعد تاريخ المستخلص
        n = a.ev("crAfterList('s1',crCert('s1')).length")
        expect(n >= 1, 'مفيش مصروفات بعد تاريخ المستخلص في التجربة')
        tot0 = a.ev("(()=>{const c=crCert('s1');return crRowsNew('s1',crK('s1',c),c).reduce((s,R)=>s+R.tot,0)})()")
        a.ev("CR.aftOpen=true;render()"); a.p.wait_for_timeout(200)
        a.p.click('[data-cr="aftall"]'); a.p.wait_for_timeout(200)
        a.p.click('[data-cr="aftin"]'); a.p.wait_for_timeout(500)
        inc = a.ev("[...crIncOf('s1',crCert('s1'))].length")
        expect(inc == n, f'التعليم «تبع المستخلص» ما اتحفظش ({inc}/{n})')
        tot1 = a.ev("(()=>{const c=crCert('s1');return crRowsNew('s1',crK('s1',c),c).reduce((s,R)=>s+R.tot,0)})()")
        expect(tot1 > tot0 + 0.01, f'المصروف المعلّم ما دخلش في المقارنة ({tot0} → {tot1})')
        expect('تبع مستخلص' in a.text(), 'علامة «تبع المستخلص» مش ظاهرة')
        # التقرير
        d = a.ev("(()=>{const x=crRepDoc(S.sites.find(s=>s.id==='s1'),true);return {t:x.title,n:(x.body.match(/crp-pb/g)||[]).length}})()")
        expect('تقرير التكاليف' in d['t'] and d['n'] >= 2, f'تقرير التكاليف ناقص: {d}')
        a.check('بعد التعليم والتقرير')
    finally:
        a.close()

def t_batch12(b, port):
    """الدفعة 1+2: بند المقايسة على المصروف، مصروفات على الشركة، الخامات المشتركة بتتوزع، الأرباح من حد الصرف، تقرير الفروق، نسبة الإشراف، عهدة المحاسب."""
    a = App(b, port, b12_seed(), OWNER)
    try:
        a.go('__cost'); a.p.wait_for_timeout(700)
        if a.ev("CR.site") != 's1':
            a.p.select_option('#cr_site', 's1'); a.p.wait_for_timeout(400)
        a.check('صفحة مراجعة التكاليف')
        k = a.ev("crCalc('s1',CR.rows.find(r=>r.id==='ci1').data)")
        expect(abs(k['tagV'] - 30000) < 0.01, f'المصروف المسجّل على البند ما اتحسبش: {k["tagV"]}')
        sp = k['split']
        expect(abs(sp['prf'] - 500) < 0.01 and abs(sp['oh'] - 1000) < 0.01 and abs(sp['dir'] - 4000) < 0.01 and abs(k['lim'] - 4000) < 0.01, f'الأرباح/الأوفر هيد/حد الصرف غلط: {sp}')
        e1 = a.ev("crLinkVal('s1',{t:'exp',n:'أعمال السباكة'})")
        all1 = a.ev("r2(S.exp.filter(e=>e.siteId==='s1'&&!e.deleted&&e.item==='أعمال السباكة'&&!e.boq).reduce((a,e)=>a+amt(e),0))")
        expect(abs(e1 - all1) < 0.01, 'المصروف المسجّل على بند مقايسة اتحسب تاني عن طريق الربط بالبند')
        SH = a.ev("(()=>{const K=crK('s1',crCert('s1'));return {B:K.SH.B.map(b=>({id:b.x.id,paid:b.paid,theoT:b.theoT,alloc:b.alloc,left:b.left,rows:b.rows.map(r=>({id:r.id,theo:r.theo,alloc:r.alloc}))})),hasOh:K.hasOh,b1:K.K.find(x=>x.r.id==='ci1').k.sha}})()")
        st = [x for x in SH['B'] if x['id'] == 'steel'][0]
        expect(abs(st['paid'] - 50000) < 0.01, f'مدفوع الحديد المشترك غلط: {st}')
        th = {r['id']: r['theo'] for r in st['rows']}
        expect(abs(th['ci1'] - 3200) < 0.01 and abs(th['ci2'] - 150000) < 0.01, f'المستهلك نظريًا غلط: {th}')
        expect(abs(st['alloc'] - 50000) < 0.05 and abs(st['left']) < 0.05, f'التوزيع غلط (المدفوع أقل من النظري): {st}')
        expect(abs(SH['b1'] - 3200 * 50000 / 153200) < 0.05, f'نصيب البند من الحديد غلط: {SH["b1"]}')
        expect(SH['hasOh'], 'الأوفر هيد مش متعرف')
        tk = a.ev("(()=>{const k=crK('s1',crCert('s1')).K.find(x=>x.r.id==='ci1').k;return {act:k.act,actTo:k.actTo,after:k.after,save:k.save,earned:k.earned}})()")
        expect(tk['actTo'] is not None and tk['after'] > 0.01 and tk['actTo'] >= 30000 - 0.01 and abs(tk['act'] - tk['actTo'] - tk['after']) < 0.01, f'المصروف بعد تاريخ المستخلص ما اتفصلش: {tk}')
        expect(abs(tk['save'] - (tk['earned'] - tk['actTo'])) < 0.01 or tk['actTo'] < 0.005, f'الوفر المفروض حتى تاريخ المستخلص: {tk}')
        expect('بعد تاريخ المستخلص' in a.text(), 'سطر «بعد تاريخ المستخلص» مش ظاهر')
        a.p.click('tr[data-cr="shtog"][data-id="steel"]'); a.p.wait_for_timeout(300)
        expect('للوحدة (المستخدم)' in a.text() and 'المستهلك نظريًا = ' in a.text(), 'تفاصيل توزيع الحديد على البنود ما ظهرتش')
        expect(a.ev("bqResolve('s1','نثريات خرسانة — مشترك')") == 'sh:misc', 'قراءة «نثريات خرسانة — مشترك» غلط')
        expect(a.ev("bqInSc('4-13','7')") and not a.ev("bqInSc('4-13','2')") and a.ev("bqInSc('','2')") and a.ev("bqInSc('4,7','7')"), 'نطاق البنود غلط')
        ms = a.ev("(()=>{ocProj('s1').data.shared=[...BQ_SH_DEF.slice(0,4),{...BQ_MISC,sc:'1.2'}];const K=crK('s1',crCert('s1'));const b=K.SH.B.find(x=>x.x.id==='misc');return {paid:b.paid,rows:b.rows.map(r=>r.id),alloc:b.alloc}})()")
        expect(ms['paid'] == 1000 and ms['rows'] == ['ci2'] and abs(ms['alloc'] - 1000) < 0.01, f'نثريات الخرسانة اتوزعت برّه النطاق: {ms}')
        a.ev("delete ocProj('s1').data.shared")
        t = a.text()
        expect('مقابل الأوفر هيد' in t and 'الخامات المشتركة' in t and 'اتصرف (مسجّل + موزّع)' in t, 'كروت الأوفر هيد / الخامات المشتركة / المصروف حتى الآن ما ظهرتش')
        expect(abs(a.ev("crCoSpent('s1')") - 2000) < 0.01, 'مصروفات على الشركة غلط')
        expect(len(a.ev("crVarRows('s1').rows")) >= 1, 'تقرير بنود فرقت عن الدراسة فاضي')
        a.ev("CR.printing=crVarDoc(S.sites.find(s=>s.id==='s1'))")
        expect('فرقت عن الدراسة' in a.ev("CR.printing.title"), 'تقرير الفروق ما اتعملش')
        # الاستيراد
        expect(a.ev("bqResolve('s1','1.1')") == 'b1' and a.ev("bqResolve('s1','مصروفات على الشركة')") == 'co' and a.ev("bqResolve('s1','حديد تسليح — مشترك')") == 'sh:steel', 'قراءة بند المقايسة من Excel غلط')
        # فورم المصروف
        a.ev("S.entryOpen='s1';S.kind='exp'"); a.go('s1'); a.p.wait_for_timeout(300)
        expect(a.p.locator('#e_boq').count() == 1, 'خانة «بند المقايسة» مش في فورم المصروف')
        opts = a.ev("[...document.querySelectorAll('#e_boq option')].map(o=>o.value)")
        expect('b1' in opts and 'co' in opts and 'sh:steel' in opts, f'اختيارات بند المقايسة ناقصة: {opts}')
        a.p.fill('#e_amount', '1234'); a.p.fill('#e_notes', 'تجربة')
        a.ev("(()=>{const s=document.getElementById('e_item');s.value=[...s.options].find(o=>o.textContent.includes('أعمال السباكة')).value;s.dispatchEvent(new Event('change'))})()")
        a.ev("(()=>{const s=document.getElementById('e_contractor');s.value=[...s.options].find(o=>o.textContent.includes('مقاول أحمد')).value;s.dispatchEvent(new Event('change'))})()")
        a.p.click('#saveBtn'); a.p.wait_for_timeout(300)
        expect('بند المقايسة' in a.p.inner_text('#formMsg'), 'المصروف اتحفظ من غير بند المقايسة')
        a.p.select_option('#e_boq', 'b2'); a.p.click('#saveBtn'); a.p.wait_for_timeout(500)
        expect(a.ev("S.exp.some(e=>e.amount===1234&&e.boq==='b2')"), 'بند المقايسة ما اتحفظش مع المصروف')
        # ملف المشروع
        a.ev("OC.site='s1';OC.tab='proj';OC.pe=null"); a.go('__ocert'); a.p.wait_for_timeout(500)
        t = a.text()
        expect('الخامات المشتركة' in t and 'تحليل السعر' in t and 'حد المصاريف الإدارية' in t, 'ملف المشروع ما فيهوش الخامات المشتركة / التحليل / حد المصاريف')
        a.p.click('[data-crboq="b1"]'); a.p.wait_for_timeout(500)
        expect(a.ev("S.sel")=='__cost' and a.ev("CR.edit&&CR.edit.boq") == 'b1', 'زرار التحليل في ملف المشروع ما فتحش البند')
        expect(a.p.locator('[data-crp="0"][data-k="sh"]').count() == 1 and 'الكمية الكلية' in a.text(), 'عمود الخامة المشتركة / الكمية الكلية مش في التحليل')
        a.p.fill('[data-crshr="steel"]', '0.12'); a.p.click('[data-cr="save"]'); a.p.wait_for_timeout(700)
        expect(a.ev("(CR.rows.find(r=>r.id==='ci1').data.shr||{}).steel") == 0.12, 'النسبة الفعلية ما اتحفظتش')
        expect(any(o['n'] == 'حديد تسليح' for x in a.ev("crVarRows('s1').rows.map(r=>({o:r.ovs}))") for o in x['o']), 'البند اللي نسبته اتغيرت مش في تقرير الفروق')
        # نسبة الإشراف
        a.ev("OC.rows.push({id:'tp',kind:'tpl',data:ocDefTpl()});ocProj('s1').data.tpl='tp';ocProj('s1').data.admPct=30")
        a.go('__cost'); a.p.wait_for_timeout(500); a.check('مراجعة تكاليف مشروع نسبة إشراف')
        expect('مشروع بنسبة إشراف' in a.text() and 'صافي ربح الشركة' in a.text(), 'وضع نسبة الإشراف ما ظهرش')
        # عهدة المحاسب
        a.ev("CU.engs=null"); a.go('__custody'); a.p.wait_for_timeout(600)
        expect(a.ev("(CU.engs||[]).some(e=>e.id==='u-acct')"), 'المحاسب مش في قائمة صرف العهدة')
        a.check('الدفعة 1+2')
    finally:
        a.close()

def t_bq_visibility(b, port):
    """بند المقايسة ظاهر: فلتر «من غير بند مقايسة» + تنبيه + تسجيل جماعي + تفاصيل البند + كشف بند مقايسة + البند في اليومية."""
    a = App(b, port, b12_seed(), OWNER)
    try:
        a.go('__cost'); a.p.wait_for_timeout(600)
        a.ev("S.filt={c:'',i:'',b:'',from:'',to:'',q:''};S.kind='exp';S.tab='exp';S.siteTab='mov'"); a.go('s1'); a.p.wait_for_timeout(400)
        a.check('صفحة الموقع')
        t = a.text()
        expect('من غير بند مقايسة' in t and a.p.locator('#bqShow').count() == 1, 'تنبيه «من غير بند مقايسة» مش ظاهر')
        expect(a.p.locator('.bq-tag').count() >= 1, 'علامة بند المقايسة مش ظاهرة في الجدول')
        a.p.click('#bqShow'); a.p.wait_for_timeout(400)
        n0 = a.ev("S.exp.filter(e=>e.siteId==='s1'&&!e.deleted&&!e.boq).length")
        expect(a.ev("S.filt.b") == '__none' and a.p.locator('[data-bqpick]').count() >= 2, 'الفلتر / الاختيار ما اشتغلش')
        a.p.locator('[data-bqpick]').nth(0).check(); a.p.wait_for_timeout(150); a.p.locator('[data-bqpick]').nth(1).check(); a.p.wait_for_timeout(150)
        a.p.select_option('#bqTo', 'b1'); a.p.click('#bqApply'); a.p.wait_for_timeout(500)
        n1 = a.ev("S.exp.filter(e=>e.siteId==='s1'&&!e.deleted&&!e.boq).length")
        expect(n1 == n0 - 2, f'التسجيل الجماعي ما اشتغلش ({n0} → {n1})')
        # اليومية
        a.go('__journal'); a.p.wait_for_timeout(400); a.check('اليومية')
        expect(a.p.locator('.j-grp').count() >= 1, 'بند المقايسة / البند العام مش ظاهر في اليومية')
        # تفاصيل البند + كشف
        a.ev("CR.open=new Set(['ci1']);CR.oldOpen=true"); a.go('__cost'); a.p.wait_for_timeout(500)
        expect('مسجّل على البند' in a.text() and a.p.locator('[data-cr="bqdoc"]').count() >= 1, 'قائمة مصروفات البند مش في التفاصيل')
        d = a.ev("bqStmt('s1',['b1'])")
        expect('كشف بند مقايسة' in d['title'] and len(d['xl']) >= 3, f'كشف البند غلط: {d["title"]}')
        s = a.ev("bqStmt('s1',[])")
        expect('من غير بند مقايسة' in s['body'], 'الملخص ما فيهوش «من غير بند مقايسة»')
        a.ev("SP.type='bq';SP.site='s1'"); a.go('__stmts'); a.p.wait_for_timeout(500); a.check('التقارير ← بند مقايسة')
        expect('كشف بنود المقايسة' in a.text(), 'موضوع «بند مقايسة» في التقارير ما ظهرش')
        a.ev("CDP.tsite=''"); a.go('__items'); a.p.wait_for_timeout(600); a.check('صفحة البنود (الشجرة)')
        expect(a.p.locator('#cdtSite').count() == 1, 'اختيار «التقسيم» مش في الشجرة')
        a.p.select_option('#cdtSite', 's1'); a.p.wait_for_timeout(600); a.check('شجرة المقايسة')
        t = a.text()
        expect('بنود المقايسة من ملف المشروع' in t and 'مصروفات على الشركة' in t and 'خامات مشتركة' in t, 'شجرة بنود المقايسة ما ظهرتش')
        a.p.select_option('#cdtSite', ''); a.p.wait_for_timeout(500)
        expect(a.p.locator('#cdNewG').count() == 1, 'الرجوع للتقسيم المشترك ما اشتغلش')
    finally:
        a.close()

def t_overhead(b, port):
    """أوفر هيد وضريبة جوه تحليل السعر: مباشر + أوفر هيد + ضريبة = حد الصرف (إجمالي البند + للوحدة) وعمود حد الصرف في المراجعة."""
    a = App(b, port, cost_seed(), OWNER)
    try:
        a.go('__cost'); a.p.wait_for_timeout(600)
        if a.ev("CR.site") != 's1':
            a.p.select_option('#cr_site', 's1'); a.p.wait_for_timeout(300)
        a.p.click('[data-cr="new"]'); a.p.wait_for_timeout(200)
        a.p.select_option('#cr_boq', 'b1'); a.p.wait_for_timeout(300)
        a.p.click('[data-cr="partadd"]'); a.p.wait_for_timeout(200)
        a.p.fill('[data-crp="0"][data-k="name"]', 'مواد')
        a.p.fill('[data-crp="0"][data-k="per"]', '1'); a.p.fill('[data-crp="0"][data-k="price"]', '1000')
        a.p.click('[data-cr="partadd"]'); a.p.wait_for_timeout(200)
        a.p.fill('[data-crp="1"][data-k="name"]', 'Over Head 10%')
        a.p.fill('[data-crp="1"][data-k="per"]', '0.1'); a.p.fill('[data-crp="1"][data-k="price"]', '1000')
        a.p.click('[data-cr="partadd"]'); a.p.wait_for_timeout(200)
        a.p.fill('[data-crp="2"][data-k="name"]', 'ضريبة 14%')
        a.p.fill('[data-crp="2"][data-k="per"]', '0.14'); a.p.fill('[data-crp="2"][data-k="price"]', '1000')
        a.p.wait_for_timeout(200)
        a.p.click('[data-cr="save"]'); a.p.wait_for_timeout(700)
        rows = a.ev("window.__DB.cost_items||[]")
        expect(len(rows) == 1, f'البند ما اتحفظش ({rows})')
        k = a.ev("crCalc('s1',window.__DB.cost_items[0].data)")
        sp = k['split']
        expect(sp['has'] and sp['dir'] > 0, f'التقسيم ما اتحسبش: {sp}')
        expect(abs(sp['oh'] - 0.1 * sp['dir']) < 0.01 and abs(sp['tax'] - 0.14 * sp['dir']) < 0.01, f'أوفر هيد/ضريبة غلط: {sp}')
        expect(abs(k['lim'] - sp['dir']) < 0.01 and abs(sp['tot'] - 1.24 * sp['dir']) < 0.01, f'حد الصرف المفروض = المباشر بس: {k["lim"]} / {sp}')
        a.ev("CR.oldOpen=true;render()"); a.p.wait_for_timeout(200)
        expect('حد الصرف' in a.text() and 'المفروض يتصرف' in a.text(), 'عمود حد الصرف ما ظهرش في المراجعة')
        expect(abs(k['limExe'] - k['lim'] / k['qty'] * k['exe']) < 0.01, f'حد الصرف للمنفذ غلط: {k["limExe"]}')
        t0 = a.text()
        expect('المفروض يتصرف' in t0 and 'الضريبة المستحقة' in t0 and 'اتصرف (مسجّل + موزّع)' in t0, 'كروت الإجمالي الجديدة ما ظهرتش')
        a.p.click('[data-cr="tog"] >> nth=0'); a.p.wait_for_timeout(200)
        expect('إجمالي البند' in a.text(), 'تفاصيل البند ما فيهاش السطرين')
        a.p.click('[data-cr="tog"] >> nth=0'); a.p.wait_for_timeout(200)
        a.p.click('.cr-old [data-cr="edit"] >> nth=0'); a.p.wait_for_timeout(300)
        txt = a.text()
        expect('أوفر هيد للوحدة' in txt and 'ضريبة للوحدة' in txt and 'حد الصرف للوحدة (المباشر)' in txt, 'كروت التحليل ما ظهروش')
        expect(a.p.locator('table.cr-an').count() == 1, 'جدول التحليل مش متعلم بـ cr-an')
        a.p.click('[data-cr="cancel"]'); a.p.wait_for_timeout(200)
        a.p.click('[data-cr="tog"] >> nth=0'); a.p.wait_for_timeout(200)
        a.p.check('[data-cr="full"]'); a.p.wait_for_timeout(300)
        expect('حد الصرف' in a.text(), '«عرض كل الأعمدة» ما فيهوش حد الصرف')
        a.p.uncheck('[data-cr="full"]'); a.p.wait_for_timeout(200)
    finally:
        a.close()

def t_cost_review(b, port):
    """مراجعة التكاليف: البند من ملف المشروع، المنفذ من مستخلص المالك (× نسبة التنفيذ) واختيار المستخلص، وسعر الوحدة + الإجمالي."""
    a = App(b, port, cost_seed(), OWNER)
    try:
        a.go('__cost'); a.p.wait_for_timeout(600)
        if a.ev("CR.site") != 's1':
            a.p.select_option('#cr_site', 's1'); a.p.wait_for_timeout(300)
        expect(a.ev("CR.oc.s1||crCert('s1').id") == 'oc2', 'الافتراضي المفروض آخر مستخلص معتمد (رقم 2)')
        a.p.click('[data-cr="new"]'); a.p.wait_for_timeout(200)
        a.p.select_option('#cr_boq', 'b1'); a.p.wait_for_timeout(300)
        a.p.fill('[data-crd="0"][data-k="v"]', '10')
        a.p.click('[data-cr="pick"][data-w="i"]'); a.p.wait_for_timeout(200)
        a.p.select_option('#cr_pv', 'أعمال السباكة'); a.p.click('[data-cr="link"][data-w="i"]'); a.p.wait_for_timeout(200)
        a.p.click('[data-cr="partadd"]'); a.p.wait_for_timeout(200)
        a.p.fill('[data-crp="0"][data-k="name"]', 'حدادة')
        a.p.click('[data-cr="pick"][data-w="p0"]'); a.p.wait_for_timeout(200)
        a.p.select_option('#cr_pt', 'man'); a.p.wait_for_timeout(200)
        a.p.fill('#cr_ma', '5000'); a.p.click('[data-cr="link"][data-w="p0"]'); a.p.wait_for_timeout(200)
        a.p.click('[data-cr="save"]'); a.p.wait_for_timeout(700)
        rows = a.ev("window.__DB.cost_items||[]")
        expect(len(rows) == 1 and rows[0]['data'].get('boq') == 'b1', f'البند ما اتحفظش مربوط بملف المشروع ({rows})')
        k = a.ev("crCalc('s1',window.__DB.cost_items[0].data)")
        exp = a.ev("r2(S.exp.filter(e=>e.siteId==='s1'&&e.item==='أعمال السباكة').reduce((a,e)=>a+amt(e),0))")
        expect(k['contract'] == 100000 and k['allowed'] == 90000 and abs(k['allowU'] - 90000) < 0.01, f'الحساب غلط: {k}')
        expect(abs(k['exe'] - 0.8) < 1e-9, f'المنفذ المفروض 1 × 80٪ = 0.8 ولقيته {k["exe"]}')
        act = exp + 5000
        expect(abs(k['act'] - act) < 0.01 and abs(k['actU'] - act / 0.8) < 0.01, f'الفعلي للوحدة غلط {k["actU"]}')
        expect(abs(k['save'] - (90000 * 0.8 - act)) < 0.01, f'الوفر غلط {k["save"]}')
        a.p.select_option('#cr_oc', 'oc1'); a.p.wait_for_timeout(300)
        expect(abs(a.ev("crCalc('s1',window.__DB.cost_items[0].data).exe") - 0.5) < 1e-9, 'اختيار مستخلص رقم 1 ما غيّرش الكمية المنفذة')
        a.ev("CR.oldOpen=true;render()"); a.p.wait_for_timeout(200)
        txt = a.text()
        expect('الإجمالي' in txt and 'بنود المراجعة (1)' in txt and 'للوحدة' not in txt, 'الجدول المختصر (4 أعمدة) مش ظاهر')
        a.p.click('[data-cr="tog"] >> nth=0'); a.p.wait_for_timeout(200)
        expect('للوحدة:' in a.text(), '«تفاصيل» ما فتحتش أسعار الوحدة')
        a.p.check('[data-cr="full"]'); a.p.wait_for_timeout(300)
        expect('سعر التعاقد' in a.text(), '«عرض كل الأعمدة» ما رجّعش الجدول الكامل')
        a.p.uncheck('[data-cr="full"]'); a.p.wait_for_timeout(200)
        a.p.click('[data-cr="impoc"]'); a.p.wait_for_timeout(700)
        expect(len(a.ev("window.__DB.cost_items")) == 2, '«إضافة كل بنود ملف المشروع» ما ضافش البند الناقص')
        a.check('مراجعة التكاليف')
    finally:
        a.close()
    e = App(b, port, base_seed(), ENG)
    try:
        expect(not e.ev("crCanAny()"), 'المهندس شايف مراجعة التكاليف')
    finally:
        e.close()

def t_owner_boq(b, port):
    """مستخلص المالك بالمقايسة: النموذج الافتراضي، سطور المشروع (ضريبة/تأمين/دفعة مقدمة) والملاحظة، بند جديد يتضاف لملف المشروع، وتسجيل البنود كبنود عامة."""
    a = App(b, port, base_seed(), OWNER)
    try:
        a.go('__ocert'); a.p.wait_for_timeout(500)
        a.ev("OC.site='s1';OC.tab='proj';render()"); a.p.wait_for_timeout(300)
        a.p.click('[data-oc="pnew"]'); a.p.wait_for_timeout(800)
        D = a.ev("window.__DB.owner_docs||[]")
        tpl = [r for r in D if r['kind'] == 'tpl']; pj = [r for r in D if r['kind'] == 'proj']
        expect(len(tpl) == 1 and tpl[0]['data'].get('type') == 'boq' and len(pj) == 1, f'النموذج الافتراضي مش «بالمقايسة» ({[r["kind"] for r in D]})')
        a.ev("OC.tab='proj';OC.pe=null;render()"); a.p.wait_for_timeout(300)
        expect('الإجمالي والضرائب والدفعة المقدمة' in a.text(), 'كارت سطور الإجمالي مش ظاهر في ملف المشروع')
        expect(a.ev("S.sites.find(x=>x.id==='s1').igMode") == 'boq', 'مشروع بالمقايسة جديد ما حوّلش البنود العامة لـ«من المقايسة»')
        a.ev("OC.fold={rows:true,head:true,secs:true};OC.pe.secs=[{id:'sc1',title:'الأعمال الصحية',g:'',parts:{}}];OC.pe.boq=[{id:'b1',s:'sc1',desc:'أعمال السباكة',unit:'م',cq:100,rate:1000}];render()"); a.p.wait_for_timeout(200)
        expect('1.1' in a.text(), 'ترقيم البنود (1.1) مش ظاهر في ملف المشروع')
        i_adv = a.ev("OC.pe.rows.findIndex(r=>r.k==='adv')")
        expect(not a.ev(f"!!document.querySelector('[data-pe=\"rows.{i_adv}.label\"]')"), 'سطر غير متعلّم (الدفعة المقدمة) ظاهر في الجدول')
        a.p.select_option('#oc_radd', f'on:{i_adv}'); a.p.click('[data-oc="raddsel"]'); a.p.wait_for_timeout(300)
        a.p.fill('[data-pe="adv.amt"]', '20000'); a.p.fill('[data-pe="adv.pct"]', '10')
        a.p.select_option('#oc_radd', 'tax'); a.p.click('[data-oc="raddsel"]'); a.p.wait_for_timeout(300)
        i_tax = a.ev("OC.pe.rows.findIndex(r=>r.label==='ضريبة أخرى')")
        expect(i_tax > 0, '«+ ضريبة» ما ضافش «ضريبة أخرى»')
        a.p.fill(f'[data-pe="rows.{i_tax}.def"]', '1')
        a.p.fill('#oc_note', 'الأسعار شاملة النقل')
        a.p.click('[data-oc="psave"]'); a.p.wait_for_timeout(800)
        P = [r for r in a.ev("window.__DB.owner_docs") if r['kind'] == 'proj'][0]['data']
        expect(P.get('note') == 'الأسعار شاملة النقل' and P.get('adv', {}).get('amt') == 20000 and isinstance(P.get('rows'), list), f'إعدادات المشروع ما اتحفظتش ({P.get("adv")}, {P.get("note")})')
        a.ev("OC.tab='certs';render()"); a.p.wait_for_timeout(300)
        a.p.click('[data-oc="cnew"]'); a.p.wait_for_timeout(900)
        expect(a.ev("!!OC.ce"), 'المستخلص الجديد ما اتفتحش')
        txt = a.text()
        expect('المصنعيات' not in txt and 'سجّله' not in txt, 'نموذج المقايسة لسه فيه أجزاء مصنعيات أو زرار «سجّله»')
        expect('المراجعة قبل المستخلص' not in txt and 'مصاريف الشركة' not in txt and 'نماذج المستخلصات' not in txt, 'تابات مالهاش لزوم ظاهرة في مشروع المقايسة')
        a.ev("const l=OC.ce.data.lines.find(x=>x.boq==='b1');l.totQ=50;OC.dirty=true;render()"); a.p.wait_for_timeout(200)
        K = a.ev("(()=>{const P=ocProj('s1'),T=ocTplOf(P),K=ocCalc(OC.ce,P,T);return Object.fromEntries(K.rows.map(r=>[r.id,r.v]))})()")
        expect(abs(K['w'] - 50000) < .01 and abs(K['vat'] - 7000) < .01 and abs(K['ret'] + 2500) < .01 and abs(K['adv'] + 5000) < .01, f'حساب سطور الإجمالي غلط {K}')
        expect('sv' not in K and 'stp' not in K, f'سطور غير متعلمة اتحسبت {K}')
        expect(any(abs(v - 500) < .01 for k, v in K.items() if k.startswith('r')), f'«ضريبة أخرى» 1٪ ما اتحسبتش {K}')
        expect('الأسعار شاملة النقل' in a.text(), 'الملاحظة العامة مش ظاهرة في المستخلص')
        a.p.click('[data-oc="nbopen"] >> nth=0'); a.p.wait_for_timeout(200)
        a.p.fill('#ocnb_desc', 'أعمال الصرف'); a.p.fill('#ocnb_unit', 'م.ط'); a.p.fill('#ocnb_cq', '30'); a.p.fill('#ocnb_rate', '200')
        a.p.click('[data-oc="nbsave"]'); a.p.wait_for_timeout(800)
        P = [r for r in a.ev("window.__DB.owner_docs") if r['kind'] == 'proj'][0]['data']
        expect(any(x['desc'] == 'أعمال الصرف' for x in P['boq']), '«+ بند جديد» ما اتضافش لملف المشروع')
        expect(a.ev("OC.ce.data.lines.some(l=>l.desc==='أعمال الصرف'&&l.boq)"), '«+ بند جديد» ما اتضافش للمستخلص')
        names = a.ev("igNames(igPfOfSite('s1'))")
        expect(names == ['1.1 أعمال السباكة', '1.2 أعمال الصرف'], f'البنود العامة المفروض = بنود المقايسة بالترقيم ({names})')
        expect(a.ev("igGroups(igPfOfSite('s2')).every(g=>g.name!=='أعمال الصرف')"), 'التسجيل أثّر على موقع تاني')
        a.p.click('[data-oc="csave"]'); a.p.wait_for_timeout(800)
        body = a.ev("ocDocBody(ocCerts('s1')[0]).body")
        expect('الأسعار شاملة النقل' in body and 'oc-pgnote' in body and 'المصنعيات' not in body, 'الطباعة: الملاحظة أو أجزاء المصنعيات')
        expect(a.ev("crBoqList('s1')[0].code") == '1.1', 'ترقيم البنود في مراجعة التكاليف')
        a.check('مستخلص المالك بالمقايسة')
    finally:
        a.close()

def t_fixes27(b, port):
    """تصليحات 27 نوفمبر: حذف قسم في ملف المشروع، أقسام المشروع الجديد من بنود الموقع، قايمة المواقع ما تطلعش برا عمودها، وجدول مراجعة التكاليف."""
    seed = cost_seed()
    a = App(b, port, seed, OWNER)
    try:
        a.p.set_viewport_size({'width': 1100, 'height': 800})
        a.ev("S.sites[0].name='مخزن PharmaOverSeas — فيلا د.ممدوح التجمع الخامس';render()"); a.p.wait_for_timeout(300)
        over = a.ev("[...document.querySelectorAll('.rail .site-btn')].some(e=>e.scrollWidth>e.clientWidth+1)")
        expect(not over, 'اسم موقع طويل بيطلع برا عمود المواقع')
        a.go('__cost'); a.p.wait_for_timeout(1000)
        a.p.click('[data-cr="impoc"]'); a.p.wait_for_timeout(800)
        a.ev("CR.oldOpen=true;render()"); a.p.wait_for_timeout(200)
        expect(a.ev("!!document.querySelector('.cr-t [data-cr=edit]')"), 'زرار «تعديل» مش ظاهر في جدول مراجعة التكاليف')
        a.go('__ocert'); a.p.wait_for_timeout(500)
        a.ev("OC.site='s1';OC.tab='proj';OC.pe=null;OC.fold={secs:true};render()"); a.p.wait_for_timeout(400)
        a.ev("OC.pe.secs.push({id:'scX',title:'قسم قديم',g:'',parts:{}});render()"); a.p.wait_for_timeout(200)
        a.p.once('dialog', lambda d: d.accept())
        a.p.click('[data-oc="sdel"][aria-label="حذف القسم قسم قديم"]'); a.p.wait_for_timeout(300)
        expect(a.ev("!OC.pe.secs.some(s=>s.id==='scX')"), '«حذف القسم» ما اشتغلش')
        n0 = a.ev("OC.pe.secs.length")
        a.p.click('[data-oc="sdel"] >> nth=0'); a.p.wait_for_timeout(300)
        expect(a.ev("OC.pe.secs.length") == n0, 'قسم عليه كميات في مستخلص اتحذف')
        a.ev("S.sites.find(x=>x.id==='s1').igMode='off'")
        d = a.ev("ocNewProjData(S.sites.find(x=>x.id==='s1'),'')")
        expect(len(d['secs']) == 0, f'مشروع جديد لموقع «بدون بنود عامة» جه بأقسام ({d["secs"]})')
        a.ev("OC.rows.push({id:'tq',kind:'tpl',data:ocBoqTpl()})")
        a.ev("S.sites.find(x=>x.id==='s1').igMode=''")
        expect(len(a.ev("ocNewProjData(S.sites.find(x=>x.id==='s1'),'tq').secs")) == 0, 'نموذج بالمقايسة المفروض يبدأ من غير أقسام')
        a.ev("igSiteMode(S.sites.find(x=>x.id==='s1'),'own');igSiteNew(S.sites.find(x=>x.id==='s1'),'مجموعة خاصة',['أعمال السباكة'])"); a.p.wait_for_timeout(500)
        expect(a.ev("igOf('أعمال السباكة',igPfOfSite('s1'))") == 'مجموعة خاصة', 'التقسيم الخاص ما اتطبقش')
        mv = a.ev("(()=>{const s=S.sites.find(x=>x.id==='s1'),P={data:{secs:[{id:'q1',g:'مجموعة خاصة',title:'مجموعة خاصة',parts:{}}],boq:[]}};return ocMoves(s,P,{data:ocDefTpl()}).filter(m=>m.s==='q1').length})()")
        expect(mv > 0, 'مستخلص المالك لسه بيقسّم الحركات بالتقسيم المشترك مش الخاص بالموقع')
        a.check('تصليحات 27 نوفمبر')
    finally:
        a.close()

def abc_seed():
    s = cost_seed()
    L = lambda q: [{'id': 'l1', 's': 'sc1', 'boq': 'b1', 'desc': 'أعمال السباكة', 'unit': 'مقطوعية', 'cq': 1, 'rate': 100000, 'totQ': q, 'pct': 100}]
    s['owner_docs'].append({'id': 'oc3', 'kind': 'cert', 'site_id': 's1', 'data': {'no': 3, 'date': d(1), 'status': 'approved', 'lines': L(1)}})
    s['docs'].append(doc('items/g1', {'name': 'الأعمال الصحية', 'kind': 'group', 'items': ['أعمال السباكة'], 'created': 5}))
    s['docs'].append(doc('items/g2', {'name': 'أعمال متنوعة', 'kind': 'group', 'items': ['أعمال السباكة', 'توريدات حديد'], 'created': 6}))
    return s

def t_batch_abc(b, port):
    """دفعات أ وب وج: حذف آخر مستخلص (المعتمد برقمه) ومنع اللي في النص، حذف ملف المشروع، تكرار البنود، البنود العامة من المقايسة، والمصاريف الإدارية."""
    rpc = "owner_cert_delete:(a,DB)=>{DB.owner_docs=DB.owner_docs.filter(r=>r.id!==a.p_id);return 'ok'},owner_proj_delete:(a,DB)=>{const n=DB.owner_docs.length;DB.owner_docs=DB.owner_docs.filter(r=>r.site_id!==a.p_site||!['cert','proj'].includes(r.kind));return n-DB.owner_docs.length}"
    a = App(b, port, abc_seed(), OWNER, rpc_js=rpc)
    try:
        # تكرار البنود
        expect(a.ev("igDups('').length") == 1, 'البند المكرر تحت بندين عامين مااتكتشفش')
        a.ev("S.siteTab='sum';CK.igsite=true"); a.go('s1'); a.p.wait_for_timeout(500)
        expect('بنود تحت أكتر من بند عام' in a.text(), 'تنبيه التكرار مش ظاهر في كارت البنود العامة')
        a.p.click('[data-igs="dfix"]'); a.p.wait_for_timeout(400)
        expect(a.ev("igDups('').length") == 0 and a.ev("igOf('أعمال السباكة','')") == 'الأعمال الصحية', 'تصليح التكرار ما اشتغلش')
        a.p.on('dialog', lambda dg: dg.accept('توريدات حديد'))
        a.p.click('[data-igs="mode"][data-v="own"]'); a.p.wait_for_timeout(400)
        a.p.click('[data-igs="new"]'); a.p.wait_for_timeout(300)
        expect('فيه بند مصروفات اسمه' in a.text(), 'بند عام بنفس اسم بند مصروفات اتعمل من غير تنبيه')
        # البنود العامة من المقايسة
        a.p.click('[data-igs="mode"][data-v="boq"]'); a.p.wait_for_timeout(500)
        expect(a.ev("igNames(igPfOfSite('s1'))") == ['1.1 أعمال السباكة', '1.2 توريدات حديد'], 'البنود العامة مش بنود المقايسة')
        a.p.click('[data-igs="badd"] >> nth=0'); a.p.wait_for_timeout(200)
        a.p.select_option('#igs_item', 'أعمال السباكة'); a.p.click('[data-igs="bitem"]'); a.p.wait_for_timeout(400)
        expect(a.ev("igOf('أعمال السباكة',igPfOfSite('s1'))") == '1.1 أعمال السباكة', 'إضافة بند مصروفات تحت بند المقايسة ما اشتغلتش')
        expect(a.ev("igOf('أعمال السباكة',igPfOfSite('s2'))") == 'الأعمال الصحية', 'وضع المقايسة أثّر على موقع تاني')
        # مراجعة التكاليف: ربط تلقائي + المصاريف الإدارية
        a.go('__cost'); a.p.wait_for_timeout(900); a.p.click('[data-cr="impoc"]'); a.p.wait_for_timeout(800)
        sab = a.ev("r2(S.exp.filter(e=>e.siteId==='s1'&&e.item==='أعمال السباكة').reduce((a,e)=>a+amt(e),0))")
        k1 = a.ev("crK('s1',crCert('s1')).K.find(x=>x.d.boq==='b1').k")
        expect(abs(k1['act'] - sab) < .01 and len(k1['auto']) == 1, f'الربط التلقائي من البنود العامة غلط ({k1["act"]} / {sab})')
        a.p.check('[data-cr="admon"]'); a.p.wait_for_timeout(500)
        a.p.click('[data-cr="admopen"]'); a.p.wait_for_timeout(200)
        a.p.select_option('#cr_admit', 'توريدات حديد'); a.p.click('[data-cr="admadd"]'); a.p.wait_for_timeout(500)
        C = a.ev("(()=>{const c=crK('s1',crCert('s1'));return {admT:c.admT,K:c.K.map(x=>({d:x.k.direct,a:x.k.adm,t:x.k.act}))}})()")
        hed = a.ev("r2(S.exp.filter(e=>e.siteId==='s1'&&e.item==='توريدات حديد').reduce((a,e)=>a+amt(e),0))")
        expect(abs(C['admT'] - hed) < .01, f'إجمالي المصاريف الإدارية غلط {C}')
        expect(abs(sum(x['a'] for x in C['K']) - hed) < .02 and all(abs(x['t'] - x['d'] - x['a']) < .01 for x in C['K']), f'توزيع المصاريف الإدارية غلط {C}')
        expect(a.ev("crUnlinked('s1').list.every(([n])=>!/توريدات حديد/.test(n))"), 'بنود المصاريف الإدارية ظاهرة «غير داخلة في أي بند»')
        # حذف مستخلص المالك
        a.go('__ocert'); a.p.wait_for_timeout(500); a.ev("OC.site='s1';OC.tab='certs';OC.cur=null;render()"); a.p.wait_for_timeout(400)
        expect(a.ev("document.querySelectorAll('[data-oc=cdelask]').length") == 1, 'زرار الحذف المفروض على آخر مستخلص بس')
        a.ev("OC.cur='oc2';render()"); a.p.wait_for_timeout(400)
        expect(a.ev("!document.querySelector('[data-oc=creopen]')"), '«فتح الاعتماد» متاح لمستخلص بعده مستخلصات')
        a.ev("OC.cur=null;render()"); a.p.wait_for_timeout(300)
        a.p.click('[data-oc="cdelask"]'); a.p.wait_for_timeout(200)
        a.p.fill('#oc_delno', '2'); a.p.click('[data-oc="cdelok"]'); a.p.wait_for_timeout(500)
        expect(len([r for r in a.ev("window.__DB.owner_docs") if r['kind'] == 'cert']) == 3, 'المستخلص المعتمد اتحذف برقم تأكيد غلط')
        a.p.fill('#oc_delno', '3'); a.p.click('[data-oc="cdelok"]'); a.p.wait_for_timeout(600)
        expect(not any(r['id'] == 'oc3' for r in a.ev("window.__DB.owner_docs")), 'حذف آخر مستخلص ما اشتغلش')
        expect(a.ev("document.querySelectorAll('[data-oc=cdelask]').length") == 1 and a.ev("ocCerts('s1').length") == 2, 'بعد الحذف المستخلص اللي قبله المفروض يبقى آخر واحد')
        a.ev("OC.tab='proj';OC.pe=null;render()"); a.p.wait_for_timeout(400)
        a.p.fill('#oc_pdname', 'غلط'); a.p.click('[data-oc="pdel"]'); a.p.wait_for_timeout(400)
        expect(a.ev("!!ocProj('s1')"), 'ملف المشروع اتحذف باسم موقع غلط')
        nm = a.ev("S.sites.find(x=>x.id==='s1').name")
        a.p.fill('#oc_pdname', nm); a.p.click('[data-oc="pdel"]'); a.p.wait_for_timeout(600)
        expect(not any(r['site_id'] == 's1' and r['kind'] in ('cert', 'proj') for r in a.ev("window.__DB.owner_docs")), 'حذف ملف المشروع بمستخلصاته ما اشتغلش')
        a.check('دفعات أ وب وج')
    finally:
        a.close()

def t_batch_d(b, port):
    """الدفعة د: تابات الموقع (التكاليف ومستخلص المالك جوه صفحة الموقع)، القائمة الرئيسية من غيرهم، خيارات الموقع مختصرة، وفورم المصروف ورا زرار."""
    a = App(b, port, cost_seed(), OWNER)
    try:
        a.go('s1'); a.p.wait_for_timeout(700)
        tabs = a.ev("[...document.querySelectorAll('.site-tabs button')].map(x=>x.textContent.trim())")
        expect('مستخلص المالك' in tabs and 'التكاليف' in tabs, f'تابات الموقع ناقصة ({tabs})')
        expect(not a.ev("!!document.getElementById('entryForm')"), 'فورم المصروف مفتوح على طول')
        a.p.click('[data-entry="exp"]'); a.p.wait_for_timeout(300)
        expect(a.ev("!!document.getElementById('entryForm')"), '«+ تسجيل مصروف» ما فتحش الفورم')
        menu = a.ev("document.getElementById('siteMenu').textContent")
        expect('مراجعة التكاليف' not in menu and 'مخزن الموقع' not in menu and 'كشف الحساب' not in menu, 'خيارات الموقع لسه فيها حاجات مكررة')
        main = a.ev("document.querySelector('.pop-tools').textContent")
        expect('مستخلص المالك' not in main and 'مراجعة التكاليف' not in main and 'التقارير' in main, 'القائمة الرئيسية لسه فيها مستخلص المالك/مراجعة التكاليف')
        a.p.click('.site-tabs [data-crgo]'); a.p.wait_for_timeout(1200)
        expect(a.ev("S.sel") == '__cost' and a.ev("!!document.querySelector('.site-bar')"), 'تاب التكاليف ما فتحش بشريط الموقع')
        a.p.click('.site-bar ~ .site-tabs [data-tab2="sum"]'); a.p.wait_for_timeout(500)
        expect(a.ev("S.sel") == 's1' and a.ev("S.siteTab") == 'sum', 'الرجوع لتاب الملخص من شريط الموقع ما اشتغلش')
        a.check('الدفعة د')
    finally:
        a.close()

TESTS = [('owner', t_owner_pages), ('paging', t_load_paging), ('custody', t_custody_pager), ('certs', t_certs_pager),
         ('engineer', t_engineer), ('tech', t_tech), ('limits', t_limits), ('limits_quiet', t_limits_quiet),
         ('journal', t_journal), ('reports', t_reports), ('mobile_ui', t_mobile_ui), ('errors', t_errors), ('resync', t_resync), ('stuck', t_stuck_queue),
         ('retention', t_cert_retention), ('site_groups', t_site_groups), ('cost', t_cost_review), ('owner_boq', t_owner_boq), ('fixes27', t_fixes27), ('abc', t_batch_abc), ('batch_d', t_batch_d), ('overhead', t_overhead), ('batch12', t_batch12), ('bqvis', t_bq_visibility), ('qtyconc', t_qtyconc), ('batch14', t_batch14), ('simplify', t_simplify), ('cost_new', t_cost_new)]

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
