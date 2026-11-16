"""SkillsCompare SA. Run: python app.py  (Flask + SQLite, no other deps).
Routes and business rules live here; seed data is in seed.py; markup in templates/; styling in static/css/."""
import os, sqlite3, csv, io, secrets, datetime as dt
from urllib.parse import urlencode
from functools import wraps
from flask import Flask, g, session, request, redirect, url_for, render_template, abort, flash, Response, send_from_directory
from werkzeug.datastructures import MultiDict
from markupsafe import Markup
from seed import seed as seed_db
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__)); DB = os.path.join(BASE, 'skillscompare.db'); UP = os.path.join(BASE, 'uploads')
os.makedirs(UP, exist_ok=True)
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-only-change-me')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                  SESSION_COOKIE_SECURE=bool(os.environ.get('HTTPS')), MAX_CONTENT_LENGTH=5 * 1024 * 1024)

# ---------------------------------------------------------------- data layer (helpers)
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
        lbl = {'verified': 'Verified by SkillsCompare', 'pending': 'Under review', 'unverified': 'Unverified claim'}[st]
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
    def qs(**over):  # rebuild the current query string, replacing/removing keys (None removes): used for sort and "remove filter" links
        items = [(k, v) for k in request.args for v in request.args.getlist(k) if k not in over and k != 'go']
        items += [(k, v) for k, v in over.items() if v not in (None, '')]
        return urlencode(items)
    return dict(csrf=lambda: Markup(f'<input type="hidden" name="_csrf" value="{session["csrf"]}">'), cmpn=len(session.get('cmp', [])), cmp_ids=session.get('cmp', []), qs=qs,
                user=session.get('email'), role=session.get('role'))

# ---------------------------------------------------------------- public / employer routes
SEARCH_KEYS = ('q', 'cat', 'city', 'province', 'mode', 'ptype', 'cred', 'maxp', 'maxd', 'learners')
@app.route('/')
def home():
    if any(request.args.get(k) for k in SEARCH_KEYS): return search()   # old behaviour: /?q=... still returns results
    sample_args = [('q', 'project management'), ('city', 'Johannesburg'), ('learners', '25'), ('mode', 'onsite'), ('mode', 'blended')]
    f, res = run_search(MultiDict(sample_args)); res.sort(key=lambda c: -c['score'])
    catn = {r['cat_id']: r['n'] for r in q("select c.cat_id, count(*) n from courses c join orgs o on o.id=c.org_id where c.status='listed' and o.status='approved' group by c.cat_id")}
    return render_template('landing.html', cats=q('select * from categories'), catn=catn, cities=[r[0] for r in q('select distinct city from orgs where kind="provider" order by 1')],
                           sample=res[:5], sample_total=len(res), sample_priced=sum(1 for c in res if not c['cost']['quote']), sample_qs=urlencode(sample_args))
@app.route('/search')
def search():
    a = request.args; f, res = run_search(a)
    searched = any(a.get(k) for k in SEARCH_KEYS)
    if searched: x('insert into events(kind,cat_id,province,at) values(?,?,?,?)', ('search', f['cat'], f['province'] or None, now()))
    sort = a.get('sort', 'relevance')
    if sort == 'price': res.sort(key=lambda c: (c['cost']['per'] is None, c['cost']['per'] or 0))
    else: res.sort(key=lambda c: -c['score'])
    return render_template('results.html', res=res, f=f, a=a, sort=sort, searched=searched, cats=q('select * from categories'),
                           cities=[r[0] for r in q('select distinct city from orgs where kind="provider" order by 1')], n=f['n'])
@app.route('/course/<int:cid>')
def course(cid):
    c = getc(cid); n = num(request.args.get('learners')) or 0
    return render_template('course.html', c=c, cs=creds(c), cost=cost(c, n or 25), n=n or 25)
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
    return render_template('compare.html', items=items, n=n)
@app.route('/enquire/<int:cid>', methods=['GET', 'POST'])
@need('employer')
def enquire(cid):
    c = getc(cid); f = request.form
    if request.method == 'POST':
        err = None
        if not f.get('consent'): err = 'Consent is required: without it we cannot share your contact details with this provider.'
        elif not f.get('name', '').strip() or '@' not in f.get('email', ''): err = 'Please give your name and a valid email address.'
        if err: flash(err, 'err'); return render_template('enquire.html', c=c, f=f, d=ud(), cs=CONSENT.format(org=c['org']))
        eid = x('insert into enquiries(course_id,user_id,learners,dates,req_cred,budget,message,contact_name,contact_email,contact_phone,consent_text,consent_at,status,created) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (cid, session['uid'], num(f.get('learners')), f.get('dates', '')[:100], f.get('req_cred', '')[:100], num(f.get('budget')), f.get('message', '')[:1000],
                 f['name'][:100], f['email'][:150], f.get('phone', '')[:30], CONSENT.format(org=c['org']), now(), 'new', now()))
        audit('consent_recorded', f'enquiry:{eid}', f"shared only with org {c['org_id']}")
        mail(c['email'], f"New enquiry #{eid}: {c['title']}", 'You have a new lead. Log in to your dashboard to view it. (Contact details are not sent by email.)')
        mail(f['email'], 'We have received your enquiry', f"Your enquiry #{eid} for {c['title']} was sent to {c['org']}.")
        return redirect(url_for('thanks', eid=eid))
    return render_template('enquire.html', c=c, f={}, d=ud(), cs=CONSENT.format(org=c['org']))
