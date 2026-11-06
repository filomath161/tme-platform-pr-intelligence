import requests
API = 'https://api.github.com'

class GitHubClient:
    def __init__(self, token):
        self.s = requests.Session()
        self.s.headers.update({'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
    def _all(self, url, params=None):
        result = []
        while url:
            r = self.s.get(url, params=params, timeout=30); r.raise_for_status()
            result.extend(r.json()); url = r.links.get('next', {}).get('url'); params = None
        return result
    def prs(self, repo): return self._all(f'{API}/repos/{repo}/pulls', {'state':'all','per_page':100})
    def pr(self, repo, number):
        r=self.s.get(f'{API}/repos/{repo}/pulls/{number}',timeout=30); r.raise_for_status(); return r.json()
    def files(self, repo, number): return self._all(f'{API}/repos/{repo}/pulls/{number}/files', {'per_page':100})
    def reviews(self, repo, number): return self._all(f'{API}/repos/{repo}/pulls/{number}/reviews', {'per_page':100})
    def timeline(self, repo, number):
        return self._all(
            f'{API}/repos/{repo}/issues/{number}/timeline',
            {'per_page': 100}
    )
