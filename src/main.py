#!/usr/bin/env python3
"""Store a merged PR's haste results and chart every stored PR against the first."""
import argparse
import collections
import datetime
import html
import io
import json
import os
import re
import statistics
import string
import sys
import tomllib
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypedDict

TEMPLATE = Path(__file__).with_name("template.html")
OUT_FILE = Path("site/index.html")


class PageTemplate(string.Template):
    delimiter = "@"


class Pr(TypedDict):
    number: int
    title: str
    date: str
    data_toml: str  # data.toml from the haste.zip attached to the PR


def get(url: str) -> bytes:
    req = urllib.request.Request(url)
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def attachment_url(body: str | None, name: str) -> str | None:
    """URL of the first <name> attached to a PR description."""
    m = re.search(rf"https://github\.com/user-attachments/files/\d+/{re.escape(name)}", body or "")
    return m[0] if m else None


def store(repo: str, sha: str, results: Path, fetch: Callable[[str], bytes] = get) -> int | None:
    """Extract data.toml and extra.toml from the haste.zip attached to the PR that <sha> merged
    to <results>/<pr>/. Returns the PR number, or None if <sha> merged no PR with a haste.zip
    holding a data.toml."""
    pulls = json.loads(fetch(f"https://api.github.com/repos/{repo}/commits/{sha}/pulls"))
    # Also lists open PRs that contain <sha>.
    pr = next((pr for pr in pulls if pr["merge_commit_sha"] == sha), None)
    url = pr and attachment_url(pr["body"], "haste.zip")
    if not url:
        return None
    z = zipfile.ZipFile(io.BytesIO(fetch(url)))
    if "data.toml" not in z.namelist():
        return None
    out = results / str(pr["number"])
    out.mkdir(parents=True, exist_ok=True)
    for name in ("data.toml", "extra.toml"):
        if name in z.namelist():
            (out / name).write_bytes(z.read(name))
    (out / "pr.json").write_text(json.dumps(dict(title=pr["title"], date=pr["merged_at"])))
    return pr["number"]


def load_prs(results: Path) -> list[Pr]:
    """Every <results>/<pr>/, oldest merge first. Loose files in <results> are skipped."""
    prs = []
    for meta_file in results.glob("*/pr.json"):
        d = meta_file.parent
        meta = json.loads(meta_file.read_text())
        prs.append(Pr(number=int(d.name), title=meta["title"], date=meta["date"],
                      data_toml=(d / "data.toml").read_text()))
    return sorted(prs, key=lambda pr: pr["date"])


def page_data(repo: str, prs: list[Pr]) -> dict[str, Any]:
    """Everything template.html shows, in the order it shows it. The first PR is the
    baseline."""
    measured = []
    for pr in prs:
        ms: dict[str, float] = {}  # {benchmark: median wallclock ms}
        try:
            for key, runs in tomllib.loads(pr["data_toml"])["data"].items():
                # haste keys look like "<benchmark>/<executor>/<arguments>". Neither the
                # executor nor the arguments are charted, so each benchmark must appear once.
                benchmark = key.split("/", 1)[0]
                assert benchmark not in ms, \
                    f"{key}: {benchmark} already seen; expected one executor and one argument"
                ms[benchmark] = statistics.median(runs)
        except Exception as e:
            e.add_note(f"in data.toml from PR #{pr['number']}")
            raise
        measured.append((pr, ms))
    baseline = measured[0][1] if measured else {}

    points = collections.defaultdict(list)
    out_prs = []
    for pr, ms in measured:
        meta = dict(pr=pr["number"], date=pr["date"], title=pr["title"])
        for benchmark, t in ms.items():
            points[benchmark].append(dict(meta, ms=round(t)))
        # Geomean of time / baseline time, only for PRs that ran every baseline benchmark so
        # that the points are comparable.
        geomean = None
        if baseline.keys() <= ms.keys():
            geomean = round(statistics.geometric_mean([ms[b] / baseline[b] for b in baseline]), 3)
        out_prs.append(dict(meta, geomean=geomean))

    return dict(repo=repo, base=prs[0]["number"] if prs else None, prs=out_prs,
                benchmarks=[dict(name=b, points=points[b]) for b in sorted(points)])


def render(page: dict[str, Any], generated: str) -> str:
    """index.html for page_data's result. PR titles are untrusted: with every "<" in the
    embedded JSON escaped, no title can end or reopen the <script> early."""
    return PageTemplate(TEMPLATE.read_text()).substitute(
        REPO=html.escape(page["repo"]),
        GENERATED=generated,
        PAGE=json.dumps(page, separators=(",", ":")).replace("<", "\\u003c"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", help="owner/repo")
    parser.add_argument("results", type=Path, help="directory with one <pr>/ per PR")
    parser.add_argument("--store", metavar="SHA",
                        help="first store the results attached to the PR that SHA merged")
    args = parser.parse_args()

    if args.store:
        pr = store(args.repo, args.store, args.results)
        if pr:
            print(f"stored PR #{pr}")
    page = page_data(args.repo, load_prs(args.results))
    OUT_FILE.parent.mkdir(exist_ok=True)
    OUT_FILE.write_text(render(page, datetime.datetime.now(datetime.UTC)
                               .strftime("%Y-%m-%d %H:%M UTC")))
    print(f"{len(page['prs'])} PRs charted")
    print(f"html written: {OUT_FILE.resolve()}")


if __name__ == "__main__":
    main()
