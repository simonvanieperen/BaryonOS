#!/usr/bin/env python3
"""Required `merge-hold` check: block merging while out-of-band acceptance is pending.

A pull request labelled `acceptance-pending` passes only when a trusted
participant (author association OWNER, MEMBER or COLLABORATOR) has commented
the exact line `acceptance-released: <head commit SHA>`. Labels and comments
are read live through the REST API, so event ordering and re-runs cannot
replay a stale decision. A new push changes the head SHA and re-arms the hold
automatically. Any API or input error fails closed. See ADR-MERGE-HOLD-20261113.
"""

import json
import os
import re
import sys
from urllib import request

LABEL = "acceptance-pending"
RELEASE_PREFIX = "acceptance-released: "
TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
SHA = re.compile(r"[0-9a-f]{40}")
MAX_PAGES = 50


def decide(labels, comments, head_sha):
    """Return (passed, message) for one pull request head."""
    if not SHA.fullmatch(head_sha or ""):
        return False, "Head SHA is missing or malformed; failing closed."
    if LABEL not in labels:
        return True, "No acceptance hold is set."
    release = RELEASE_PREFIX + head_sha
    for comment in comments:
        if comment.get("author_association") not in TRUSTED:
            continue
        lines = (comment.get("body") or "").replace("\r", "").split("\n")
        if any(line.strip() == release for line in lines):
            return True, f"Acceptance released for {head_sha}."
    return False, (
        f"The '{LABEL}' label is set and no trusted '{release}' comment exists. "
        "Post it only after the required acceptance has passed on this head commit."
    )


def fetch_all(token, url):
    """Read every page of a REST list endpoint; raise on any failure."""
    items, page = [], 1
    while True:
        req = request.Request(
            f"{url}?per_page=100&page={page}",
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "baryon-merge-hold",
            },
        )
        with request.urlopen(req, timeout=20) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise TypeError("Unexpected API response")
        items.extend(batch)
        if len(batch) < 100:
            return items
        page += 1
        if page > MAX_PAGES:
            raise ValueError("Too many pages")


def main():
    try:
        token = os.environ["GH_TOKEN"]
        repo = os.environ["REPO"]
        number = int(os.environ["PR_NUMBER"])
        head_sha = os.environ["HEAD_SHA"]
        base = f"https://api.github.com/repos/{repo}/issues/{number}"
        labels = [item["name"] for item in fetch_all(token, base + "/labels")]
        comments = fetch_all(token, base + "/comments") if LABEL in labels else []
    except (KeyError, ValueError, TypeError, OSError) as exc:
        print(f"::error::merge-hold could not read the pull request ({exc}); failing closed.")
        return 1
    passed, message = decide(labels, comments, head_sha)
    print(message if passed else "::error::" + message)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
