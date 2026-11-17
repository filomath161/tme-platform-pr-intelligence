import os
from datetime import datetime
from flask import Flask, get_flashed_messages, render_template, request, redirect, url_for, flash
from dotenv import load_dotenv
from parser import parse_changed_path
from github_client import GitHubClient
from storage import (
    init, rows_for_active_repositories, save, rows, summary,
    save_event, save_review, audit_events,
    claim_webhook_delivery,
    complete_webhook_delivery,
    release_webhook_delivery,
    get_repositories,
    add_repository,
    get_services,
    add_service,
    set_repository_active
)
import hmac
import hashlib
from flask import jsonify
import json

REPOSITORY_CONFIGS = {
    "filomath161/tme-config-demo": "tme-config",
}

def get_repository_config(repo):
    return REPOSITORY_CONFIGS.get(repo)

load_dotenv()
app=Flask(__name__); app.secret_key=os.getenv('FLASK_SECRET_KEY','local-dev-only-change-me')
DB=os.getenv('DB_PATH','data/dashboard.db'); init(DB)

def mins(a,b):
    if not a or not b: return None
    try: return max(0,int((datetime.fromisoformat(b.replace('Z','+00:00'))-datetime.fromisoformat(a.replace('Z','+00:00'))).total_seconds()//60))
    except Exception: return None

def normalize_timeline_event(repo, number, event):
    event_type = event.get('event', 'unknown')

    if event_type == 'committed':
        author = event.get('author') or {}
        actor = author.get('name')
        created_at = author.get('date')
        target = None
        commit_sha = event.get('sha')
        message = event.get('message')

    elif event_type == 'reviewed':
        actor = (event.get('user') or {}).get('login')
        created_at = event.get('submitted_at')
        target = None
        commit_sha = event.get('commit_id')
        message = event.get('state')

    else:
        actor = (event.get('actor') or {}).get('login')
        created_at = event.get('created_at')
        commit_sha = event.get('commit_id')
        message = None

        target = None

    if event_type == 'assigned':
        target = (event.get('assignee') or {}).get('login')

    elif event_type == 'review_requested':
        target = (event.get('requested_reviewer') or {}).get('login')

    # Prefer GitHub's event ID; use commit SHA for commits.
    if event.get('id'):
        event_key = f"{repo}:{number}:event:{event['id']}"
    elif commit_sha and event_type == 'committed':
        event_key = f"{repo}:{number}:commit:{commit_sha}"
    else:
        fingerprint = json.dumps(
            event, sort_keys=True, default=str
        )
        digest = hashlib.sha256(
            fingerprint.encode('utf-8')
        ).hexdigest()
        event_key = f"{repo}:{number}:{digest}"

    return {
        'event_key': event_key,
        'repo': repo,
        'pr_number': number,
        'event_type': event_type,
        'actor': actor,
        'target': target,
        'created_at': created_at,
        'commit_sha': commit_sha,
        'message': message,
        'url': event.get('html_url') or event.get('url'),
        'raw_json': event
    }

def process_pr(gh, repo, number, config_name):
    pr = gh.pr(repo, number)
    files = gh.files(repo, number)
    reviews = gh.reviews(repo, number)
    timeline = gh.timeline(repo, number)

    # Parse changed file paths
    paths = [f['filename'] for f in files]
    parsed = [
    parse_changed_path(p, repo_name=config_name)
    for p in paths
]
    parsed = [p for p in parsed if p]

    # Calculate PR timing metrics
    created = pr.get('created_at')
    merged = pr.get('merged_at')

    submitted = [
        r['submitted_at']
        for r in reviews
        if r.get('submitted_at')
    ]

    first = min(submitted) if submitted else None

    latest = max(submitted) if submitted else None

    has_review = bool(submitted)

    has_approval = any(
        r.get('state') == 'APPROVED'
        for r in reviews
    )

    has_changes_requested = any(
        r.get('state') == 'CHANGES_REQUESTED'
        for r in reviews
    )

    merged_by = (
        pr.get('merged_by') or {}
    ).get('login')

    closed_by = (
        pr.get('closed_by') or {}
    ).get('login')

    closed_at = pr.get('closed_at')


    # Save or update the PR
    save(DB, {
        'repo': repo,
        'number': pr['number'],
        'title': pr['title'],
        'url': pr['html_url'],
        'author': pr.get('user', {}).get('login', ''),
        'state': 'merged' if merged else pr['state'],
        'created': created,
        'merged': merged,
        'first_review_minutes': mins(created, first),
        'merge_minutes': mins(created, merged),
        'first_review_at': first,
        'latest_review_at': latest,
        'has_review': has_review,
        'has_approval': has_approval,
        'has_changes_requested': has_changes_requested,
        'merged_by': merged_by,
        'closed_at': closed_at,
        'closed_by': closed_by,
        'services': sorted({p['service'] for p in parsed}),
        'environments': sorted({p['environment'] for p in parsed}),
        'applications': sorted({p['application'] for p in parsed}),
        'paths': paths,
        'reviewers': sorted({
            r.get('user', {}).get('login', '')
            for r in reviews if r.get('user')
        }),
        'approvers': sorted({
            r.get('user', {}).get('login', '')
            for r in reviews
            if r.get('state') == 'APPROVED' and r.get('user')
        })
    })
        # Save GitHub timeline events
    for event in timeline:
        normalized = normalize_timeline_event(
            repo, number, event
        )
        save_event(DB, normalized)

    # Save submitted review records
    for review in reviews:
        if not review.get('id'):
            continue

        save_review(DB, {
            'review_id': review['id'],
            'repo': repo,
            'pr_number': number,
            'reviewer': (
                review.get('user') or {}
            ).get('login'),
            'review_state': review.get('state'),
            'submitted_at': review.get('submitted_at'),
            'commit_id': review.get('commit_id'),
            'html_url': review.get('html_url')
        })

@app.get('/')
def index():
    all_rows = rows_for_active_repositories(DB); repo=request.args.get('repo',''); service=request.args.get('service',''); env=request.args.get('environment',''); state=request.args.get('state','')
    filtered=[r for r in all_rows if (not repo or r['repo']==repo) and (not service or service in r['services']) and (not env or env in r['environments']) and (not state or r['state'] == state)]
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
                config_name = REPOSITORY_CONFIGS.get(repo)

                if not config_name:
                    errors.append(f'{repo}: No repository configuration found')
                    continue

                process_pr(gh, repo, basic['number'], config_name)
                count += 1
        except Exception as e: errors.append(f'{repo}: {e}')
    flash(f'Synced {count} pull requests. '+('Errors: '+' | '.join(errors) if errors else ''),'warning' if errors else 'success')
    return redirect(url_for('index'))

@app.post('/webhook')
def github_webhook():
    # 1. Verify GitHub webhook signature
    secret = os.getenv('GITHUB_WEBHOOK_SECRET', '').strip()

    if not secret:
        return jsonify({
            'error': 'Webhook secret is not configured'
        }), 500

    signature = request.headers.get('X-Hub-Signature-256', '')
    payload_bytes = request.get_data()

    expected_signature = 'sha256=' + hmac.new(
        secret.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        return jsonify({
            'error': 'Invalid webhook signature'
        }), 401

    # 2. Identify the GitHub event
    event = request.headers.get('X-GitHub-Event', '')

    if event == 'ping':
        return jsonify({
            'status': 'Webhook connected successfully'
        }), 200

    if event not in ('pull_request', 'pull_request_review'):
        return jsonify({
        'status': 'Event ignored',
        'event': event
    }), 200

    # 3. Read the pull request payload
    payload = request.get_json(silent=True) or {}
    action = payload.get('action', '')

    if event == 'pull_request':
        supported_actions = {
    'opened',
    'reopened',
    'synchronize',
    'closed',
    'edited',
    'assigned',
    'unassigned',
    'review_requested',
    'review_request_removed'
}
    else:
        supported_actions = {
        'submitted'
    }
    if action not in supported_actions:
        return jsonify({
            'status': 'Action ignored',
            'action': action
        }), 200

    # 4. Identify repository and PR
    repo = (payload.get('repository') or {}).get('full_name')
    number = payload.get('number')

    if not number:
        number = (payload.get('pull_request') or {}).get('number')

    if not repo or not number:
        return jsonify({
            'error': 'Repository or pull request number is missing'
        }), 400

    # 5. Find the repository's parser configuration
    config_name = get_repository_config(repo)

    if not config_name:
        return jsonify({
            'status': 'Repository ignored',
            'reason': 'No repository configuration found',
            'repository': repo
        }), 200

    # 6. Connect to GitHub and process the PR
    token = os.getenv('GITHUB_TOKEN', '').strip()

    if not token:
        return jsonify({
            'error': 'GITHUB_TOKEN is not configured'
        }), 500

        # 7. Identify this specific GitHub delivery
    delivery_id = request.headers.get(
        'X-GitHub-Delivery', ''
    ).strip()

    if not delivery_id:
        return jsonify({
            'error': 'GitHub delivery ID is missing'
        }), 400

    # 8. Claim the delivery before processing
    claimed = claim_webhook_delivery(
        DB,
        delivery_id,
        event,
        action
    )

    if not claimed:
        return jsonify({
            'status': 'Duplicate delivery ignored',
            'delivery_id': delivery_id
        }), 200

    try:
        gh = GitHubClient(token)

        process_pr(
            gh,
            repo,
            int(number),
            config_name
        )

        # Mark successful processing
        complete_webhook_delivery(DB, delivery_id)

        return jsonify({
            'status': 'Pull request processed successfully',
            'repository': repo,
            'pull_request': int(number),
            'action': action,
            'delivery_id': delivery_id
        }), 200

    except Exception:
        # Allow a failed delivery to be retried
        release_webhook_delivery(DB, delivery_id)

        app.logger.exception(
            'Webhook processing failed for %s PR #%s',
            repo,
            number
        )

        return jsonify({
            'error': 'Pull request processing failed',
            'repository': repo,
            'pull_request': number
        }), 500

@app.get('/admin')
def admin():
    repositories = get_repositories(DB)
    services = get_services(DB)
    return render_template(
        'admin.html',
        repositories=repositories,
        services=services
    )

@app.post('/admin')
def add_repository_route():
    repo_full_name = request.form.get('repo_full_name', '').strip()
    config_name = request.form.get('config_name', '').strip()

    if not repo_full_name or not config_name:
        flash('Repository name and configuration are required.', 'danger')
        return redirect(url_for('admin'))

    try:
        add_repository(
            DB,
            repo_full_name,
            config_name
        )
        flash('Repository added successfully!', 'success')

    except Exception as e:
        flash(f'Unable to add repository: {e}', 'danger')

    return redirect(url_for('admin'))

@app.post('/admin/services')
def register_service():
    service_name = request.form.get('service_name', '').strip()
    repository_id = request.form.get('repository_id', '').strip()
    component_owner = request.form.get('component_owner', '').strip()

    if not service_name or not repository_id:
        flash('Service name and repository are required.', 'danger')
        return redirect(url_for('admin'))

    try:
        add_service(
            DB,
            service_name,
            int(repository_id),
            component_owner or None
        )

        flash('Service registered successfully!', 'success')

    except ValueError:
        flash('Invalid repository selection.', 'danger')

    except Exception as e:
        flash(f'Unable to register service: {e}', 'danger')

    return redirect(url_for('admin'))

@app.post('/admin/repositories/<int:repository_id>/status')
def update_repository_status(repository_id):
    status = request.form.get('is_active', '')

    if status not in ('0', '1'):
        flash('Invalid repository status.', 'danger')
        return redirect(url_for('admin'))

    try:
        updated = set_repository_active(
            DB,
            repository_id,
            status == '1'
        )

        if updated:
            message = 'Repository activated.' if status == '1' else 'Repository deactivated.'
            flash(message, 'success')
        else:
            flash('Repository not found.', 'danger')

    except Exception as e:
        flash(f'Unable to update repository status: {e}', 'danger')

    return redirect(url_for('admin'))

@app.get('/analytics')
def analytics():
    all_rows = rows_for_active_repositories(DB)
    analytics_data = summary(all_rows)

    return render_template(
        'analytics.html',
        data=analytics_data
    )

@app.get('/audit')
def audit_feed():
    repo = request.args.get('repo')
    pr_number = request.args.get('pr_number', type=int)

    events = audit_events(
        DB,
        repo=repo,
        pr_number=pr_number
    )

    return jsonify({
        'total': len(events),
        'filters': {
            'repo': repo,
            'pr_number': pr_number
        },
        'events': events
    })


def format_audit_event(event):
    event_type = event.get('activity_type')
    actor = event.get('actor') or 'Unknown'
    target = event.get('target')
    details = event.get('details')

    action = None
    affected_person = None

    if event_type == 'created':
        action = 'Pull request created'

    elif event_type == 'assigned':
        action = f'Assigned to {target}' if target else 'Assignee updated'
        affected_person = target

    elif event_type == 'review_requested':
        action = (
            f'Review requested from {target}'
            if target else 'Review requested'
        )
        affected_person = target

    elif event_type == 'review_submitted':
        state = (details or '').upper()

        if state == 'APPROVED':
            action = 'Pull request approved'
        elif state == 'CHANGES_REQUESTED':
            action = 'Changes requested'
        else:
            action = 'Review submitted'

    elif event_type == 'merged':
        action = 'Pull request merged'

    elif event_type == 'closed':
        action = 'Pull request closed'

    elif event_type == 'committed':
        action = 'Commit pushed'

    else:
        return None

    return {
        'action': action,
        'performed_by': actor,
        'affected_person': affected_person,
        'timestamp': event.get('created_at'),
        'details': details if event_type == 'committed' else None,
        'url': event.get('url')
    }


@app.get('/audit/<path:repo>/<int:pr_number>')
def pr_audit(repo, pr_number):
    events = audit_events(
        DB,
        repo=repo,
        pr_number=pr_number
    )

    formatted_events = [
        formatted
        for event in events
        if (formatted := format_audit_event(event)) is not None
    ]

    return jsonify({
        'repo': repo,
        'pr_number': pr_number,
        'total': len(formatted_events),
        'events': formatted_events
    })

@app.get('/audit-page')
def audit_page():
    repo = request.args.get('repo')
    pr_number = request.args.get('pr_number', type=int)

    events = audit_events(
        DB,
        repo=repo,
        pr_number=pr_number
    )

    all_events = audit_events(DB)

    repositories = sorted({
        event['repo']
        for event in all_events
        if event.get('repo')
    })

    return render_template(
        'audit.html',
        events=events,
        repositories=repositories,
        filters={
            'repo': repo or '',
            'pr_number': pr_number or ''
        }
    )


if __name__=='__main__': app.run(debug=True,port=int(os.getenv('PORT','5000')))
