"""SkillsCompare SA - prototype. Run: python app.py  (Flask + SQLite, no other deps)."""
import os, sqlite3, csv, io, secrets, random, datetime as dt
from functools import wraps
from flask import Flask, g, session, request, redirect, url_for, render_template, abort, flash, Response, send_from_directory
from jinja2 import DictLoader
from markupsafe import Markup
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__)); DB = os.path.join(BASE, 'skillscompare.db'); UP = os.path.join(BASE, 'uploads')
os.makedirs(UP, exist_ok=True)
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-only-change-me')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                  SESSION_COOKIE_SECURE=bool(os.environ.get('HTTPS')), MAX_CONTENT_LENGTH=5 * 1024 * 1024)

# ---------------------------------------------------------------- data layer
SCHEMA = """
create table orgs(id integer primary key, name text, type text, city text, province text, status text, email text, kind text);
create table users(id integer primary key, email text unique, pw text, role text, name text, org_id integer references orgs(id));
create table categories(id integer primary key, name text unique);
create table courses(id integer primary key, org_id integer references orgs(id), cat_id integer references categories(id),
  title text, summary text, outcomes text, days integer, mode text, city text, province text, capacity integer,
  price_type text, price integer, price_unit text, status text);            -- price_type fixed|quote ; price_unit learner|cohort
create table credentials(id integer primary key, org_id integer, course_id integer, kind text, authority text, scope text,
  method text, checked_on text, valid_from text, expires_on text, status text, evidence text);
create table enquiries(id integer primary key, course_id integer, user_id integer, learners integer, dates text, req_cred text,
  budget integer, message text, contact_name text, contact_email text, contact_phone text, consent_text text, consent_at text,
  status text, created text);
create table notifications(id integer primary key, to_email text, subject text, body text, at text);
create table subscriptions(id integer primary key, org_id integer, plan text, status text);
create table events(id integer primary key, kind text, cat_id integer, province text, at text);   -- no user id: anonymised
create table audit(id integer primary key, actor text, action text, target text, detail text, at text);
"""
CATS = ['Leadership & management', 'Project management', 'Occupational health & safety', 'IT, AI & digital skills', 'Learnerships & occupational qualifications']
# name, type, city, province  (all fictional)
PROVS = [('Highveld Project Academy', 'private', 'Johannesburg', 'Gauteng'), ('Sandton Leadership Institute', 'exec-ed', 'Sandton', 'Gauteng'),
 ('Pretoria Safety & Risk Training', 'qcto', 'Pretoria', 'Gauteng'), ('Rand Digital Skills Hub', 'private', 'Johannesburg', 'Gauteng'),
 ('Jacaranda University Continuing Education', 'university', 'Pretoria', 'Gauteng'), ('Midrand Technical & Vocational College', 'tvet', 'Midrand', 'Gauteng'),
 ('Gold Reef Learnerships', 'qcto', 'Johannesburg', 'Gauteng'), ('Table Bay Executive School', 'exec-ed', 'Cape Town', 'Western Cape'),
 ('Durban Coastal Skills', 'private', 'Durban', 'KwaZulu-Natal'), ('Ekurhuleni OHS Academy', 'qcto', 'Germiston', 'Gauteng'),
 ('Centurion AI & Data Lab', 'private', 'Centurion', 'Gauteng'), ('Southern Cross University of Technology Short Courses', 'university', 'Johannesburg', 'Gauteng'),
 ('Meadowlands Skills College', 'tvet', 'Soweto', 'Gauteng'), ('Apex PM Consulting', 'private', 'Johannesburg', 'Gauteng'),
 ('Leadership Lab Africa', 'exec-ed', 'Johannesburg', 'Gauteng')]
# provider#, cat#, title, days, mode, price (None = quote only), unit, capacity
C = [(1,2,'Project Management Fundamentals',5,'blended',9500,'learner',30),(1,2,'Agile & Scrum for Teams',3,'onsite',None,'cohort',25),
(14,2,'PM for Non-Project Managers',3,'onsite',7200,'learner',20),(14,2,'Advanced Project Leadership',4,'blended',None,'cohort',24),
(12,2,'Certificate in Project Management',30,'blended',18500,'learner',40),(5,2,'Project Management Short Course',10,'online',6800,'learner',50),
(8,2,'Strategic Programme Management',5,'onsite',24500,'learner',25),(2,1,'Leading High-Performing Teams',3,'onsite',12500,'learner',20),
(2,1,'Executive Leadership Programme',10,'blended',None,'cohort',30),(15,1,'First-Time Manager Essentials',2,'onsite',4800,'learner',25),
(15,1,'Coaching Skills for Leaders',2,'blended',None,'cohort',20),(8,1,'Senior Leadership Development',8,'blended',48000,'learner',30),
(5,1,'Management Development Programme',20,'online',11900,'learner',60),(12,1,'Emerging Leaders Certificate',15,'blended',9800,'learner',40),
(13,1,'Supervisory Skills',3,'onsite',3200,'learner',30),(2,1,'Negotiation Skills',2,'onsite',5600,'learner',20),(15,1,'Change Leadership',2,'blended',None,'cohort',25),
(3,3,'SHE Representative Training',2,'onsite',1850,'learner',30),(3,3,'Incident Investigation',2,'onsite',None,'cohort',20),(10,3,'First Aid Level 1-2',3,'onsite',1450,'learner',16),
(10,3,'Working at Heights',1,'onsite',1200,'learner',12),(10,3,'OHS Compliance for Managers',2,'blended',None,'cohort',25),(6,3,'Safety Officer Short Course',5,'onsite',3900,'learner',30),
(9,3,'Fire Marshal & Evacuation',1,'onsite',950,'learner',25),(3,3,'Hazard Identification & Risk Assessment',2,'onsite',2400,'learner',25),
(4,4,'Excel for Business Analysis',3,'blended',2800,'learner',24),(4,4,'Power BI Fundamentals',3,'online',3400,'learner',30),(11,4,'AI for Business Leaders',2,'blended',6500,'learner',25),
(11,4,'Python for Data Analysis',5,'online',None,'cohort',20),(11,4,'Cybersecurity Awareness',1,'online',18000,'cohort',100),(5,4,'Digital Transformation Certificate',12,'online',14500,'learner',80),
(12,4,'Data Analytics Short Course',10,'blended',12900,'learner',40),(6,4,'End-User Computing',5,'onsite',2200,'learner',30),(4,4,'Generative AI Workshop',1,'onsite',4200,'learner',30),
(7,5,'Business Administration Learnership (NQF 3)',365,'blended',None,'cohort',30),(7,5,'Project Support Learnership (NQF 4)',365,'blended',None,'cohort',25),
(13,5,'Generic Management Learnership (NQF 5)',365,'onsite',None,'cohort',30),(6,5,'Occupational Certificate: Office Administration',240,'onsite',None,'cohort',25),
(10,5,'OHS Occupational Qualification',180,'onsite',None,'cohort',20),(9,5,'Customer Service Learnership',365,'blended',None,'cohort',30)]
OUT = {1: 'Plan, schedule and track a project; manage scope and risk; report to stakeholders', 2: 'Lead teams, give feedback and manage performance',
       3: 'Meet legal safety duties; identify hazards; respond to incidents', 4: 'Apply tools to real workplace data and processes', 5: 'Workplace-based qualification toward an occupational outcome'}
OUT = {2: OUT[1], 1: OUT[2], 3: OUT[3], 4: OUT[4], 5: OUT[5]}

