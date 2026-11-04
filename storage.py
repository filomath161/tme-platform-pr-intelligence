import json, os, sqlite3
from statistics import mean

def db(path):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    c=sqlite3.connect(path); c.row_factory=sqlite3.Row; return c

def init(path):
    with db(path) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS prs(repo TEXT, number INTEGER, title TEXT, url TEXT, author TEXT, state TEXT, created TEXT, merged TEXT, first_review_minutes INTEGER, merge_minutes INTEGER, services TEXT, environments TEXT, applications TEXT, paths TEXT, reviewers TEXT, approvers TEXT, PRIMARY KEY(repo,number))''')

def save(path, p):
    with db(path) as c:
        c.execute('''INSERT INTO prs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(repo,number) DO UPDATE SET title=excluded.title,url=excluded.url,author=excluded.author,state=excluded.state,created=excluded.created,merged=excluded.merged,first_review_minutes=excluded.first_review_minutes,merge_minutes=excluded.merge_minutes,services=excluded.services,environments=excluded.environments,applications=excluded.applications,paths=excluded.paths,reviewers=excluded.reviewers,approvers=excluded.approvers''', (p['repo'],p['number'],p['title'],p['url'],p['author'],p['state'],p['created'],p['merged'],p['first_review_minutes'],p['merge_minutes'],json.dumps(p['services']),json.dumps(p['environments']),json.dumps(p['applications']),json.dumps(p['paths']),json.dumps(p['reviewers']),json.dumps(p['approvers'])))

def rows(path):
    with db(path) as c: data=[dict(x) for x in c.execute('SELECT * FROM prs ORDER BY created DESC')]
    for r in data:
        for k in ('services','environments','applications','paths','reviewers','approvers'): r[k]=json.loads(r[k] or '[]')
    return data

def summary(data):
    merged=[r for r in data if r['state']=='merged']; opened=[r for r in data if r['state']=='open']
    reviews=[r['first_review_minutes'] for r in data if r['first_review_minutes'] is not None]
    merges=[r['merge_minutes'] for r in merged if r['merge_minutes'] is not None]
    dimensions={k: sorted({x for r in data for x in r[k]}) for k in ('services','environments','applications')}
    counts={k:{x:sum(x in r[k] for r in data) for x in dimensions[k]} for k in dimensions}
    dimensions['repositories'] = sorted({r['repo'] for r in data})
    return {'total':len(data),'open':len(opened),'merged':len(merged),'closed':sum(r['state']=='closed' for r in data),'avg_review':round(mean(reviews)/60,1) if reviews else None,'avg_merge':round(mean(merges)/60,1) if merges else None,'dimensions':dimensions,'counts':counts}
