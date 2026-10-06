"""Details of every non-maintainer pull request of Kunzisoft/KeePassDX: size, files, discussion.

uv run python fetch_prs.py pulls.jsonl details.json
"""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

REPO = "Kunzisoft/KeePassDX"


def api(path: str):
    out = subprocess.run(["gh", "api", "--paginate", path], capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        return {"error": out.stderr.strip()}
    text = out.stdout.strip()
    # --paginate concatenates JSON arrays: "][" between pages
    return json.loads(text.replace("][", ","))


def detail(number: int) -> dict:
    pr = api(f"repos/{REPO}/pulls/{number}")
    files = api(f"repos/{REPO}/pulls/{number}/files")
    issue_comments = api(f"repos/{REPO}/issues/{number}/comments")
    review_comments = api(f"repos/{REPO}/pulls/{number}/comments")
    reviews = api(f"repos/{REPO}/pulls/{number}/reviews")
    commits = api(f"repos/{REPO}/pulls/{number}/commits")

    def talk(items):
        return [
            {"who": c["user"]["login"], "assoc": c.get("author_association"), "at": c.get("created_at") or c.get("submitted_at"),
             "state": c.get("state"), "body": c.get("body") or ""}
            for c in items if isinstance(c, dict) and c.get("user")
        ]

    return {
        "number": number,
        "additions": pr.get("additions"), "deletions": pr.get("deletions"), "changed_files": pr.get("changed_files"),
        "commits": pr.get("commits"), "merged_by": (pr.get("merged_by") or {}).get("login"),
        "mergeable_state": pr.get("mergeable_state"), "head_repo_fork": (pr.get("head", {}).get("repo") or {}).get("fork"),
        "files": [f["filename"] for f in files] if isinstance(files, list) else [],
        "commit_messages": [c["commit"]["message"].split("\n")[0] for c in commits] if isinstance(commits, list) else [],
        "issue_comments": talk(issue_comments) if isinstance(issue_comments, list) else [],
        "review_comments": talk(review_comments) if isinstance(review_comments, list) else [],
        "reviews": talk(reviews) if isinstance(reviews, list) else [],
    }


def main() -> None:
    pulls = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
    wanted = [p["number"] for p in pulls if p["assoc"] in ("CONTRIBUTOR", "NONE")]
    with ThreadPoolExecutor(6) as pool:
        details = list(pool.map(detail, wanted))
    json.dump(details, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
    print(len(details), "pull requests")


main()
