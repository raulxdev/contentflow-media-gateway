import os
import subprocess

import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_HEADERS = {
    "Authorization": f"token {os.getenv('GITHUB_TOKEN', '')}",
    "Accept": "application/vnd.github.v3+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def create_private_repo(repo_name: str, description: str):
    response = requests.post(
        "https://api.github.com/user/repos",
        json={"name": repo_name, "description": description, "private": True, "auto_init": False},
        headers=GITHUB_HEADERS,
        timeout=30,
    )
    if response.status_code == 201:
        repo = response.json()
        return repo["owner"]["login"], repo["name"], repo["id"]
    if response.status_code == 422:
        owner = requests.get("https://api.github.com/user", headers=GITHUB_HEADERS, timeout=30).json()["login"]
        repo = requests.get(f"https://api.github.com/repos/{owner}/{repo_name}", headers=GITHUB_HEADERS, timeout=30).json()
        return repo["owner"]["login"], repo["name"], repo["id"]
    raise RuntimeError(f"GitHub repo creation failed: {response.status_code} {response.text[:200]}")


def grant_github_app_access(repo_id: int, installation_id: int) -> None:
    response = requests.put(
        f"https://api.github.com/user/installations/{installation_id}/repositories/{repo_id}",
        headers=GITHUB_HEADERS,
        timeout=30,
    )
    if response.status_code not in {204, 304}:
        raise RuntimeError(f"GitHub App access failed: {response.status_code} {response.text[:200]}")


def initialize_and_push(repo_name: str, owner: str) -> None:
    token = os.getenv("GITHUB_TOKEN")
    remote_url = f"https://{token}@github.com/{owner}/{repo_name}.git"
    if not os.path.exists(".git"):
        subprocess.run(["git", "init"], check=True)
    subprocess.run(["git", "remote", "remove", "origin"], stderr=subprocess.DEVNULL)
    subprocess.run(["git", "remote", "add", "origin", remote_url], check=True)
    subprocess.run(["git", "add", "."], check=True)
    commit = subprocess.run(["git", "commit", "-m", f"initial: {repo_name}"], text=True, capture_output=True)
    if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr).lower():
        raise RuntimeError(commit.stderr or commit.stdout)
    subprocess.run(["git", "branch", "-M", "main"], check=True)
    subprocess.run(["git", "push", "-u", "origin", "main", "--force"], check=True)