def db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row; g.db.execute('pragma foreign_keys=on')
    return g.db
def q(sql, a=(), one=False):
    r = db().execute(sql, a).fetchall()
    return (r[0] if r else None) if one else r
def x(sql, a=()):
    c = db().execute(sql, a); db().commit(); return c.lastrowid
@app.teardown_appcontext
def _close(e):
    d = g.pop('db', None)
    if d: d.close()
now = lambda: dt.datetime.now().strftime('%Y-%m-%d %H:%M')
today = lambda: dt.date.today().isoformat()
def audit(action, target, detail=''):
    x('insert into audit(actor,action,target,detail,at) values(?,?,?,?,?)', (session.get('email', 'system'), action, target, detail, now()))
def mail(to, subject, body):  # stubbed transactional email: stored + logged, never sent
    x('insert into notifications(to_email,subject,body,at) values(?,?,?,?)', (to, subject, body, now())); print(f'[email-stub] to={to} subject={subject}')
def num(v):
    try: return int(v)
    except (TypeError, ValueError): return None

def seed():
    con = sqlite3.connect(DB); con.executescript(SCHEMA); r = random.Random(7)
    for c in CATS: con.execute('insert into categories(name) values(?)', (c,))
    for i, (n, t, city, pr) in enumerate(PROVS, 1):
        con.execute('insert into orgs values(?,?,?,?,?,?,?,?)', (i, n, t, city, pr, 'approved', f'leads@{n.split()[0].lower()}.example', 'provider'))
        con.execute('insert into subscriptions(org_id,plan,status) values(?,?,?)', (i, 'premium' if i % 4 == 0 else 'free', 'active'))
    con.execute("insert into orgs values(16,'Demo Mining & Logistics (Pty) Ltd','employer','Johannesburg','Gauteng','approved','hr@demo.example','employer')")
    con.execute("insert into orgs values(17,'SkillsCompare Admin','admin','','','approved','','admin')")
    con.execute("insert into orgs values(18,'Newcomer Training CC','private','Pretoria','Gauteng','pending','info@newcomer.example','provider')")
    for e, role, n, o in [('employer@demo.co.za', 'employer', 'Thandi Mokoena', 16), ('provider@demo.co.za', 'provider', 'Pieter van Wyk', 1),
                          ('admin@demo.co.za', 'admin', 'Admin User', 17), ('new@demo.co.za', 'provider', 'Nomsa Dlamini', 18)]:
        con.execute('insert into users(email,pw,role,name,org_id) values(?,?,?,?,?)', (e, generate_password_hash('demo1234'), role, n, o))
    for p, cat, t, d, m, pr, u, cap in C:
        o = PROVS[p - 1]
        con.execute('insert into courses(org_id,cat_id,title,summary,outcomes,days,mode,city,province,capacity,price_type,price,price_unit,status) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (p, cat, t, f'{t} delivered by {o[0]}.', OUT[cat], d, m, o[2], o[3], cap, 'quote' if pr is None else 'fixed', pr, u, 'listed'))
    ver, pend = {3, 5, 6, 7, 10, 12, 13}, {1, 2, 11}
    auth = {'qcto': 'QCTO / relevant SETA', 'university': 'DHET / CHE institutional registration', 'tvet': 'DHET public TVET college register',
            'private': 'DHET private college register', 'exec-ed': 'Claimed: international business-school body'}
    for i, (n, t, city, pr) in enumerate(PROVS, 1):
        kind = 'institutional_status' if t in ('university', 'tvet') else 'provider_accreditation'
        st = 'verified' if i in ver else 'pending' if i in pend else 'unverified'
        v = st == 'verified'
        con.execute('insert into credentials(org_id,course_id,kind,authority,scope,method,checked_on,valid_from,expires_on,status) values(?,?,?,?,?,?,?,?,?,?)',
                    (i, None, kind, auth[t], 'Organisation-level registration' if v else 'Provider-stated', 'Register lookup' if v else None,
                     '2026-11-03' if v else None, '2025-01-01', '2027-11-03' if v else None, st))
    for i, row in enumerate(C, 1):  # programme-level accreditation for learnerships
        if row[1] == 5:
            st = 'verified' if row[0] in (7, 10, 13) else 'pending' if row[0] == 6 else 'unverified'
            con.execute('insert into credentials(org_id,course_id,kind,authority,scope,method,checked_on,valid_from,expires_on,status) values(?,?,?,?,?,?,?,?,?,?)',
                        (row[0], i, 'programme_accreditation', 'QCTO', 'This qualification only', 'QCTO register lookup' if st == 'verified' else None,
                         '2026-11-03' if st == 'verified' else None, '2025-06-01', '2028-06-01' if st == 'verified' else None, st))
    con.execute("insert into credentials(org_id,course_id,kind,authority,scope,status) values(14,NULL,'professional_recognition','Claimed: PM professional body','Individual facilitators','unverified')")
    for cid, st in [(1, 'new'), (1, 'contacted'), (3, 'quoted')]:
        con.execute('insert into enquiries(course_id,user_id,learners,dates,message,contact_name,contact_email,contact_phone,consent_text,consent_at,status,created) values(?,?,?,?,?,?,?,?,?,?,?,?)',
                    (cid, 1, 25, 'Q1 2027', 'Sample seeded lead', 'Thandi Mokoena', 'employer@demo.co.za', '011 555 0100', CONSENT.format(org='seed'), now(), st, now()))
    for _ in range(120):
        con.execute('insert into events(kind,cat_id,province,at) values(?,?,?,?)', (r.choice(['search'] * 6 + ['compare'] * 2), r.randint(1, 5), r.choice(['Gauteng'] * 6 + ['Western Cape', 'KwaZulu-Natal']), now()))
    con.execute("insert into audit(actor,action,target,detail,at) values('system','seed_data','-','fictional demo data',?)", (now(),))
    con.commit(); con.close()

CONSENT = ('I consent to SkillsCompare SA sharing my name, email address and phone number (if provided) with {org} so they can respond to this enquiry. '
           'No other provider will receive them. I can withdraw consent by emailing privacy@skillscompare.example.')
KIND = {'provider_accreditation': 'Provider accreditation', 'programme_accreditation': 'Programme accreditation', 'institutional_status': 'Institutional status',
        'professional_recognition': 'Professional recognition'}

# ---------------------------------------------------------------- credentials, pricing, matching
def creds(c):
    rows = q("select * from credentials where org_id=? and (course_id is null or course_id=?) order by status='verified' desc", (c['org_id'], c['id']))
    out = []
    for k in rows:
        st = 'verified' if k['status'] == 'verified' and k['checked_on'] else 'pending' if k['status'] == 'pending' else 'unverified'  # never "verified" without a recorded check
        lbl = {'verified': '✔ Verified by SkillsCompare', 'pending': '⏳ Under review', 'unverified': '⚠ Unverified claim'}[st]
        out.append(dict(row=k, kind=KIND.get(k['kind'], k['kind']), state=st, label=lbl))
    return out
def cost(c, n):
    n = n or 1
    if c['price_type'] == 'quote' or c['price'] is None: return dict(quote=True, per=None, total=None, line='Request Quote', basis='Price on request: provider quotes after your enquiry')
    if c['price_unit'] == 'learner': return dict(quote=False, per=c['price'], total=c['price'] * n, line=f"R{c['price']:,} per learner", basis=f"≈ R{c['price'] * n:,} for {n} learners")
    return dict(quote=False, per=c['price'] / n, total=c['price'], line=f"R{c['price']:,} per cohort", basis=f"≈ R{c['price'] / n:,.0f} per learner at {n} learners (cohort up to {c['capacity']})")

def run_search(a):
    f = dict(q=a.get('q', '').strip().lower(), cat=num(a.get('cat')), province=a.get('province', ''), city=a.get('city', ''), modes=a.getlist('mode'),
             ptype=a.get('ptype', ''), cred=a.get('cred', ''), maxp=num(a.get('maxp')), maxd=num(a.get('maxd')), n=num(a.get('learners')) or 0)
    rows = q("select c.*,o.name org,o.type otype,k.name cat from courses c join orgs o on o.id=c.org_id join categories k on k.id=c.cat_id where c.status='listed' and o.status='approved'")
    out = []
    for r in rows:
        c = dict(r); s = 0; why = []; flags = []; online = c['mode'] == 'online'
        if f['cat'] and c['cat_id'] != f['cat']: continue
        if f['ptype'] and c['otype'] != f['ptype']: continue
        if f['modes'] and c['mode'] not in f['modes']: continue
        if f['maxd'] and c['days'] > f['maxd']: continue
        if f['province'] and c['province'] != f['province'] and not online: continue
        if f['city'] and c['city'] != f['city'] and not online: continue
        cs = creds(c); c['creds'] = cs; c['cost'] = cost(c, f['n'])
        if f['cred'] == 'verified' and not any(k['state'] == 'verified' for k in cs): continue
        if f['maxp'] and c['cost']['per'] and c['cost']['per'] > f['maxp']: continue
        words = f['q'].split()
        if words:
            t = c['title'].lower(); other = (c['summary'] + ' ' + c['cat'] + ' ' + c['outcomes']).lower()
            th = sum(w in t for w in words); oh = sum((w in other) and (w not in t) for w in words)
            if th + oh < len(words): continue  # every search word must match somewhere
            s += min(40, 15 * th + 8 * oh); why.append(f'Keyword match ({th} in title, {oh} in description) +{min(40, 15 * th + 8 * oh)}')
        else: s += 10
        if f['city'] and c['city'] == f['city']: s += 20; why.append(f"Based in {c['city']} +20")
        elif f['province'] and c['province'] == f['province']: s += 10; why.append(f"Delivers in {c['province']} +10")
        elif online: s += 10; why.append('Online: available in any region +10')
        if f['n']:
            if c['capacity'] >= f['n']: s += 10; why.append(f"Capacity for {f['n']} learners +10")
            else: s -= 10; flags.append(f"Max group {c['capacity']} is below {f['n']}: may need multiple intakes")
        if f['modes']: s += 15; why.append('Delivery format matches +15')
        if any(k['state'] == 'verified' for k in cs): s += 15; why.append('Credential checked by an admin +15')
        if f['maxp'] and c['cost']['per']: s += 10; why.append('Within your per-learner budget +10')
        if c['cost']['quote']: flags.append('Quote-only: budget fit cannot be checked until you enquire')
        c['score'] = s; c['why'] = why; c['flags'] = flags; out.append(c)
    return f, out

def need(*roles):
    def d(fn):
        @wraps(fn)
        def w(*a, **k):
            if not session.get('uid'): return redirect(url_for('login', next=request.path))
            if session['role'] not in roles: abort(403)
            return fn(*a, **k)
        return w
    return d
@app.before_request
def csrf_check():
    if request.method == 'POST' and (not session.get('csrf') or request.form.get('_csrf') != session['csrf']): abort(400)
@app.context_processor
def ctx():
    session.setdefault('csrf', secrets.token_hex(16))
    return dict(csrf=lambda: Markup(f'<input type="hidden" name="_csrf" value="{session["csrf"]}">'), cmpn=len(session.get('cmp', [])), user=session.get('email'), role=session.get('role'))

# ---------------------------------------------------------------- public / employer routes
@app.route('/')
def home():
    a = request.args; f, res = run_search(a)
    searched = any(a.get(k) for k in ('q', 'cat', 'city', 'province', 'mode', 'ptype', 'cred', 'maxp', 'maxd', 'learners'))
    if searched: x('insert into events(kind,cat_id,province,at) values(?,?,?,?)', ('search', f['cat'], f['province'] or None, now()))
    sort = a.get('sort', 'relevance')
    if sort == 'price': res.sort(key=lambda c: (c['cost']['per'] is None, c['cost']['per'] or 0))
    else: res.sort(key=lambda c: -c['score'])
    return render_template('home', res=res, f=f, a=a, sort=sort, searched=searched, cats=q('select * from categories'),
                           cities=[r[0] for r in q('select distinct city from orgs where kind="provider" order by 1')], n=f['n'])
@app.route('/course/<int:cid>')
def course(cid):
    c = getc(cid); n = num(request.args.get('learners')) or 0
    return render_template('course', c=c, cs=creds(c), cost=cost(c, n or 25), n=n or 25)
def getc(cid):
    c = q("select c.*,o.name org,o.type otype,o.email,k.name cat from courses c join orgs o on o.id=c.org_id join categories k on k.id=c.cat_id where c.id=? and c.status='listed' and o.status='approved'", (cid,), one=True)
    if not c: abort(404)
    return dict(c)
@app.post('/compare/add/<int:cid>')
def cmp_add(cid):
    getc(cid); l = session.get('cmp', [])
    if cid in l: pass
    elif len(l) >= 3: flash('You can compare up to 3 programmes. Remove one first.', 'err')
    else: l.append(cid); flash('Added to comparison.', 'ok')
    session['cmp'] = l; return redirect(request.referrer or url_for('compare'))
@app.post('/compare/remove/<int:cid>')
def cmp_rm(cid):
    session['cmp'] = [i for i in session.get('cmp', []) if i != cid]; return redirect(url_for('compare'))
@app.route('/compare')
def compare():
    n = num(request.args.get('learners')) or 25; items = []
    for cid in session.get('cmp', []):
        try: c = getc(cid)
        except Exception: continue
        c['cost'] = cost(c, n); c['creds'] = creds(c); items.append(c)
    if len(items) >= 2: x('insert into events(kind,cat_id,province,at) values(?,?,?,?)', ('compare', items[0]['cat_id'], items[0]['province'], now()))
    return render_template('compare', items=items, n=n)
@app.route('/enquire/<int:cid>', methods=['GET', 'POST'])
@need('employer')
def enquire(cid):
    c = getc(cid); f = request.form
    if request.method == 'POST':
        err = None
        if not f.get('consent'): err = 'Consent is required: without it we cannot share your contact details with this provider.'
        elif not f.get('name', '').strip() or '@' not in f.get('email', ''): err = 'Please give your name and a valid email address.'
        if err: flash(err, 'err'); return render_template('enquire', c=c, f=f, d=ud(), cs=CONSENT.format(org=c['org']))
        eid = x('insert into enquiries(course_id,user_id,learners,dates,req_cred,budget,message,contact_name,contact_email,contact_phone,consent_text,consent_at,status,created) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (cid, session['uid'], num(f.get('learners')), f.get('dates', '')[:100], f.get('req_cred', '')[:100], num(f.get('budget')), f.get('message', '')[:1000],
                 f['name'][:100], f['email'][:150], f.get('phone', '')[:30], CONSENT.format(org=c['org']), now(), 'new', now()))
        audit('consent_recorded', f'enquiry:{eid}', f"shared only with org {c['org_id']}")
        mail(c['email'], f"New enquiry #{eid}: {c['title']}", 'You have a new lead. Log in to your dashboard to view it. (Contact details are not sent by email.)')
        mail(f['email'], 'We have received your enquiry', f"Your enquiry #{eid} for {c['title']} was sent to {c['org']}.")
        return redirect(url_for('thanks', eid=eid))
    return render_template('enquire', c=c, f={}, d=ud(), cs=CONSENT.format(org=c['org']))