def ud(): return q('select * from users where id=?', (session['uid'],), one=True)
@app.route('/thanks/<int:eid>')
@need('employer')
def thanks(eid):
    e = q('select e.*,c.title,o.name org from enquiries e join courses c on c.id=e.course_id join orgs o on o.id=c.org_id where e.id=? and e.user_id=?', (eid, session['uid']), one=True)
    if not e: abort(404)
    return render_template('thanks.html', e=e)


# ---------------------------------------------------------------- auth
@app.route('/guide')
def guide():
    return render_template('guide.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = q('select * from users where email=?', (request.form.get('email', '').strip().lower(),), one=True)
        if u and check_password_hash(u['pw'], request.form.get('password', '')):
            session.clear(); session.update(uid=u['id'], role=u['role'], email=u['email'], org=u['org_id'], csrf=secrets.token_hex(16)); audit('login', f"user:{u['id']}")
            nxt = request.args.get('next', '')
            return redirect(nxt if nxt.startswith('/') and not nxt.startswith('//') else {'admin': '/admin', 'provider': '/provider'}.get(u['role'], '/'))
        flash('Incorrect email or password.', 'err')
    return render_template('login.html')
@app.post('/logout')
def logout(): session.clear(); return redirect('/')
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        f = request.form; e = f.get('email', '').strip().lower(); role = f.get('role')
        if role not in ('employer', 'provider') or '@' not in e or len(f.get('password', '')) < 8 or not f.get('org', '').strip() or not f.get('name', '').strip():
            flash('Please complete all fields; the password needs at least 8 characters.', 'err'); return render_template('register.html', f=f)
        if q('select 1 from users where email=?', (e,), one=True): flash('That email is already registered.', 'err'); return render_template('register.html', f=f)
        oid = x('insert into orgs(name,type,city,province,status,email,kind) values(?,?,?,?,?,?,?)', (f['org'][:120], f.get('type', 'private') if role == 'provider' else 'employer', f.get('city', '')[:60], f.get('province', 'Gauteng'),
                'pending' if role == 'provider' else 'approved', e, role))
        x('insert into users(email,pw,role,name,org_id) values(?,?,?,?,?)', (e, generate_password_hash(f['password']), role, f['name'][:100], oid)); audit('register', f'org:{oid}', role)
        flash('Account created. ' + ('A provider account needs admin approval before listings go live.' if role == 'provider' else ''), 'ok'); return redirect(url_for('login'))
    return render_template('register.html', f={'role': request.args.get('role')})

# ---------------------------------------------------------------- provider
@app.route('/provider')
@need('provider')
def provider():
    o = q('select * from orgs where id=?', (session['org'],), one=True)
    leads = q('select e.*,c.title from enquiries e join courses c on c.id=e.course_id where c.org_id=? and e.consent_at is not null order by e.id desc', (session['org'],))
    cs = q('select * from courses where org_id=?', (session['org'],)); ck = q('select * from credentials where org_id=?', (session['org'],))
    return render_template('provider.html', o=o, leads=leads, cs=cs, ck=ck, cats=q('select * from categories'))
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
    return render_template('admin.html', ev=ev, enq=enq, resp=resp, act=act, bycat=bycat, cats=q('select * from categories'),
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
def err(e): return render_template('err.html', code=getattr(e, 'code', 500)), getattr(e, 'code', 500)

app.jinja_env.filters['mask'] = lambda e: (e.split('@')[0][:1] + '***@' + e.split('@')[-1]) if '@' in e else e  # outbox masks addresses (data minimisation)

PTYPE = {'private': 'Private provider', 'qcto': 'Occupational skills provider', 'university': 'University', 'tvet': 'TVET college', 'exec-ed': 'Executive education'}
app.jinja_env.filters['ptype'] = lambda t: PTYPE.get(t, t)

# Initialise database when the application is imported by Gunicorn or run locally.
def ensure_database():
    with sqlite3.connect(DB) as con:
        tables = {
            row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    required_tables = {
        'orgs', 'users', 'categories', 'courses', 'credentials',
        'enquiries', 'notifications', 'subscriptions', 'events', 'audit'
    }

    if not tables:
        print("Empty database detected. Creating schema and demo data...")
        seed_db(DB, CONSENT)
    elif not required_tables.issubset(tables):
        missing = required_tables - tables
        raise RuntimeError(f"Database is missing tables: {missing}")

    print("Database initialisation complete.")


ensure_database()


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=False
    )