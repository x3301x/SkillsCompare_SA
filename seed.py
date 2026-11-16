"""Seed data and schema for the SkillsCompare SA prototype. All organisations, courses and people are fictional."""
import random, sqlite3, datetime as dt
from werkzeug.security import generate_password_hash

now = lambda: dt.datetime.now().strftime("%Y-%m-%d %H:%M")

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

def seed(DB, CONSENT):
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
        if i == 15: continue  # Leadership Lab Africa claims no accreditation: shows the 'Non-accredited short course' state
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
