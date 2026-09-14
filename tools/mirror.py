#!/usr/bin/env python3
"""Mirror the latest release assets of every NUSV project into ./public.

Output (committed to the NUSV/downloads repository by the workflow):

  public/<repo-slug>/<asset file>      - the actual release files
  public/downloads.json                - machine-readable manifest, consumed
                                         by the nusv.github.io generator
  public/index.html                    - a small human-readable listing
  public/.nojekyll                     - disable Jekyll processing

Only the *latest* release of each project is mirrored, so the published site
stays small. The downloads repository history is rewritten on every run
(orphan commit, force push) by the workflow, which keeps the repository at
roughly the size of one snapshot forever.

Discovery rule matches the website: org repos tagged "nusv-project".

Run: python3 tools/mirror.py
"""

import datetime
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
ORG = "NUSV"
PROJECT_TOPIC = "nusv-project"
PUBLIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public")
BASE_URL = "https://nusv.github.io/downloads"

MAX_FILE = 95 * 1024 * 1024        # GitHub rejects files >= 100 MB
MAX_TOTAL = 900 * 1024 * 1024      # stay well under Pages soft limits


def gh_json(url, token):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "nusv-mirror")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def discover(token):
    repos = gh_json("%s/orgs/%s/repos?per_page=100&type=public" % (API, ORG), token) or []
    out = []
    for r in sorted(repos, key=lambda x: (x.get("name") or "").lower()):
        name = r.get("name")
        if r.get("fork"):
            continue
        topics = gh_json("%s/repos/%s/%s/topics" % (API, ORG, name), token) or {}
        if PROJECT_TOPIC in (topics.get("names") or []):
            out.append(name)
    return out


def latest_release(repo, token):
    data = gh_json("%s/repos/%s/%s/releases/latest" % (API, ORG, repo), token)
    return data


def download(url, dest):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "nusv-mirror")
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)


def human_size(num):
    num = num or 0
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return ("%.0f %s" % (num, unit)) if unit == "B" else ("%.1f %s" % (num, unit))
        num /= 1024.0
    return str(num)


def main():
    token = os.environ.get("NUSV_SYNC_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if os.path.isdir(PUBLIC):
        for root, dirs, files in os.walk(PUBLIC, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
    os.makedirs(PUBLIC, exist_ok=True)

    manifest = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "base_url": BASE_URL,
        "repos": {},
    }

    total = 0
    for repo in discover(token):
        rel = latest_release(repo, token)
        if not rel:
            print("%s: no releases, skipped" % repo)
            continue
        slug = re.sub(r"[^a-z0-9-]+", "-", repo.lower()).strip("-")
        tag = rel.get("tag_name", "")
        entry = {"tag": tag, "name": rel.get("name") or tag, "assets": []}
        for a in rel.get("assets", []):
            name = a.get("name", "")
            size = a.get("size", 0)
            if not name:
                continue
            if size > MAX_FILE:
                print("%s/%s: %.1f MB > file cap, skipped" % (repo, name, size / 1048576.0))
                continue
            if total + size > MAX_TOTAL:
                print("%s/%s: total mirror cap reached, skipped" % (repo, name))
                continue
            dest_dir = os.path.join(PUBLIC, slug)
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, name)
            print("downloading %s/%s (%.1f MB)..." % (repo, name, size / 1048576.0))
            try:
                download(a["browser_download_url"], dest)
            except Exception as e:  # noqa: BLE001
                print("  FAILED: %s" % e)
                if os.path.exists(dest):
                    os.remove(dest)
                continue
            real = os.path.getsize(dest)
            total += real
            entry["assets"].append(
                {
                    "name": name,
                    "size": real,
                    "mirror": "%s/%s/%s" % (BASE_URL, slug, name),
                    "github": a["browser_download_url"],
                }
            )
        if entry["assets"]:
            manifest["repos"][repo] = entry
            print("%s: mirrored %d asset(s) for %s" % (repo, len(entry["assets"]), tag))

    with open(os.path.join(PUBLIC, "downloads.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with open(os.path.join(PUBLIC, ".nojekyll"), "w", encoding="utf-8") as f:
        f.write("")

    rows = []
    for repo, entry in manifest["repos"].items():
        for a in entry["assets"]:
            rows.append(
                '<li><a href="%s"><b>%s</b></a> <span>%s &middot; %s</span></li>'
                % (
                    html.escape(a["mirror"], quote=True),
                    html.escape(a["name"]),
                    html.escape(repo),
                    human_size(a["size"]),
                )
            )
    with open(os.path.join(PUBLIC, "index.html"), "w", encoding="utf-8") as f:
        f.write(
            """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NUSV Downloads (mirror)</title>
<style>
body{background:#070b14;color:#e6edf7;font-family:'Segoe UI',-apple-system,Helvetica,Arial,sans-serif;max-width:820px;margin:40px auto;padding:0 22px;line-height:1.7}
a{color:#22d3ee}h1{letter-spacing:-.02em}li{margin:10px 0}li span{color:#8ea0b8;font-size:13px;margin-left:8px}
.note{color:#8ea0b8;font-size:14px;border:1px solid rgba(148,163,184,.2);border-radius:10px;padding:12px 16px;background:rgba(148,163,184,.06)}
</style>
</head>
<body>
<h1>NUSV Downloads</h1>
<p class="note">Mirror of the latest release assets, generated %s UTC. Main site: <a href="https://nusv.github.io/">nusv.github.io</a></p>
<ul>
%s
</ul>
</body>
</html>
"""
            % (manifest["generated_at"], "\n".join(rows))
        )

    print("done: %d project(s), %.1f MB total" % (len(manifest["repos"]), total / 1048576.0))
    sys.exit(0)


if __name__ == "__main__":
    main()
