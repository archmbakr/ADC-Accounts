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
        a.p.click('#hdrSync')
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

def t_cost_review(b, port):
    """مراجعة التكاليف: بند بخصم وربط بند مصروفات ومبلغ يدوي في تحليل السعر، والحفظ والحساب صح."""
    a = App(b, port, base_seed(), OWNER)
    try:
        a.go('__cost'); a.p.wait_for_timeout(400)
        if a.ev("CR.site") != 's1':
            a.p.select_option('#cr_site', 's1'); a.p.wait_for_timeout(200)
        a.p.click('[data-cr="new"]'); a.p.wait_for_timeout(200)
        a.p.fill('#cr_name', 'أعمال السباكة'); a.p.fill('#cr_unit', 'مقطوعية'); a.p.fill('#cr_qty', '1'); a.p.fill('#cr_rate', '100000')
        a.p.fill('[data-crd="0"][data-k="v"]', '10')
        a.p.click('[data-cr="pick"][data-w="i"]'); a.p.wait_for_timeout(200)
        a.p.select_option('#cr_pv', 'أعمال السباكة'); a.p.click('[data-cr="link"][data-w="i"]'); a.p.wait_for_timeout(200)
        a.p.click('[data-cr="partadd"]'); a.p.wait_for_timeout(200)
        a.p.fill('[data-crp="0"][data-k="name"]', 'حدادة')
        a.p.click('[data-cr="pick"][data-w="p0"]'); a.p.wait_for_timeout(200)
        a.p.select_option('#cr_pt', 'man'); a.p.wait_for_timeout(200)
        a.p.fill('#cr_ma', '5000'); a.p.fill('#cr_mx', 'دفعات حداد'); a.p.click('[data-cr="link"][data-w="p0"]'); a.p.wait_for_timeout(200)
        a.p.click('[data-cr="save"]'); a.p.wait_for_timeout(600)
        rows = a.ev("window.__DB.cost_items||[]")
        expect(len(rows) == 1 and rows[0]['site_id'] == 's1', f'البند ما اتحفظش ({len(rows)})')
        k = a.ev("crCalc('s1',window.__DB.cost_items[0].data)")
        exp = a.ev("r2(S.exp.filter(e=>e.siteId==='s1'&&e.item==='أعمال السباكة').reduce((a,e)=>a+amt(e),0))")
        expect(k['contract'] == 100000 and k['dedT'] == 10000 and k['allowed'] == 90000, f'الحساب غلط: {k}')
        expect(abs(k['act'] - (exp + 5000)) < 0.01, f'المصروف فعلًا {k["act"]} والمتوقع {exp + 5000}')
        txt = a.text()
        expect('بنود المقايسة (1)' in txt and 'غير داخلة في أي بند' in txt, 'الجدول أو تنبيه غير المربوط مش ظاهر')
        a.check('مراجعة التكاليف')
    finally:
        a.close()
    e = App(b, port, base_seed(), ENG)
    try:
        expect(not e.ev("crCanAny()"), 'المهندس شايف مراجعة التكاليف')
    finally:
        e.close()

TESTS = [('owner', t_owner_pages), ('paging', t_load_paging), ('custody', t_custody_pager), ('certs', t_certs_pager),
         ('engineer', t_engineer), ('tech', t_tech), ('limits', t_limits), ('limits_quiet', t_limits_quiet),
         ('journal', t_journal), ('reports', t_reports), ('mobile_ui', t_mobile_ui), ('errors', t_errors), ('resync', t_resync), ('stuck', t_stuck_queue),
         ('retention', t_cert_retention), ('site_groups', t_site_groups), ('cost', t_cost_review)]

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