def ud(): return q('select * from users where id=?', (session['uid'],), one=True)
@app.route('/thanks/<int:eid>')
@need('employer')
def thanks(eid):
    e = q('select e.*,c.title,o.name org from enquiries e join courses c on c.id=e.course_id join orgs o on o.id=c.org_id where e.id=? and e.user_id=?', (eid, session['uid']), one=True)
    if not e: abort(404)
    return render_template('thanks', e=e)

# ---------------------------------------------------------------- auth
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = q('select * from users where email=?', (request.form.get('email', '').strip().lower(),), one=True)
        if u and check_password_hash(u['pw'], request.form.get('password', '')):
            session.clear(); session.update(uid=u['id'], role=u['role'], email=u['email'], org=u['org_id'], csrf=secrets.token_hex(16)); audit('login', f"user:{u['id']}")
            nxt = request.args.get('next', '')
            return redirect(nxt if nxt.startswith('/') and not nxt.startswith('//') else {'admin': '/admin', 'provider': '/provider'}.get(u['role'], '/'))
        flash('Incorrect email or password.', 'err')
    return render_template('login')
@app.post('/logout')
def logout(): session.clear(); return redirect('/')
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        f = request.form; e = f.get('email', '').strip().lower(); role = f.get('role')
        if role not in ('employer', 'provider') or '@' not in e or len(f.get('password', '')) < 8 or not f.get('org', '').strip() or not f.get('name', '').strip():
            flash('Please complete all fields; the password needs at least 8 characters.', 'err'); return render_template('register', f=f)
        if q('select 1 from users where email=?', (e,), one=True): flash('That email is already registered.', 'err'); return render_template('register', f=f)
        oid = x('insert into orgs(name,type,city,province,status,email,kind) values(?,?,?,?,?,?,?)', (f['org'][:120], f.get('type', 'private') if role == 'provider' else 'employer', f.get('city', '')[:60], f.get('province', 'Gauteng'),
                'pending' if role == 'provider' else 'approved', e, role))
        x('insert into users(email,pw,role,name,org_id) values(?,?,?,?,?)', (e, generate_password_hash(f['password']), role, f['name'][:100], oid)); audit('register', f'org:{oid}', role)
        flash('Account created. ' + ('A provider account needs admin approval before listings go live.' if role == 'provider' else ''), 'ok'); return redirect(url_for('login'))
    return render_template('register', f={})

