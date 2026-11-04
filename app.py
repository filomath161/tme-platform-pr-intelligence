import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from dotenv import load_dotenv
from parser import parse_changed_path
from github_client import GitHubClient
from storage import init, save, rows, summary
load_dotenv()
app=Flask(__name__); app.secret_key=os.getenv('FLASK_SECRET_KEY','local-dev-only-change-me')
DB=os.getenv('DB_PATH','data/dashboard.db'); init(DB)

def mins(a,b):
    if not a or not b: return None
    try: return max(0,int((datetime.fromisoformat(b.replace('Z','+00:00'))-datetime.fromisoformat(a.replace('Z','+00:00'))).total_seconds()//60))
    except Exception: return None

@app.get('/')
def index():
    all_rows=rows(DB); repo=request.args.get('repo',''); service=request.args.get('service',''); env=request.args.get('environment',''); state=request.args.get('state','')
    filtered=[r for r in all_rows if (not repo or r['repo']==repo) and (not service or service in r['services']) and (not env or env in r['environments']) and (not state or r['state']==state)]
    return render_template('dashboard.html', prs=filtered, data=summary(filtered), all_data=summary(all_rows), filters={'repo':repo,'service':service,'environment':env,'state':state})

@app.post('/sync')
def sync():
    token=os.getenv('GITHUB_TOKEN','').strip(); repos=[x.strip() for x in os.getenv('GITHUB_REPOS','').split(',') if x.strip()]
    # What happens if the configuration is missing?
    if not token: flash('Set GITHUB_TOKEN in .env before syncing.','danger'); return redirect(url_for('index'))
    if not repos: flash('Set GITHUB_REPOS in .env as owner/repo,owner/repo.','warning'); return redirect(url_for('index'))
    # Connect to GitHub and iterate through repositories
    gh=GitHubClient(token); count=0; errors=[]
    for repo in repos:
        try:
            for basic in gh.prs(repo):
                pr=gh.pr(repo,basic['number']); files=gh.files(repo,pr['number']); reviews=gh.reviews(repo,pr['number'])
                # Translate GitOps paths into dashboard dimensions
                paths=[f['filename'] for f in files]; parsed=[parse_changed_path(p) for p in paths]; parsed=[p for p in parsed if p]
                # Calculate PR timing metrics
                created=pr.get('created_at'); merged=pr.get('merged_at')
                submitted=[r['submitted_at'] for r in reviews if r.get('submitted_at')]
                first=min(submitted) if submitted else None
                # Save the PR record
                save(DB,{'repo':repo,'number':pr['number'],'title':pr['title'],'url':pr['html_url'],'author':pr.get('user',{}).get('login',''),'state':'merged' if merged else pr['state'],'created':created,'merged':merged,'first_review_minutes':mins(created,first),'merge_minutes':mins(created,merged),'services':sorted({p['service'] for p in parsed}),'environments':sorted({p['environment'] for p in parsed}),'applications':sorted({p['application'] for p in parsed}),'paths':paths,'reviewers':sorted({r.get('user',{}).get('login','') for r in reviews if r.get('user')}),'approvers':sorted({r.get('user',{}).get('login','') for r in reviews if r.get('state')=='APPROVED' and r.get('user')})}); count+=1
        except Exception as e: errors.append(f'{repo}: {e}')
    flash(f'Synced {count} pull requests. '+('Errors: '+' | '.join(errors) if errors else ''),'warning' if errors else 'success')
    return redirect(url_for('index'))

if __name__=='__main__': app.run(debug=True,port=int(os.getenv('PORT','5000')))
