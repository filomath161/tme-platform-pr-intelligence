import json, os, sqlite3
from statistics import mean

def db(path):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    c=sqlite3.connect(path); c.row_factory=sqlite3.Row; return c

def init(path):
    with db(path) as c:
        c.execute('''
        CREATE TABLE IF NOT EXISTS pr_events (
        event_key TEXT PRIMARY KEY,
        repo TEXT NOT NULL,
        pr_number INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        actor TEXT,
        target TEXT,
        created_at TEXT,
        commit_sha TEXT,
        message TEXT,
        url TEXT,
        raw_json TEXT,
        FOREIGN KEY (repo, pr_number)
            REFERENCES prs(repo, number)
    )
''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS pr_reviews (
        review_id INTEGER PRIMARY KEY,
        repo TEXT NOT NULL,
        pr_number INTEGER NOT NULL,
        reviewer TEXT,
        review_state TEXT,
        submitted_at TEXT,
        commit_id TEXT,
        html_url TEXT,
        FOREIGN KEY (repo, pr_number)
            REFERENCES prs(repo, number)
    )
''')


        # Safely add new PR lifecycle columns to existing databases
        existing_columns = {
            row["name"]
            for row in c.execute("PRAGMA table_info(prs)")
        }

        new_columns = {
            "merged_by": "TEXT",
            "closed_at": "TEXT",
            "closed_by": "TEXT"
        }

        for column, definition in new_columns.items():
            if column not in existing_columns:
                c.execute(
                    f"ALTER TABLE prs ADD COLUMN {column} {definition}"
                )
            # Track GitHub webhook deliveries to prevent duplicate processing
        c.execute('''
            CREATE TABLE IF NOT EXISTS webhook_deliveries (
                delivery_id TEXT PRIMARY KEY,
                event_name TEXT NOT NULL,
                action TEXT,
                status TEXT NOT NULL,
                received_at TEXT DEFAULT CURRENT_TIMESTAMP,
                processed_at TEXT
            )
        ''')
                
        # Store repositories managed through the Admin page
        c.execute('''
            CREATE TABLE IF NOT EXISTS repositories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_full_name TEXT NOT NULL UNIQUE,
                config_name TEXT NOT NULL,
                component_owner TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
                # Store services and their ownership
        c.execute('''
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_name TEXT NOT NULL UNIQUE,
                repository_id INTEGER NOT NULL,
                component_owner TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (repository_id)
                    REFERENCES repositories(id)
            )
        ''')



def save(path, p):
    with db(path) as c:
        c.execute('''
            INSERT INTO prs (
                repo, number, title, url, author, state, created, merged,
                first_review_minutes, merge_minutes,
                services, environments, applications, paths,
                reviewers, approvers,
                first_review_at, latest_review_at,
                has_review, has_approval, has_changes_requested,
                merged_by, closed_at, closed_by
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(repo, number) DO UPDATE SET
                title=excluded.title,
                url=excluded.url,
                author=excluded.author,
                state=excluded.state,
                created=excluded.created,
                merged=excluded.merged,
                first_review_minutes=excluded.first_review_minutes,
                merge_minutes=excluded.merge_minutes,
                services=excluded.services,
                environments=excluded.environments,
                applications=excluded.applications,
                paths=excluded.paths,
                reviewers=excluded.reviewers,
                approvers=excluded.approvers,
                first_review_at=excluded.first_review_at,
                latest_review_at=excluded.latest_review_at,
                has_review=excluded.has_review,
                has_approval=excluded.has_approval,
                has_changes_requested=excluded.has_changes_requested,
                merged_by=excluded.merged_by,
                closed_at=excluded.closed_at,
                closed_by=excluded.closed_by
        ''', (
            p['repo'],
            p['number'],
            p['title'],
            p['url'],
            p['author'],
            p['state'],
            p['created'],
            p['merged'],
            p['first_review_minutes'],
            p['merge_minutes'],
            json.dumps(p.get('services', [])),
            json.dumps(p.get('environments', [])),
            json.dumps(p.get('applications', [])),
            json.dumps(p.get('paths', [])),
            json.dumps(p.get('reviewers', [])),
            json.dumps(p.get('approvers', [])),
            p.get('first_review_at'),
            p.get('latest_review_at'),
            int(bool(p.get('has_review', False))),
            int(bool(p.get('has_approval', False))),
            int(bool(p.get('has_changes_requested', False))),
            p.get('merged_by'),
            p.get('closed_at'),
            p.get('closed_by')
        ))

def rows(path):
    with db(path) as c: data=[dict(x) for x in c.execute('SELECT * FROM prs ORDER BY created DESC')]
    for r in data:
        for k in ('services','environments','applications','paths','reviewers','approvers'): r[k]=json.loads(r[k] or '[]')
    return data

def rows_for_active_repositories(path):
    data = rows(path)

    with db(path) as c:
        active_repos = {
            row['repo_full_name']
            for row in c.execute(
                'SELECT repo_full_name FROM repositories WHERE is_active = 1'
            ).fetchall()
        }

    return [
        r for r in data
        if r['repo'] in active_repos
    ]

def summary(data):
    merged=[r for r in data if r['state']=='merged']; opened=[r for r in data if r['state']=='open']
    reviews=[r['first_review_minutes'] for r in data if r['first_review_minutes'] is not None]
    merges=[r['merge_minutes'] for r in merged if r['merge_minutes'] is not None]
    dimensions={k: sorted({x for r in data for x in r[k]}) for k in ('services','environments','applications')}
    counts={k:{x:sum(x in r[k] for r in data) for x in dimensions[k]} for k in dimensions}
    dimensions['repositories'] = sorted({r['repo'] for r in data})
    return {'total':len(data),'open':len(opened),'merged':len(merged),'closed':sum(r['state']=='closed' for r in data),'avg_review':round(mean(reviews)/60,1) if reviews else None,'avg_merge':round(mean(merges)/60,1) if merges else None,'dimensions':dimensions,'counts':counts}

def save_event(path, event):
    with db(path) as c:
        c.execute('''
            INSERT INTO pr_events (
                event_key, repo, pr_number, event_type,
                actor, target, created_at, commit_sha,
                message, url, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(event_key) DO UPDATE SET
                event_type=excluded.event_type,
                actor=excluded.actor,
                target=excluded.target,
                created_at=excluded.created_at,
                commit_sha=excluded.commit_sha,
                message=excluded.message,
                url=excluded.url,
                raw_json=excluded.raw_json
        ''', (
            event['event_key'],
            event['repo'],
            event['pr_number'],
            event['event_type'],
            event.get('actor'),
            event.get('target'),
            event.get('created_at'),
            event.get('commit_sha'),
            event.get('message'),
            event.get('url'),
            json.dumps(event.get('raw_json', {}))
        ))

def save_review(path, review):
    with db(path) as c:
        c.execute('''
            INSERT INTO pr_reviews (
                review_id, repo, pr_number, reviewer,
                review_state, submitted_at, commit_id, html_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(review_id) DO UPDATE SET
                reviewer=excluded.reviewer,
                review_state=excluded.review_state,
                submitted_at=excluded.submitted_at,
                commit_id=excluded.commit_id,
                html_url=excluded.html_url
        ''', (
            review['review_id'],
            review['repo'],
            review['pr_number'],
            review.get('reviewer'),
            review.get('review_state'),
            review.get('submitted_at'),
            review.get('commit_id'),
            review.get('html_url')
        ))



def audit_events(path, repo=None, pr_number=None):
    query = '''
        SELECT
            repo,
            pr_number,
            event_type AS activity_type,
            actor,
            target,
            created_at,
            message AS details,
            url
        FROM pr_events
        WHERE event_type != 'reviewed'

        UNION ALL

        SELECT
            repo,
            pr_number,
            'review_submitted' AS activity_type,
            reviewer AS actor,
            NULL AS target,
            submitted_at AS created_at,
            review_state AS details,
            html_url AS url
        FROM pr_reviews
        UNION ALL

        SELECT
            repo,
            number AS pr_number,
            'created' AS activity_type,
            author AS actor,
            NULL AS target,
            created AS created_at,
            NULL AS details,
            NULL AS url
        FROM prs
    '''

    # Wrap the UNION before applying filters
    query = f'''
        SELECT *
        FROM ({query}) AS combined_events
    '''

    conditions = []
    params = []

    if repo:
        conditions.append('repo = ?')
        params.append(repo)

    if pr_number is not None:
        conditions.append('pr_number = ?')
        params.append(pr_number)

    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)

    query += '''
        ORDER BY
            CASE WHEN created_at IS NULL THEN 1 ELSE 0 END,
            created_at DESC
    '''

    with db(path) as c:
        result = c.execute(query, params).fetchall()

    return [dict(row) for row in result]


def claim_webhook_delivery(path, delivery_id, event_name, action):
    with db(path) as c:
        cursor = c.execute('''
            INSERT INTO webhook_deliveries (
                delivery_id, event_name, action, status,
                received_at, processed_at
            )
            VALUES (
                ?, ?, ?, 'processing',
                CURRENT_TIMESTAMP, NULL
            )
            ON CONFLICT(delivery_id) DO UPDATE SET
                status = 'processing',
                received_at = CURRENT_TIMESTAMP,
                processed_at = NULL,
                event_name = excluded.event_name,
                action = excluded.action
            WHERE
                webhook_deliveries.status = 'processing'
                AND webhook_deliveries.received_at
                    < datetime('now', '-15 minutes')
        ''', (delivery_id, event_name, action))

        return cursor.rowcount == 1



def complete_webhook_delivery(path, delivery_id):
    with db(path) as c:
        c.execute('''
            UPDATE webhook_deliveries
            SET status = 'completed',
                processed_at = CURRENT_TIMESTAMP
            WHERE delivery_id = ?
        ''', (delivery_id,))


def release_webhook_delivery(path, delivery_id):
    with db(path) as c:
        c.execute('''
            DELETE FROM webhook_deliveries
            WHERE delivery_id = ?
              AND status = 'processing'
        ''', (delivery_id,))

def get_repositories(path):
    with db(path) as c:
        result = c.execute('''
            SELECT
                id,
                repo_full_name,
                config_name,
                component_owner,
                is_active,
                created_at
            FROM repositories
            ORDER BY repo_full_name
        ''').fetchall()

    return [dict(row) for row in result]

def add_repository(path, repo_full_name, config_name, component_owner=None):
    with db(path) as c:
        cursor = c.execute('''
            INSERT INTO repositories (
                repo_full_name,
                config_name,
                component_owner
            )
            VALUES (?, ?, ?)
        ''', (repo_full_name, config_name, component_owner))

        return cursor.lastrowid
def add_service(path, service_name, repository_id, component_owner=None):
    with db(path) as c:
        cursor = c.execute('''
            INSERT INTO services (
                service_name,
                repository_id,
                component_owner
            )
            VALUES (?, ?, ?)
        ''', (service_name, repository_id, component_owner))

        return cursor.lastrowid
    
def get_services(path):
    with db(path) as c:
        result = c.execute('''
            SELECT
                s.id,
                s.service_name,
                s.repository_id,
                r.repo_full_name,
                s.component_owner,
                s.is_active,
                s.created_at
            FROM services s
            JOIN repositories r
                ON s.repository_id = r.id
            ORDER BY s.service_name
        ''').fetchall()

    return [dict(row) for row in result]

def set_repository_active(path, repository_id, is_active):
    with db(path) as c:
        cursor = c.execute('''
            UPDATE repositories
            SET is_active = ?
            WHERE id = ?
        ''', (1 if is_active else 0, repository_id))

        return cursor.rowcount == 1