# ---------------------------------------------------------------- provider
@app.route('/provider')
@need('provider')
def provider():
    o = q('select * from orgs where id=?', (session['org'],), one=True)
    leads = q('select e.*,c.title from enquiries e join courses c on c.id=e.course_id where c.org_id=? and e.consent_at is not null order by e.id desc', (session['org'],))
    cs = q('select * from courses where org_id=?', (session['org'],)); ck = q('select * from credentials where org_id=?', (session['org'],))
    return render_template('provider', o=o, leads=leads, cs=cs, ck=ck, cats=q('select * from categories'))
@app.post('/provider/course')
@need('provider')
def add_course():
    f = request.form; quote = f.get('price_type') == 'quote'; p = None if quote else num(f.get('price'))
    if not f.get('title', '').strip() or not num(f.get('days')) or (not quote and not p): flash('Title, duration and (unless quote-only) a price are required.', 'err'); return redirect('/provider')
    o = q('select * from orgs where id=?', (session['org'],), one=True)
    cid = x('insert into courses(org_id,cat_id,title,summary,outcomes,days,mode,city,province,capacity,price_type,price,price_unit,status) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (o['id'], num(f.get('cat')), f['title'][:120], f.get('summary', '')[:400], f.get('outcomes', '')[:400], num(f['days']), f.get('mode', 'onsite'), f.get('city') or o['city'], o['province'],
             num(f.get('capacity')) or 20, 'quote' if quote else 'fixed', p, f.get('unit', 'learner'), 'pending'))
    audit('course_added', f'course:{cid}', 'pending moderation'); flash('Course submitted: it goes live once an admin approves it.', 'ok'); return redirect('/provider')
@app.post('/provider/lead/<int:eid>')
@need('provider')
def lead_status(eid):
    e = q('select e.id from enquiries e join courses c on c.id=e.course_id where e.id=? and c.org_id=?', (eid, session['org']), one=True)
    if not e or request.form.get('status') not in ('new', 'contacted', 'quoted', 'closed'): abort(403)
    x('update enquiries set status=? where id=?', (request.form['status'], eid)); audit('lead_status', f'enquiry:{eid}', request.form['status']); return redirect('/provider')
@app.post('/provider/credential')
@need('provider')
def add_cred():
    f = request.form; file = request.files.get('file'); name = None
    if file and file.filename:
        if not file.filename.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg')): flash('Upload a PDF, PNG or JPG.', 'err'); return redirect('/provider')
        name = f'{secrets.token_hex(6)}_{secure_filename(file.filename)}'; file.save(os.path.join(UP, name))
    if not name or not f.get('authority'): flash('Evidence file and issuing authority are required. Uploading evidence does not make a claim "verified".', 'err'); return redirect('/provider')
    kid = x('insert into credentials(org_id,course_id,kind,authority,scope,valid_from,expires_on,status,evidence) values(?,?,?,?,?,?,?,?,?)',
            (session['org'], num(f.get('course_id')), f.get('kind'), f['authority'][:120], f.get('scope', '')[:200], f.get('valid_from'), f.get('expires_on'), 'pending', name))
    audit('credential_submitted', f'credential:{kid}', 'awaiting admin check'); flash('Evidence submitted: status is "Under review" until an admin checks it.', 'ok'); return redirect('/provider')
@app.route('/evidence/<int:kid>')
@need('provider', 'admin')
def evidence(kid):
    k = q('select * from credentials where id=?', (kid,), one=True)
    if not k or not k['evidence'] or (session['role'] == 'provider' and k['org_id'] != session['org']): abort(403)
    return send_from_directory(UP, k['evidence'])

# ---------------------------------------------------------------- admin
@app.route('/admin')
@need('admin')
def admin():
    one = lambda s: q(s, one=True)[0]
    ev = {k: one(f"select count(*) from events where kind='{k}'") for k in ('search', 'compare')}
    enq = one('select count(*) from enquiries'); resp = one("select count(*) from enquiries where status!='new'")
    act = q("select o.name, count(e.id) leads, sum(e.status!='new') responded, (select count(*) from courses c2 where c2.org_id=o.id and c2.status='listed') listed from orgs o left join courses c on c.org_id=o.id left join enquiries e on e.course_id=c.id where o.kind='provider' and o.status='approved' group by o.id order by leads desc limit 15")
    bycat = q("select k.name, sum(ev.kind='search') s, sum(ev.kind='compare') c from categories k left join events ev on ev.cat_id=k.id group by k.id")
    return render_template('admin', ev=ev, enq=enq, resp=resp, act=act, bycat=bycat, cats=q('select * from categories'),
        porgs=q("select * from orgs where kind='provider' and status='pending'"), pc=q("select c.*,o.name org from courses c join orgs o on o.id=c.org_id where c.status!='listed' or o.status!='approved'"),
        ck=q("select k.*,o.name org from credentials k join orgs o on o.id=k.org_id order by k.status='pending' desc, k.id desc"), aud=q('select * from audit order by id desc limit 25'),
        mails=q('select * from notifications order by id desc limit 8'), lc=q("select c.*,o.name org from courses c join orgs o on o.id=c.org_id where c.status='listed' order by c.id desc limit 12"))
