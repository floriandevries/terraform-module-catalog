from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
REGISTRY = "https://registry.terraform.io/v1/providers/hashicorp/azurerm/versions"
STRING = r'"(?:\\.|[^"\\])*"'
COMMENT_RE = re.compile(STRING + r"|(?P<c>/\*.*?\*/|//[^\n]*|#[^\n]*)", re.S)
RELEASE_RE = re.compile(r"^v\d+\.\d+\.\d+$")
STABLE_RE = re.compile(r"^\d+\.\d+\.\d+$")
NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')
STRING_RE = re.compile(STRING)


def strip_comments(text: str) -> str:
    return COMMENT_RE.sub(lambda m: "" if m.group("c") else m.group(0), text)


def block_body(text: str, open_idx: int) -> str | None:
    depth = 0
    i = open_idx
    while i < len(text):
        s = STRING_RE.match(text, i)
        if s:
            i = s.end()
            continue
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i]
        i += 1
    return None


def extract_azurerm_constraint(tf_text: str) -> str | None:
    text = strip_comments(tf_text)
    for rp in re.finditer(r"\brequired_providers\s*\{", text):
        providers = block_body(text, rp.end() - 1)
        if providers is None:
            continue
        for entry in re.finditer(r"(?<![\w-])azurerm\s*=\s*\{", providers):
            body = block_body(providers, entry.end() - 1)
            if body is None:
                continue
            source = re.search(r'\bsource\s*=\s*"([^"]*)"', body)
            if source and source.group(1).lower() not in ("hashicorp/azurerm", "registry.terraform.io/hashicorp/azurerm"):
                continue
            version = re.search(r'\bversion\s*=\s*"([^"]*)"', body)
            if version:
                return version.group(1)
    return None


def is_release_tag(name: str) -> bool:
    return bool(RELEASE_RE.match(name))


class GitHub:
    def __init__(self, token: str):
        self.token = token

    def _open(self, url: str, accept: str):
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + self.token,
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
        })
        return urllib.request.urlopen(req, timeout=60)

    def _json_pages(self, url: str):
        while url:
            with self._open(url, "application/vnd.github+json") as r:
                data = json.load(r)
                link = r.headers.get("Link") or ""
            yield data
            m = NEXT_RE.search(link)
            url = m.group(1) if m else None

    def search_repos(self, owner: str) -> list[str]:
        url = "%s/search/repositories?q=user:%s+topic:terraform+topic:azurerm&per_page=100" % (API, owner)
        names = []
        for page in self._json_pages(url):
            if page.get("incomplete_results"):
                raise urllib.error.URLError("incomplete search results")
            names.extend(i["name"] for i in page["items"])
        return sorted(names)

    def tags(self, owner: str, repo: str) -> list[tuple[str, str]]:
        url = "%s/repos/%s/%s/tags?per_page=100" % (API, owner, repo)
        return [(t["name"], t["commit"]["sha"]) for page in self._json_pages(url) for t in page]

    def root_tf_texts(self, owner: str, repo: str, ref: str) -> list[str]:
        url = "%s/repos/%s/%s/contents?ref=%s" % (API, owner, repo, urllib.parse.quote(ref, safe=""))
        texts = []
        with self._open(url, "application/vnd.github+json") as r:
            entries = json.load(r)
        for e in entries:
            if e["type"] == "file" and e["name"].endswith(".tf"):
                with self._open(e["url"], "application/vnd.github.raw") as r:
                    texts.append(r.read().decode("utf-8", "replace"))
        return texts

    def azurerm_versions(self) -> list[str]:
        req = urllib.request.Request(REGISTRY, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        stable = {v["version"] for v in data["versions"] if STABLE_RE.match(v["version"])}
        return sorted(stable, key=lambda v: tuple(int(p) for p in v.split(".")), reverse=True)


def scan(owner: str, previous: dict | None, gh, now: str) -> dict:
    old_modules = (previous or {}).get("modules", {})
    modules = {}
    for repo in gh.search_repos(owner):
        old_tags = old_modules.get(repo, {}).get("tags", {})
        tags = {}
        for name, sha in gh.tags(owner, repo):
            if not is_release_tag(name):
                continue
            if old_tags.get(name, {}).get("sha") == sha:
                tags[name] = old_tags[name]
                continue
            constraint = None
            for text in gh.root_tf_texts(owner, repo, name):
                constraint = extract_azurerm_constraint(text)
                if constraint is not None:
                    break
            tags[name] = {"sha": sha, "constraint": constraint}
        modules[repo] = {"url": "https://github.com/%s/%s" % (owner, repo), "tags": tags}
    versions = gh.azurerm_versions()
    changed = (
        previous is None
        or previous.get("azurerm_versions") != versions
        or previous.get("modules") != modules
    )
    return {
        "owner": owner,
        "updated_at": now if changed else previous["updated_at"],
        "azurerm_versions": versions,
        "modules": modules,
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    token = os.environ.get("GH_TOKEN")
    if not token:
        print("GH_TOKEN is not set", file=sys.stderr)
        return 1
    previous = None
    existing = None
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            existing = f.read()
        try:
            previous = json.loads(existing)
        except ValueError:
            previous = None
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        result = scan(args.owner, previous, GitHub(token), now)
    except urllib.error.URLError as e:
        print("scan failed: %s" % e, file=sys.stderr)
        return 1
    content = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if content != existing:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(content)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
