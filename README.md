# Platform PR Analytics Dashboard (local MVP)

Flask + AdminLTE + GitHub REST API + SQLite.

## What this starter does

- Syncs pull requests from configured GitHub repositories.
- Collects PR metadata, changed files, reviews and approval reviewers.
- Parses `service/environment/environment_application_config.yml`.
- Shows repository, service, environment, application and PR-state summaries.
- Stores snapshots locally in SQLite so refreshes do not require rebuilding the database.

## 1. Requirements

- Python 3.10+
- A GitHub personal access token with read access to the repositories' metadata and pull requests.
- Internet access for GitHub API and the AdminLTE CDN.

## 2. Set up

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1

pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:
- Set `GITHUB_TOKEN`.
- Set `GITHUB_REPOS` to comma-separated `owner/repo` values.
- Keep the token private; never commit `.env`.

Example:
`GITHUB_REPOS=filomath161/tme-config-demo,filomath161/tme-eks-demo`

When you're ready to query the real central GitOps repository, add its exact `owner/repo` to `GITHUB_REPOS`.

## 3. Run

```bash
python app.py
```

Open http://127.0.0.1:5000 and click **Sync from GitHub**.

## Path parser convention

Expected path:
`<service>/<environment>/<environment>_<application>_config.yml`

Examples:
- `mft/dev/dev_nokia_config.yml` -> service `mft`, environment `dev`, application `nokia`
- `mft/uat/uat_nokia_config.yml` -> service `mft`, environment `uat`, application `nokia`
- `backup/prod/prod_billing_api_config.yaml` -> service `backup`, environment `prod`, application `billing api`

Paths that do not match the convention are ignored for service/application/environment breakdown, but the PR itself remains in the overall PR table.

## Important first-version limitations

- A PR touching multiple matching files is associated with every distinct service/environment/application found in those paths. The same PR remains one row in the PR table.
- Summary counts are PR-to-dimension counts, not unique PR totals across every dimension. Adding service counts together can exceed total PRs when a PR changes multiple services.
- This starter fetches all PRs each time you sync. That is acceptable for a small MVP, but should later be replaced with incremental sync and rate-limit-aware caching for 10–30 repositories.
- The first review timestamp is approximated from submitted review records. Comments without formal reviews are not counted as reviews.
- The starter UI uses AdminLTE 4.10.0 CDN assets. It needs internet access. This starter uses AdminLTE 4.10.0 with Bootstrap 5 and vanilla JavaScript (no jQuery).
- GitHub rulesets/CODEOWNERS govern repository behavior; the dashboard only reports recorded activity and does not enforce review permissions.

## Suggested next steps

1. Confirm the app runs and the demo repositories sync.
2. Add the central `tme-config` repository.
3. Validate parser results against a few real PRs.
4. Add date filters, trend charts, reviewer workload and export.
5. Add incremental sync and scheduled refresh after the data model is validated.
# tme-platform-pr-intelligence
GitOps visibility · PR auditability · SLA governance · Engineering analytics

A configurable PR governance and engineering analytics platform that provides centralized visibility into pull-request activity, ownership, audit history, and SLA compliance across TME repositories.