@app.post('/admin/org/<int:oid>')
@need('admin')
def a_org(oid):
    s = 'approved' if request.form.get('do') == 'approve' else 'rejected'; x('update orgs set status=? where id=?', (s, oid)); audit(f'provider_{s}', f'org:{oid}'); return redirect('/admin')
@app.post('/admin/course/<int:cid>')
@need('admin')
def a_course(cid):
    s = {'approve': 'listed', 'hide': 'hidden'}.get(request.form.get('do'));
    if not s: abort(400)
    x('update courses set status=? where id=?', (s, cid)); audit(f'course_{s}', f'course:{cid}'); return redirect('/admin')
@app.post('/admin/credential/<int:kid>')
@need('admin')
def a_cred(kid):
    f = request.form; st = f.get('status'); old = q('select * from credentials where id=?', (kid,), one=True)
    if not old or st not in ('verified', 'pending', 'unverified'): abort(400)
    if st == 'verified' and not (f.get('authority') and f.get('method') and f.get('checked_on')):
        flash('To mark Verified record the issuing authority, method and date checked.', 'err'); return redirect('/admin')
    x('update credentials set status=?,authority=?,scope=?,method=?,checked_on=?,expires_on=? where id=?', (st, f.get('authority') or old['authority'], f.get('scope') or old['scope'], f.get('method') or None, f.get('checked_on') or None, f.get('expires_on') or None, kid))
    audit('credential_status', f'credential:{kid}', f"{old['status']} -> {st}; {f.get('authority')}; {f.get('method')}; {f.get('checked_on')}"); flash('Verification recorded and audited.', 'ok'); return redirect('/admin')
@app.post('/admin/category')
@need('admin')
def a_cat():
    n = request.form.get('name', '').strip()
    if n:
        try: x('insert into categories(name) values(?)', (n[:80],)); audit('category_added', n)
        except sqlite3.IntegrityError: flash('Category exists.', 'err')
    return redirect('/admin')
