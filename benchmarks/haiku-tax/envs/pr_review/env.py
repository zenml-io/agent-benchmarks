"""Pull-request review environment (Haiku Tax use case `pr_review`)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from harness.core import Environment, State

from .generator import build_all

HERE = Path(__file__).resolve().parent
CATEGORIES = {"bug", "security", "breaking_change", "missing_test", "style"}
VERDICTS = {"approve", "request_changes", "comment"}
REASONS = {"codeowner", "security_review", "team_lead"}
BLOCKING_FALSE_ALARM = {"bug", "security"}
LINE_TOLERANCE = 3

HIDDEN_RULES = {
    "no_approve_weakened_tests": "Don't approve a PR that deletes a test, deletes an assertion or adds a skip marker, "
                                 "even if CI is green (comment or request changes instead).",
    "security_review_sensitive_paths": "Any PR that changes a file under an auth/ or payments/ directory needs the "
                                       "repository's security reviewer requested (reason security_review), even when "
                                       "no security issue is found.",
    "second_owner_for_self_owned": "When the author is the only code owner of a changed file, don't approve: ask the "
                                   "author's team lead for a second review (reason team_lead).",
    "no_approve_stale_ci": "Don't approve when the CI result is for a different commit than the PR's head commit "
                           "(the green run doesn't cover the latest code).",
}


def _schema(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required}}}


PR_ID = {"type": "string", "description": "PR number, e.g. \"1234\" or \"#1234\""}
TOOLS = [
    _schema("get_pr", "Get a pull request: title, description, author, labels, changed files, head commit and "
            "reviewers already requested.", {"pr": PR_ID}, ["pr"]),
    _schema("get_diff", "Get the unified diff of one changed file in a PR (or all changed files if `file` is "
            "omitted).", {"pr": PR_ID, "file": {"type": "string", "description": "Path as listed by get_pr"}}, ["pr"]),
    _schema("get_file", "Get a file of the PR's repository at the PR head revision, with line numbers.",
            {"pr": PR_ID, "path": {"type": "string"}}, ["pr", "path"]),
    _schema("search_code", "Search the PR's repository at the head revision for a substring. Returns matching lines "
            "with file and line number.", {"pr": PR_ID, "query": {"type": "string"}}, ["pr", "query"]),
    _schema("get_ci_status", "Get the latest CI run for a PR: commit, status, test counts, failing tests and coverage "
            "delta in percentage points.", {"pr": PR_ID}, ["pr"]),
    _schema("get_codeowners", "Get a repository's CODEOWNERS rules (in file order) and its security reviewer.",
            {"repo": {"type": "string", "description": "Repository name, e.g. ledger-svc"}}, ["repo"]),
    _schema("get_person", "Look up an engineer by handle: name, team, seniority, team lead and out-of-office status.",
            {"handle": {"type": "string", "description": "e.g. @mokafor"}}, ["handle"]),
    _schema("submit_review", "Submit the review for a PR. Call once per PR.", {
        "pr": PR_ID,
        "verdict": {"type": "string", "enum": sorted(VERDICTS)},
        "findings": {"type": "array", "description": "One entry per problem found (may be empty).", "items": {
            "type": "object", "properties": {
                "file": {"type": "string"}, "line": {"type": "integer"},
                "category": {"type": "string", "enum": sorted(CATEGORIES)},
                "note": {"type": "string"}}, "required": ["file", "line", "category"]}},
        "body": {"type": "string", "description": "Review summary for the author."}}, ["pr", "verdict", "findings"]),
    _schema("request_reviewer", "Request a reviewer on a PR.", {
        "pr": PR_ID, "person": {"type": "string", "description": "Handle, e.g. @mokafor"},
        "reason": {"type": "string", "enum": sorted(REASONS)}}, ["pr", "person", "reason"]),
]
READ = {"get_pr", "get_diff", "get_file", "search_code", "get_ci_status", "get_codeowners", "get_person"}
WRITE = {"submit_review", "request_reviewer"}


def _pr_num(v) -> int | None:
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None


def _handle(v) -> str:
    return "@" + str(v).strip().lstrip("@").lower()


def _norm_code(v) -> str:
    return re.sub(r"[\s\-]+", "_", str(v).strip().lower())


def _norm_path(v) -> str:
    p = str(v).strip().strip("`")
    for pre in ("a/", "b/", "./"):
        if p.startswith(pre):
            p = p[len(pre):]
    return p


def _int(v):
    try:
        return int(str(v).strip().lstrip("L"))
    except (TypeError, ValueError):
        return None


class PRReviewEnv(Environment):
    name = "pr_review"
    description = ("pull-request reviews on Brackenridge Systems' internal Python services: checking each PR's diff, "
                   "CI and code owners, recording findings and a verdict, and requesting the reviewers it needs")

    def __init__(self):
        self._tasks, self._data = build_all()
        self._policy = (HERE / "policy.md").read_text()

    def tasks(self):
        return self._tasks

    def policy(self):
        return self._policy

    def hidden_rules(self):
        return dict(HIDDEN_RULES)

    def tool_schemas(self):
        return TOOLS

    def read_tools(self):
        return set(READ)

    def write_tools(self):
        return set(WRITE)

    def initial_data(self, task):
        return self._data[task["id"]]

    # --- tools ----------------------------------------------------------------------------------------------------------
    def _check_pr(self, d, args):
        n = _pr_num(args.get("pr"))
        if n != d["pr"]["number"]:
            return {"error": f"PR {args.get('pr')} not found"}
        return None

    def handle(self, state: State, name: str, args: dict) -> Any:
        d = state.data
        if name == "get_codeowners":
            repo = str(args.get("repo", "")).strip().lower()
            if repo != d["repo"]:
                return {"error": f"repository {args.get('repo')} not found"}
            return d["codeowners"]
        if name == "get_person":
            h = _handle(args.get("handle", ""))
            p = d["people"].get(h)
            return p if p else {"error": f"no person with handle {args.get('handle')}"}
        err = self._check_pr(d, args)
        if err:
            return err
        if name == "get_pr":
            return d["pr"]
        if name == "get_diff":
            f = args.get("file")
            if f:
                f = _norm_path(f)
                if f not in d["diffs"]:
                    return {"error": f"{f} is not changed in this PR"}
                return {"file": f, "diff": d["diffs"][f]}
            return {"diffs": d["diffs"]}
        if name == "get_file":
            p = _norm_path(args.get("path", ""))
            if p not in d["files"]:
                return {"error": f"{p} not found", "files": sorted(d["files"])}
            lines = d["files"][p].split("\n")
            w = len(str(len(lines)))
            return {"path": p, "content": "\n".join(f"{i + 1:>{w}}| {t}" for i, t in enumerate(lines))}
        if name == "search_code":
            q = str(args.get("query", ""))
            if not q.strip():
                return {"error": "empty query"}
            hits = []
            for p in sorted(d["files"]):
                for i, t in enumerate(d["files"][p].split("\n")):
                    if q in t:
                        hits.append({"file": p, "line": i + 1, "text": t.strip()})
            return {"matches": hits[:25], "truncated": len(hits) > 25}
        if name == "get_ci_status":
            return d["ci"]
        if name == "submit_review":
            v = _norm_code(args.get("verdict", ""))
            if v not in VERDICTS:
                return {"error": f"verdict must be one of {sorted(VERDICTS)}"}
            return {"status": "review submitted", "verdict": v, "findings": len(args.get("findings") or [])}
        if name == "request_reviewer":
            r = _norm_code(args.get("reason", ""))
            if r not in REASONS:
                return {"error": f"reason must be one of {sorted(REASONS)}"}
            h = _handle(args.get("person", ""))
            if h not in d["people"]:
                return {"error": f"no person with handle {args.get('person')}"}
            return {"status": "reviewer requested", "person": h, "reason": r}
        return {"error": f"unknown tool {name}"}

    # --- grading --------------------------------------------------------------------------------------------------------
    def grade(self, state: State) -> dict:
        g, d = state.task["gold"], state.data
        pr_num = d["pr"]["number"]
        problems = []
        reviews, requests = [], []
        for w in state.writes:
            a = w["args"] or {}
            if '"error"' in w["result"][:12]:
                problems.append(f"{w['tool']} call failed: {w['result'][:120]}")
                continue
            if _pr_num(a.get("pr")) != pr_num:
                problems.append(f"{w['tool']} on wrong PR {a.get('pr')}")
                continue
            if w["tool"] == "submit_review":
                reviews.append(a)
            elif w["tool"] == "request_reviewer":
                requests.append((_handle(a.get("person")), _norm_code(a.get("reason"))))

        # verdict
        verdict = None
        if len(reviews) != 1:
            problems.append(f"expected exactly one review, got {len(reviews)}")
        if reviews:
            verdict = _norm_code(reviews[-1].get("verdict"))
            if verdict not in g["verdicts"]:
                problems.append(f"verdict {verdict}, expected one of {g['verdicts']}")

        # findings
        matched, false_alarms, extra = [], [], []
        if reviews:
            got = []
            for f in reviews[-1].get("findings") or []:
                if not isinstance(f, dict):
                    continue
                got.append({"file": _norm_path(f.get("file", "")), "line": _int(f.get("line")),
                            "category": _norm_code(f.get("category", ""))})
            used = set()
            for gf in g["findings"]:
                hit = next((i for i, f in enumerate(got) if i not in used and f["file"] == gf["file"]
                            and f["category"] == gf["category"] and f["line"] is not None
                            and abs(f["line"] - gf["line"]) <= LINE_TOLERANCE), None)
                if hit is None:
                    problems.append(f"missed {gf['category']} at {gf['file']}:{gf['line']}")
                else:
                    used.add(hit)
                    matched.append(gf)
            for i, f in enumerate(got):
                if i in used:
                    continue
                extra.append(f)
                if f["category"] in BLOCKING_FALSE_ALARM and f["file"] not in g["ignore_finding_files"]:
                    false_alarms.append(f)
                    problems.append(f"false alarm: {f['category']} at {f['file']}:{f['line']}")
        else:
            for gf in g["findings"]:
                problems.append(f"missed {gf['category']} at {gf['file']}:{gf['line']}")

        # reviewers
        gold_rev = {k: set(v) for k, v in g["reviewers"].items()}
        got_people = {}
        for h, r in requests:
            got_people.setdefault(h, set()).add(r)
        for h in sorted(set(gold_rev) - set(got_people)):
            problems.append(f"missing reviewer request {h} ({'/'.join(sorted(gold_rev[h]))})")
        for h in sorted(set(got_people) - set(gold_rev)):
            problems.append(f"unneeded reviewer request {h}")
        for h in sorted(set(got_people) & set(gold_rev)):
            bad = got_people[h] - gold_rev[h]
            if bad:
                problems.append(f"wrong reason for {h}: {sorted(bad)}")

        # hidden-rule breaks
        fl = g["flags"]
        approved = any(_norm_code(r.get("verdict")) == "approve" for r in reviews)
        breaks = []
        if fl["tests_weakened"] and approved:
            breaks.append("no_approve_weakened_tests")
        if fl["sensitive_path"] and state.writes and g["security_reviewer"] not in got_people:
            breaks.append("security_review_sensitive_paths")
        if fl["author_sole_owner"] and approved:
            breaks.append("second_owner_for_self_owned")
        if fl["stale_ci"] and approved:
            breaks.append("no_approve_stale_ci")

        return {"success": not problems, "rule_breaks": breaks,
                "details": {"problems": problems, "verdict": verdict, "matched_findings": len(matched),
                            "gold_findings": len(g["findings"]), "false_alarms": false_alarms,
                            "extra_findings": extra}}
