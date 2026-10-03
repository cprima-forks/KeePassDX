"""Build upstream-fit/pull-requests.csv from the API data and the coding of the comments.

Usage:
    uv run python cprima-fork/tools/upstream_fit/make_pr_table.py PULLS.jsonl DETAILS.json CODED.json OUT.csv

PULLS.jsonl   one JSON object per pull request of the repository (REST: GET /repos/{repo}/pulls?state=all)
DETAILS.json  fetch_prs.py: size, files, commits and every comment of each non-maintainer pull request
CODED.json    the coding of those comments (one record per pull request, the keys listed in CODING_KEYS)

Facts from the API are copied as they are. The coded columns (kind, reason, requests, ...) come from reading
the comments; the quotes in them were checked against the comments, 95 of 98 are verbatim (see method.md).
Handles of people other than the maintainer are replaced: the pull requests are cited by number.
"""

import csv
import json
import re
import sys
from datetime import datetime

CODING_KEYS = ("kind", "maintainer_stated_reason", "maintainer_requests", "author_responded_to_requests",
               "taken_over", "discussed_before", "body_quality", "process_notes")


def days(start: str, end: str | None) -> int | str:
    if not end:
        return ""
    return (datetime.fromisoformat(end.rstrip("Z")) - datetime.fromisoformat(start.rstrip("Z"))).days


KEEP = {"J-Jamet", "Copilot"}  # the maintainer, and a product


def scrub(text: str, handles: set[str]) -> str:
    """Names of other people do not belong in the table: the pull requests are cited by number."""
    for handle in sorted(handles - KEEP, key=len, reverse=True):
        text = re.sub(r"(?<![\w-])@?" + re.escape(handle) + r"(?![\w-])", "[a participant]", text, flags=re.I)
    return text


def main() -> int:
    pulls_file, details_file, coded_file, out = sys.argv[1:5]
    pulls = {}
    for line in open(pulls_file, encoding="utf-8"):
        pull = json.loads(line)
        pulls[pull["number"]] = pull
    details = {d["number"]: d for d in json.load(open(details_file, encoding="utf-8"))}
    coded = {c["number"]: c for c in json.load(open(coded_file, encoding="utf-8"))}

    handles = {p["login"] for p in pulls.values()}
    for detail in details.values():
        handles |= {t["who"] for t in detail["issue_comments"] + detail["review_comments"] + detail["reviews"]}

    columns = ["number", "author_association", "outcome", "base", "created", "ended", "days_open", "additions",
               "deletions", "files", "commits", "comments_by_maintainer", "comments_by_others", *CODING_KEYS, "title"]
    with open(out, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for number in sorted(coded):
            pull, detail, code = pulls[number], details[number], coded[number]
            talk = detail["issue_comments"] + detail["review_comments"] + detail["reviews"]
            talk = [t for t in talk if (t["body"] or "").strip()]
            ended = pull["merged_at"] or pull["closed_at"]
            outcome = "merged" if pull["merged_at"] else ("open" if pull["state"] == "open" else "closed")
            writer.writerow([
                number, pull["assoc"], outcome, pull["base"], pull["created_at"][:10], (ended or "")[:10],
                days(pull["created_at"], ended), detail["additions"], detail["deletions"], detail["changed_files"],
                detail["commits"], sum(t["who"] == "J-Jamet" for t in talk), sum(t["who"] != "J-Jamet" for t in talk),
                code["kind"], scrub(code["maintainer_stated_reason"], handles),
                scrub(" ; ".join(code["maintainer_requests"]), handles),
                code["author_responded_to_requests"], str(code["taken_over"]).lower(),
                str(code["discussed_before"]).lower(), code["body_quality"],
                scrub(" ; ".join(code["process_notes"]), handles), scrub(pull["title"], handles),
            ])
    print(len(coded), "rows ->", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