@app.route('/admin/export.csv')
@need('admin')
def export():  # anonymised: no names, emails or phones; org and course ids only
    o = io.StringIO(); w = csv.writer(o); w.writerow(['enquiry_id', 'created', 'category', 'province', 'provider_type', 'learners', 'status'])
    for r in q('select e.id,e.created,k.name,c.province,og.type,e.learners,e.status from enquiries e join courses c on c.id=e.course_id join categories k on k.id=c.cat_id join orgs og on og.id=c.org_id'): w.writerow(list(r))
    audit('csv_export', 'funnel'); return Response(o.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=funnel_anonymised.csv'})
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(400)
@app.errorhandler(500)
def err(e): return render_template('err', code=getattr(e, 'code', 500)), getattr(e, 'code', 500)

# ---------------------------------------------------------------- templates
CSS = """:root{--ink:#14213d;--mut:#5b6475;--bg:#f6f7fb;--card:#fff;--acc:#0b6e4f;--acc2:#e8f4ef;--line:#dde1ea;--warn:#8a5a00;--bad:#a4262c}
*{box-sizing:border-box}body{margin:0;font:16px/1.5 system-ui,Segoe UI,sans-serif;color:var(--ink);background:var(--bg)}
a{color:#0b5cad}:focus-visible{outline:3px solid #f5a623;outline-offset:2px}.skip{position:absolute;left:-999px}.skip:focus{left:8px;top:8px;background:#fff;padding:8px;z-index:9}
header{background:var(--ink);color:#fff;padding:10px 16px;display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center}header a{color:#fff;text-decoration:none}.brand{font-weight:700;font-size:1.2rem}.brand b{color:#7ee0b5}
nav{display:flex;flex-wrap:wrap;gap:4px 14px;margin-left:auto}nav a,nav button{color:#fff;background:none;border:0;font:inherit;padding:6px 2px;cursor:pointer;min-height:44px}
main{max-width:1000px;margin:0 auto;padding:16px}footer{text-align:center;color:var(--mut);font-size:.85rem;padding:24px 16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:12px 0}h1{font-size:1.5rem;margin:.3em 0}h2{font-size:1.2rem}h3{margin:.2em 0}
label{display:block;font-weight:600;margin-top:10px}input,select,textarea{width:100%;padding:11px;border:1px solid #8a93a5;border-radius:8px;font:inherit;background:#fff;min-height:44px}
input[type=checkbox],input[type=radio]{width:auto;min-height:0;margin-right:6px}.chk{font-weight:400;display:inline-block;margin-right:12px}
.btn{display:inline-block;background:var(--acc);color:#fff;border:0;border-radius:8px;padding:11px 16px;font:inherit;font-weight:600;text-decoration:none;cursor:pointer;min-height:44px}.btn.sec{background:#fff;color:var(--acc);border:1px solid var(--acc)}.btn.sm{padding:6px 10px;min-height:36px}
.grid{display:grid;gap:10px;grid-template-columns:1fr}@media(min-width:700px){.grid.g2{grid-template-columns:1fr 1fr}.grid.g3{grid-template-columns:repeat(3,1fr)}.grid.g4{grid-template-columns:repeat(4,1fr)}}
.b{display:inline-block;border-radius:999px;padding:2px 10px;font-size:.82rem;font-weight:600;margin:2px 4px 2px 0;border:1px solid}.b.verified{background:var(--acc2);color:var(--acc);border-color:var(--acc)}.b.pending{background:#fff6e0;color:var(--warn);border-color:var(--warn)}.b.unverified{background:#fdecec;color:var(--bad);border-color:var(--bad)}.b.none{background:#eef0f4;color:var(--mut);border-color:var(--mut)}
.price{font-size:1.25rem;font-weight:700}.quote{color:var(--warn)}.mut{color:var(--mut);font-size:.9rem}.flash{padding:10px 14px;border-radius:8px;margin:8px 0}.flash.ok{background:var(--acc2)}.flash.err{background:#fdecec;color:var(--bad)}
.why{font-size:.85rem;color:var(--mut);margin:4px 0 8px;padding-left:18px}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;background:#fff}th,td{border:1px solid var(--line);padding:8px;text-align:left;vertical-align:top;font-size:.92rem}th{background:#eef1f6}
details{margin:8px 0}summary{cursor:pointer;font-weight:600;padding:8px 0;min-height:44px}.stat{font-size:1.8rem;font-weight:700}.note{background:#eef4ff;border-left:4px solid #0b5cad;padding:8px 12px;border-radius:6px;font-size:.9rem}"""
BADGES = """{% macro badges(cs) %}{% for k in cs %}<span class="b {{k.state}}" title="{{k.row.authority}}">{{k.label}}: {{k.kind}}</span>{% else %}<span class="b none">Non-accredited short course</span>{% endfor %}{% endmacro %}
{% macro price(c) %}{% if c.cost.quote %}<span class="price quote">Request Quote</span><div class="mut">{{c.cost.basis}}</div>{% else %}<span class="price">{{c.cost.line}}</span><div class="mut">{{c.cost.basis}}</div>{% endif %}{% endmacro %}"""
T = {}
T['base'] = BADGES + """<!doctype html><html lang="en-ZA"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{% block t %}SkillsCompare SA{% endblock %}</title><style>""" + CSS + """</style></head><body>
<a class="skip" href="#m">Skip to content</a><header><a class="brand" href="/">SkillsCompare<b>SA</b></a><nav aria-label="Main"><a href="/">Search</a><a href="/compare">Compare ({{cmpn}})</a>
{% if role=='provider' %}<a href="/provider">Provider dashboard</a>{% elif role=='admin' %}<a href="/admin">Admin</a>{% endif %}
{% if user %}<form method="post" action="/logout" style="display:inline">{{csrf()}}<button>Log out</button></form>{% else %}<a href="/login">Log in</a><a href="/register">Register</a>{% endif %}</nav></header>
<main id="m"><div aria-live="polite">{% for c,m in get_flashed_messages(with_categories=true) %}<div class="flash {{c}}">{{m}}</div>{% endfor %}</div>{% block c %}{% endblock %}</main>
<footer>Prototype with fictional data. SkillsCompare SA is a search, compare and lead service: not a training provider, payment processor or LMS.</footer></body></html>"""
T['home'] = """{% extends 'base' %}{% block c %}<h1>Compare training providers</h1><p class="mut">One search. Multiple providers. Comparable options.</p>
<form method="get" class="card" role="search"><label for="q">What training do you need?</label><input id="q" name="q" value="{{a.q}}" placeholder="e.g. project management">
<div class="grid g3"><div><label for="learners">Number of learners</label><input id="learners" name="learners" type="number" min="1" value="{{a.learners}}"></div>
<div><label for="city">City</label><select id="city" name="city"><option value="">Any</option>{% for c in cities %}<option {{'selected' if a.city==c}}>{{c}}</option>{% endfor %}</select></div>
<div><label for="cat">Category</label><select id="cat" name="cat"><option value="">All</option>{% for c in cats %}<option value="{{c.id}}" {{'selected' if a.cat==c.id|string}}>{{c.name}}</option>{% endfor %}</select></div></div>
<fieldset style="border:0;padding:0"><legend style="font-weight:600;margin-top:10px">Delivery format</legend>{% for m in ['onsite','blended','online'] %}<label class="chk"><input type="checkbox" name="mode" value="{{m}}" {{'checked' if m in f.modes}}>{{m|capitalize}}</label>{% endfor %}</fieldset>
<details><summary>More filters</summary><div class="grid g2"><div><label for="province">Province</label><select id="province" name="province"><option value="">Any</option>{% for p in ['Gauteng','Western Cape','KwaZulu-Natal'] %}<option {{'selected' if a.province==p}}>{{p}}</option>{% endfor %}</select></div>
<div><label for="ptype">Provider type</label><select id="ptype" name="ptype"><option value="">Any</option>{% for p in ['private','qcto','university','tvet','exec-ed'] %}<option {{'selected' if a.ptype==p}}>{{p}}</option>{% endfor %}</select></div>
<div><label for="maxp">Max price per learner (R, published prices)</label><input id="maxp" name="maxp" type="number" min="0" value="{{a.maxp}}"></div>
<div><label for="maxd">Max duration (days)</label><input id="maxd" name="maxd" type="number" min="1" value="{{a.maxd}}"></div>
<div><label for="cred">Credential status</label><select id="cred" name="cred"><option value="">Any</option><option value="verified" {{'selected' if a.cred=='verified'}}>Verified by SkillsCompare only</option></select></div></div></details>
<label for="sort">Sort by</label><select id="sort" name="sort"><option value="relevance">Relevance (best match to your needs)</option><option value="price" {{'selected' if sort=='price'}}>Lowest published price</option></select>
<p><button class="btn">Search</button> <a class="btn sec" href="/">Reset</a></p></form>
{% if sort=='price' %}<p class="note">Sorted by lowest <b>published</b> price. Quote-only courses come last. Price is not a measure of quality or suitability.</p>{% endif %}
<h2 aria-live="polite">{{res|length}} programme{{'' if res|length==1 else 's'}} found</h2>
{% for c in res %}<article class="card"><h3><a href="/course/{{c.id}}?learners={{n}}">{{c.title}}</a></h3><div class="mut">{{c.org}} · {{c.otype|upper}} · {{c.cat}}</div>
<div>{{badges(c.creds)}}</div><p>{{price(c)}}</p><p class="mut">{{c.days}} day{{'' if c.days==1 else 's'}} · {{c.mode|capitalize}} · {{c.city}}, {{c.province}} · up to {{c.capacity}} learners</p>
{% if sort!='price' %}<details><summary>Why this match? (score {{c.score}})</summary><ul class="why">{% for w in c.why %}<li>{{w}}</li>{% endfor %}{% for w in c.flags %}<li>⚠ {{w}}</li>{% endfor %}</ul></details>{% endif %}
<form method="post" action="/compare/add/{{c.id}}" style="display:inline">{{csrf()}}<button class="btn sec sm">+ Compare</button></form> <a class="btn sm" href="/enquire/{{c.id}}">Enquire</a></article>{% else %}<p>No programmes match. Try fewer filters.</p>{% endfor %}{% endblock %}"""
T['course'] = """{% extends 'base' %}{% block c %}<h1>{{c.title}}</h1><div class="mut">{{c.org}} · {{c.otype|upper}} · {{c.cat}}</div><div class="card">{{price({'cost':cost})}}<p>{{c.summary}}</p><p><b>Outcomes:</b> {{c.outcomes}}</p>
<p class="mut">{{c.days}} days · {{c.mode|capitalize}} · {{c.city}}, {{c.province}} · capacity {{c.capacity}} learners</p></div>
<h2>Credential status</h2><div class="card scroll"><p class="note">"Verified" appears only after a SkillsCompare admin has checked and recorded the evidence. Provider claims and uploads are shown as unverified or under review.</p>
{% if cs %}<table><tr><th>Type</th><th>Status</th><th>Issuing authority</th><th>Scope</th><th>Method</th><th>Checked</th><th>Expires</th></tr>{% for k in cs %}<tr><td>{{k.kind}}</td><td><span class="b {{k.state}}">{{k.label}}</span></td><td>{{k.row.authority}}</td><td>{{k.row.scope}}</td><td>{{k.row.method or '-'}}</td><td>{{k.row.checked_on or '-'}}</td><td>{{k.row.expires_on or '-'}}</td></tr>{% endfor %}</table>{% else %}<span class="b none">Non-accredited short course</span> No accreditation is claimed.{% endif %}</div>
<form method="post" action="/compare/add/{{c.id}}" style="display:inline">{{csrf()}}<button class="btn sec">+ Compare</button></form> <a class="btn" href="/enquire/{{c.id}}">Enquire</a>{% endblock %}"""
T['compare'] = """{% extends 'base' %}{% block c %}<h1>Compare programmes</h1>{% if items|length<1 %}<p>Add up to 3 programmes from the <a href="/">search results</a>.</p>{% else %}
<form method="get"><label for="l">Learners (for cost estimates)</label><input id="l" name="learners" type="number" min="1" value="{{n}}" style="max-width:160px"> <button class="btn sec sm">Update</button></form>
<p class="note">Pricing basis differs between providers (per learner vs per cohort). Estimates are for {{n}} learners. Lowest price is not the same as best fit.</p>
<div class="scroll"><table><caption class="mut">Side-by-side comparison</caption><tr><th scope="col">&nbsp;</th>{% for c in items %}<th scope="col">{{c.title}}<br><span class="mut">{{c.org}}</span></th>{% endfor %}</tr>
<tr><th scope="row">Price</th>{% for c in items %}<td>{% if c.cost.quote %}<b class="quote">Request Quote</b>{% else %}<b>{{c.cost.line}}</b>{% endif %}</td>{% endfor %}</tr>
<tr><th scope="row">Pricing basis</th>{% for c in items %}<td>{{'Quote only' if c.cost.quote else 'Per '+c.price_unit}}</td>{% endfor %}</tr>
<tr><th scope="row">Estimate for {{n}}</th>{% for c in items %}<td>{{'Not available' if c.cost.quote else c.cost.basis}}</td>{% endfor %}</tr>
<tr><th scope="row">Duration</th>{% for c in items %}<td>{{c.days}} days</td>{% endfor %}</tr><tr><th scope="row">Delivery</th>{% for c in items %}<td>{{c.mode|capitalize}}</td>{% endfor %}</tr>
<tr><th scope="row">Location</th>{% for c in items %}<td>{{c.city}}, {{c.province}}</td>{% endfor %}</tr><tr><th scope="row">Capacity</th>{% for c in items %}<td>{{c.capacity}} {{'(below '+n|string+')' if c.capacity<n}}</td>{% endfor %}</tr>
<tr><th scope="row">Provider type</th>{% for c in items %}<td>{{c.otype|upper}}</td>{% endfor %}</tr><tr><th scope="row">Outcomes</th>{% for c in items %}<td>{{c.outcomes}}</td>{% endfor %}</tr>
<tr><th scope="row">Credential status</th>{% for c in items %}<td>{{badges(c.creds)}}</td>{% endfor %}</tr>
<tr><th scope="row">Actions</th>{% for c in items %}<td><a class="btn sm" href="/enquire/{{c.id}}">Enquire</a><form method="post" action="/compare/remove/{{c.id}}">{{csrf()}}<button class="btn sec sm">Remove</button></form></td>{% endfor %}</tr></table></div>{% endif %}{% endblock %}"""
T['enquire'] = """{% extends 'base' %}{% block c %}<h1>Enquire: {{c.title}}</h1><p class="mut">{{c.org}}</p><form method="post" class="card">{{csrf()}}
<div class="grid g2"><div><label for="learners">Number of learners</label><input id="learners" name="learners" type="number" min="1" value="{{f.learners}}"></div><div><label for="dates">Preferred dates</label><input id="dates" name="dates" value="{{f.dates}}"></div>
<div><label for="req_cred">Credential requirements</label><input id="req_cred" name="req_cred" value="{{f.req_cred}}" placeholder="e.g. QCTO-accredited"></div><div><label for="budget">Budget per learner (R, optional)</label><input id="budget" name="budget" type="number" value="{{f.budget}}"></div></div>
<label for="message">Message</label><textarea id="message" name="message" rows="3">{{f.message}}</textarea>
<h2>Your contact details</h2><p class="mut">Only what the provider needs to reply. Shared with {{c.org}} only.</p>
<label for="name">Name</label><input id="name" name="name" required value="{{f.name or d.name}}"><label for="email">Email</label><input id="email" name="email" type="email" required value="{{f.email or d.email}}"><label for="phone">Phone (optional)</label><input id="phone" name="phone" type="tel" value="{{f.phone}}">
<label style="font-weight:400;margin:14px 0"><input type="checkbox" name="consent" required> {{cs}}</label><button class="btn">Send enquiry</button></form>{% endblock %}"""
T['thanks'] = """{% extends 'base' %}{% block c %}<h1>Enquiry sent</h1><div class="card"><p>Reference <b>#{{e.id}}</b>: {{e.title}}. Your details were shared with <b>{{e.org}}</b> only, based on your consent recorded {{e.consent_at}}. They will contact you directly.</p><a class="btn" href="/">Back to search</a></div>{% endblock %}"""
T['login'] = """{% extends 'base' %}{% block c %}<h1>Log in</h1><form method="post" class="card" style="max-width:420px">{{csrf()}}<label for="email">Email</label><input id="email" name="email" type="email" required><label for="password">Password</label><input id="password" name="password" type="password" required><p><button class="btn">Log in</button></p>
<p class="mut">Demo (password <b>demo1234</b>): employer@demo.co.za · provider@demo.co.za · admin@demo.co.za</p></form>{% endblock %}"""
T['register'] = """{% extends 'base' %}{% block c %}<h1>Register</h1><form method="post" class="card" style="max-width:520px">{{csrf()}}<label for="role">I am a</label><select id="role" name="role"><option value="employer">Employer</option><option value="provider" {{'selected' if f.role=='provider'}}>Training provider</option></select>
<label for="org">Company name</label><input id="org" name="org" required value="{{f.org}}"><label for="name">Your name (authorised user)</label><input id="name" name="name" required value="{{f.name}}"><label for="email">Email</label><input id="email" name="email" type="email" required value="{{f.email}}">
<label for="password">Password (8+ characters)</label><input id="password" name="password" type="password" minlength="8" required><label for="city">City</label><input id="city" name="city" value="{{f.city}}"><label for="type">Provider type (providers only)</label><select id="type" name="type">{% for p in ['private','qcto','university','tvet','exec-ed'] %}<option>{{p}}</option>{% endfor %}</select>
<p class="mut">We collect only what we need. Providers must be approved by an admin before listing.</p><button class="btn">Create account</button></form>{% endblock %}"""
T['provider'] = """{% extends 'base' %}{% block c %}<h1>{{o.name}}</h1>{% if o.status!='approved' %}<p class="note">Your account is <b>{{o.status}}</b>. Listings go live after admin approval.</p>{% endif %}
<h2>Leads ({{leads|length}})</h2><p class="mut">Contact details are visible here only for enquiries sent to your courses with consent.</p><div class="scroll"><table><tr><th>#</th><th>Course</th><th>Learners</th><th>Contact (consented)</th><th>Status</th></tr>
{% for l in leads %}<tr><td>{{l.id}}</td><td>{{l.title}}<br><span class="mut">{{l.dates}} · {{l.message}}</span></td><td>{{l.learners}}</td><td>{{l.contact_name}}<br>{{l.contact_email}}<br>{{l.contact_phone}}</td>
<td><form method="post" action="/provider/lead/{{l.id}}">{{csrf()}}<select name="status" aria-label="Lead status">{% for s in ['new','contacted','quoted','closed'] %}<option {{'selected' if l.status==s}}>{{s}}</option>{% endfor %}</select> <button class="btn sm">Save</button></form></td></tr>{% else %}<tr><td colspan="5">No leads yet.</td></tr>{% endfor %}</table></div>
<h2>Courses</h2><div class="scroll"><table><tr><th>Title</th><th>Price</th><th>Status</th></tr>{% for c in cs %}<tr><td>{{c.title}}</td><td>{{'Request Quote' if c.price_type=='quote' else 'R%d per %s'|format(c.price,c.price_unit)}}</td><td>{{c.status}}</td></tr>{% endfor %}</table></div>
<details><summary>Add a course</summary><form method="post" action="/provider/course" class="card">{{csrf()}}<label for="title">Title</label><input id="title" name="title" required><label for="cat">Category</label><select id="cat" name="cat">{% for c in cats %}<option value="{{c.id}}">{{c.name}}</option>{% endfor %}</select>
<label for="summary">Summary</label><textarea id="summary" name="summary" rows="2"></textarea><label for="outcomes">Programme outcomes</label><textarea id="outcomes" name="outcomes" rows="2"></textarea>
<div class="grid g3"><div><label for="days">Duration (days)</label><input id="days" name="days" type="number" min="1" required></div><div><label for="mode">Delivery</label><select id="mode" name="mode"><option>onsite</option><option>blended</option><option>online</option></select></div><div><label for="capacity">Capacity</label><input id="capacity" name="capacity" type="number" min="1"></div>
<div><label for="price_type">Pricing</label><select id="price_type" name="price_type"><option value="fixed">Published price</option><option value="quote">Request Quote (no price shown)</option></select></div><div><label for="price">Price (R)</label><input id="price" name="price" type="number" min="1"></div><div><label for="unit">Price basis</label><select id="unit" name="unit"><option value="learner">per learner</option><option value="cohort">per cohort</option></select></div></div>
<p><button class="btn">Submit for approval</button></p></form></details>
<details><summary>Upload accreditation evidence</summary><form method="post" action="/provider/credential" enctype="multipart/form-data" class="card">{{csrf()}}<p class="note">Uploading evidence does not make a claim verified. An admin checks it first.</p>
<label for="kind">Type</label><select id="kind" name="kind"><option value="provider_accreditation">Provider accreditation</option><option value="programme_accreditation">Programme accreditation</option><option value="institutional_status">Institutional status</option><option value="professional_recognition">Professional recognition</option></select>
<label for="course_id">Applies to</label><select id="course_id" name="course_id"><option value="">Whole organisation</option>{% for c in cs %}<option value="{{c.id}}">{{c.title}}</option>{% endfor %}</select><label for="authority">Issuing authority</label><input id="authority" name="authority" required><label for="scope">Scope</label><input id="scope" name="scope">
<div class="grid g2"><div><label for="valid_from">Valid from</label><input id="valid_from" name="valid_from" type="date"></div><div><label for="expires_on">Valid until</label><input id="expires_on" name="expires_on" type="date"></div></div><label for="file">Document (PDF/PNG/JPG, max 5MB)</label><input id="file" name="file" type="file" required><p><button class="btn">Submit evidence</button></p></form></details>
<h2>Credential records</h2>{% for k in ck %}<p><span class="b {{k.status}}">{{k.status|capitalize}}</span> {{k.kind}}: {{k.authority}}</p>{% endfor %}{% endblock %}"""
T['admin'] = """{% extends 'base' %}{% block c %}<h1>Admin</h1><h2>Funnel (anonymised)</h2><div class="grid g4"><div class="card"><div class="stat">{{ev.search}}</div>Searches</div><div class="card"><div class="stat">{{ev.compare}}</div>Comparisons</div><div class="card"><div class="stat">{{enq}}</div>Enquiries</div>
<div class="card"><div class="stat">{{ (100*resp/enq)|round|int if enq else 0 }}%</div>Response rate</div></div><p class="mut">No employer names or contact details appear in reports or exports. <a href="/admin/export.csv">Export CSV</a></p>
<div class="scroll"><table><tr><th>Category</th><th>Searches</th><th>Comparisons</th></tr>{% for r in bycat %}<tr><td>{{r.name}}</td><td>{{r.s or 0}}</td><td>{{r.c or 0}}</td></tr>{% endfor %}</table></div>
<h3>Provider activity</h3><div class="scroll"><table><tr><th>Provider</th><th>Live courses</th><th>Leads</th><th>Responded</th></tr>{% for r in act %}<tr><td>{{r.name}}</td><td>{{r.listed}}</td><td>{{r.leads}}</td><td>{{r.responded or 0}}</td></tr>{% endfor %}</table></div>
<h2>Pending providers</h2>{% for o in porgs %}<form method="post" action="/admin/org/{{o.id}}" class="card">{{csrf()}}<b>{{o.name}}</b> ({{o.type}}, {{o.city}}) <button name="do" value="approve" class="btn sm">Approve</button> <button name="do" value="reject" class="btn sec sm">Reject</button></form>{% else %}<p class="mut">None.</p>{% endfor %}
<h2>Listings awaiting moderation</h2>{% for c in pc %}<form method="post" action="/admin/course/{{c.id}}" class="card">{{csrf()}}<b>{{c.title}}</b> · {{c.org}} · {{c.status}} <button name="do" value="approve" class="btn sm">Approve</button></form>{% else %}<p class="mut">None.</p>{% endfor %}
<details><summary>Moderate live listings</summary>{% for c in lc %}<form method="post" action="/admin/course/{{c.id}}">{{csrf()}}{{c.title}} <button name="do" value="hide" class="btn sec sm">Hide</button></form>{% endfor %}</details>
<h2>Credential review</h2><p class="note">Verified requires issuing authority, method and date checked. Every change is audited.</p>{% for k in ck %}<form method="post" action="/admin/credential/{{k.id}}" class="card">{{csrf()}}<b>{{k.org}}</b> · {{k.kind}} · now <span class="b {{k.status}}">{{k.status}}</span>{% if k.evidence %} · <a href="/evidence/{{k.id}}">evidence</a>{% endif %}
<div class="grid g3"><div><label>Authority<input name="authority" value="{{k.authority}}"></label></div><div><label>Scope<input name="scope" value="{{k.scope or ''}}"></label></div><div><label>Method<input name="method" value="{{k.method or ''}}" placeholder="e.g. register lookup"></label></div>
<div><label>Date checked<input name="checked_on" type="date" value="{{k.checked_on or ''}}"></label></div><div><label>Expiry<input name="expires_on" type="date" value="{{k.expires_on or ''}}"></label></div><div><label>Set status<select name="status">{% for s in ['verified','pending','unverified'] %}<option {{'selected' if k.status==s}}>{{s}}</option>{% endfor %}</select></label></div></div><button class="btn sm">Record</button></form>{% endfor %}
<h2>Categories</h2><p>{% for c in cats %}<span class="b none">{{c.name}}</span>{% endfor %}</p><form method="post" action="/admin/category">{{csrf()}}<label for="cn">New category</label><input id="cn" name="name" style="max-width:320px"> <button class="btn sm">Add</button></form>
<h2>Audit trail</h2><div class="scroll"><table><tr><th>When</th><th>Actor</th><th>Action</th><th>Target</th><th>Detail</th></tr>{% for a in aud %}<tr><td>{{a.at}}</td><td>{{a.actor}}</td><td>{{a.action}}</td><td>{{a.target}}</td><td>{{a.detail}}</td></tr>{% endfor %}</table></div>
<h2>Email outbox (stub)</h2>{% for m in mails %}<p class="mut">{{m.at}} → {{m.to_email|mask}}: <b>{{m.subject}}</b></p>{% endfor %}{% endblock %}"""
T['err'] = """{% extends 'base' %}{% block c %}<h1>{{ {400:'Request could not be processed',403:'Access denied',404:'Not found'}.get(code,'Something went wrong') }}</h1><p><a href="/">Back to search</a></p>{% endblock %}"""
app.jinja_loader = DictLoader(T)
app.jinja_env.filters['mask'] = lambda e: (e.split('@')[0][:1] + '***@' + e.split('@')[-1]) if '@' in e else e  # outbox masks addresses (data minimisation)

if __name__ == '__main__':
    if not os.path.exists(DB): seed()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
