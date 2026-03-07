import requests


class GitHubAPI:
    def __init__(self, token: str):
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def get_user(self):
        r = requests.get("https://api.github.com/user", headers=self.headers)
        r.raise_for_status()
        return r.json()

    def get_all_repos(self):
        repos, page = [], 1
        while True:
            r = requests.get(
                "https://api.github.com/user/repos",
                headers=self.headers,
                params={"per_page": 100, "page": page, "affiliation": "owner"},
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            repos.extend(batch)
            page += 1
        return repos
