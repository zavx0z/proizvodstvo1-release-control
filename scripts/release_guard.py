#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request
from typing import Callable

REPOSITORY = "zavx0z/proizvodstvo1-release-control"
OWNER = "zavx0z"
MANIFEST_PATH = "release/staging.json"
SOURCE_REPOSITORY = "zavx0z/proizvodstvo1"
SOURCE_REF = "refs/heads/ai-dev"

MAINTENANCE_PATHS = {
    "README.md",
    "AGENTS.md",
    ".github/CODEOWNERS",
    ".github/pull_request_template.md",
    ".github/workflows/bootstrap-check.yml",
    ".github/workflows/release-manifest-guard.yml",
    ".github/workflows/publish-staging.yml",
    ".github/workflows/ghcr-cleanup.yml",
    "docs/RELEASE_CONTRACT.md",
    "docs/RETENTION_AND_CLEANUP.md",
    "docs/CURRENT_STATE.md",
    "docs/SECURITY.md",
    "scripts/release_guard.py",
    "scripts/ghcr_cleanup.py",
    "scripts/publish_preflight.py",
    "ops/README.md",
    "ops/p1-react-staging-deploy.sh",
}

CRITICAL_PATHS = {
    "README.md",
    "AGENTS.md",
    ".github/CODEOWNERS",
    ".github/workflows/release-manifest-guard.yml",
    "docs/RELEASE_CONTRACT.md",
    "docs/RETENTION_AND_CLEANUP.md",
    "scripts/release_guard.py",
}

SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
)


class GuardError(RuntimeError):
    pass


def reject(message: str) -> None:
    raise GuardError(message)


def validate_text_safety(path: str, text: str) -> None:
    if len(text.encode("utf-8")) > 131072:
        reject(f"file too large: {path}")
    if "\x00" in text:
        reject(f"binary content rejected: {path}")
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            reject(f"possible secret material rejected in {path}")


def validate_manifest(text: str) -> dict:
    validate_text_safety(MANIFEST_PATH, text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        reject(f"manifest is not valid JSON: {error}")

    keys = {
        "schema",
        "environment",
        "source_repository",
        "source_ref",
        "source_sha",
        "sequence",
        "requested_at",
        "summary",
    }
    if not isinstance(value, dict) or set(value) != keys:
        reject("manifest keys do not match the exact schema")
    if type(value["schema"]) is not int or value["schema"] != 1:
        reject("manifest schema must be integer 1")
    if value["environment"] != "staging":
        reject("manifest environment must be staging")
    if value["source_repository"] != SOURCE_REPOSITORY:
        reject("manifest source_repository is fixed")
    if value["source_ref"] != SOURCE_REF:
        reject("manifest source_ref is fixed")
    if not isinstance(value["source_sha"], str) or not re.fullmatch(
        r"[0-9a-f]{40}", value["source_sha"]
    ):
        reject("manifest source_sha must be 40 lowercase hex")
    if type(value["sequence"]) is not int or value["sequence"] < 1:
        reject("manifest sequence must be a positive integer")

    stamp = value["requested_at"]
    if not isinstance(stamp, str) or not stamp.endswith("Z"):
        reject("manifest requested_at must be RFC3339 UTC ending in Z")
    try:
        parsed = dt.datetime.fromisoformat(stamp[:-1] + "+00:00")
    except ValueError as error:
        reject(f"manifest requested_at is invalid: {error}")
    if parsed.utcoffset() != dt.timedelta(0):
        reject("manifest requested_at must be UTC")

    summary = value["summary"]
    if not isinstance(summary, str) or not 1 <= len(summary) <= 160:
        reject("manifest summary length must be 1..160")
    if "\n" in summary or "\r" in summary or not summary.isprintable():
        reject("manifest summary must be one printable line")
    return value


def validate_pr(
    pr: dict,
    changed: dict[str, dict],
    fetch_text: Callable[[str, str], str],
) -> str:
    head = pr["head"]
    base = pr["base"]
    head_ref = head["ref"]
    head_sha = head["sha"]
    head_repo = (head.get("repo") or {}).get("full_name")
    base_sha = base["sha"]
    author = pr["user"]["login"]

    if head_repo != REPOSITORY:
        reject("release-control PRs must originate from this repository, not a fork")
    if not changed:
        reject("empty PR is not a release-control change")
    if len(changed) > 20:
        reject("release-control PR changes too many files")

    release_match = re.fullmatch(r"release/staging-seq-([1-9][0-9]*)", head_ref)
    if release_match:
        if set(changed) != {MANIFEST_PATH}:
            reject("release PR must change exactly release/staging.json")
        if changed[MANIFEST_PATH]["status"] != "modified":
            reject("release/staging.json must be modified, not added/deleted/renamed")

        base_manifest = validate_manifest(fetch_text(MANIFEST_PATH, base_sha))
        head_manifest = validate_manifest(fetch_text(MANIFEST_PATH, head_sha))
        expected_sequence = base_manifest["sequence"] + 1
        branch_sequence = int(release_match.group(1))
        if head_manifest["sequence"] != expected_sequence:
            reject(f"sequence must increment by exactly one to {expected_sequence}")
        if branch_sequence != head_manifest["sequence"]:
            reject("branch sequence does not match manifest sequence")
        return (
            "P1_RELEASE_MANIFEST_VALID "
            f"sequence={head_manifest['sequence']} source_sha={head_manifest['source_sha']}"
        )

    if head_ref.startswith("maintenance/"):
        if author != OWNER:
            reject("maintenance PR must be authored by repository owner")
        if MANIFEST_PATH in changed:
            reject("maintenance PR must not change the release manifest")

        unexpected = sorted(set(changed) - MAINTENANCE_PATHS)
        if unexpected:
            reject(f"maintenance PR contains unexpected paths: {unexpected}")
        if len(changed) > 12:
            reject("maintenance PR changes too many files")

        removed_critical = sorted(
            path
            for path, item in changed.items()
            if path in CRITICAL_PATHS and item["status"] == "removed"
        )
        if removed_critical:
            reject(f"critical release-control files cannot be deleted: {removed_critical}")

        for path, item in changed.items():
            if item["status"] == "removed":
                continue
            validate_text_safety(path, fetch_text(path, head_sha))
        return f"P1_RELEASE_MAINTENANCE_VALID files={len(changed)}"

    reject("branch must be release/staging-seq-<N> or owner-only maintenance/<slug>")


class GitHubAPI:
    def __init__(self, repository: str, token: str):
        self.repository = repository
        self.token = token

    def json(self, path: str):
        request = urllib.request.Request(
            "https://api.github.com" + path,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + self.token,
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "proizvodstvo1-release-control-guard",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def changed_files(self, number: int) -> dict[str, dict]:
        files = self.json(
            f"/repos/{self.repository}/pulls/{number}/files?per_page=100&page=1"
        )
        if len(files) >= 100:
            reject("PR is too large for release-control")
        return {item["filename"]: item for item in files}

    def fetch_text(self, path: str, ref: str) -> str:
        encoded_path = urllib.parse.quote(path, safe="/")
        encoded_ref = urllib.parse.quote(ref, safe="")
        data = self.json(
            f"/repos/{self.repository}/contents/{encoded_path}?ref={encoded_ref}"
        )
        if data.get("type") != "file" or data.get("encoding") != "base64":
            reject(f"expected regular file content for {path}")
        raw = base64.b64decode(data["content"], validate=True)
        if len(raw) > 131072 or b"\x00" in raw:
            reject(f"non-text or oversized file rejected: {path}")
        return raw.decode("utf-8")


def run_live(event_path: str) -> None:
    if os.environ.get("GH_REPOSITORY") != REPOSITORY:
        reject("unexpected repository")
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        reject("GH_TOKEN is required")
    event = json.loads(pathlib.Path(event_path).read_text("utf-8"))
    pr = event["pull_request"]
    api = GitHubAPI(REPOSITORY, token)
    result = validate_pr(pr, api.changed_files(pr["number"]), api.fetch_text)
    print(result)


def manifest(sequence: int, source_sha: str = "a" * 40) -> str:
    return json.dumps(
        {
            "schema": 1,
            "environment": "staging",
            "source_repository": SOURCE_REPOSITORY,
            "source_ref": SOURCE_REF,
            "source_sha": source_sha,
            "sequence": sequence,
            "requested_at": "2026-08-30T00:00:00Z",
            "summary": "self-test",
        }
    )


def expect_error(callable_, contains: str) -> None:
    try:
        callable_()
    except GuardError as error:
        if contains not in str(error):
            raise AssertionError(f"expected {contains!r}, got {error!r}") from error
        return
    raise AssertionError(f"expected GuardError containing {contains!r}")


def run_self_test() -> None:
    base_sha = "b" * 40
    head_sha = "c" * 40
    texts = {
        (MANIFEST_PATH, base_sha): manifest(1),
        (MANIFEST_PATH, head_sha): manifest(2),
        ("README.md", head_sha): "safe maintenance text\n",
        ("docs/SECURITY.md", head_sha): "safe security text\n",
    }

    def fetch(path: str, ref: str) -> str:
        return texts[(path, ref)]

    release_pr = {
        "head": {
            "ref": "release/staging-seq-2",
            "sha": head_sha,
            "repo": {"full_name": REPOSITORY},
        },
        "base": {"sha": base_sha},
        "user": {"login": OWNER},
    }
    result = validate_pr(
        release_pr,
        {MANIFEST_PATH: {"status": "modified"}},
        fetch,
    )
    assert result.startswith("P1_RELEASE_MANIFEST_VALID sequence=2")

    expect_error(
        lambda: validate_pr(
            release_pr,
            {
                MANIFEST_PATH: {"status": "modified"},
                "README.md": {"status": "modified"},
            },
            fetch,
        ),
        "exactly release/staging.json",
    )

    maintenance_pr = {
        "head": {
            "ref": "maintenance/docs",
            "sha": head_sha,
            "repo": {"full_name": REPOSITORY},
        },
        "base": {"sha": base_sha},
        "user": {"login": OWNER},
    }
    assert validate_pr(
        maintenance_pr,
        {"README.md": {"status": "modified"}},
        fetch,
    ) == "P1_RELEASE_MAINTENANCE_VALID files=1"

    expect_error(
        lambda: validate_pr(
            maintenance_pr,
            {MANIFEST_PATH: {"status": "modified"}},
            fetch,
        ),
        "must not change the release manifest",
    )

    fork_pr = json.loads(json.dumps(maintenance_pr))
    fork_pr["head"]["repo"]["full_name"] = "other/fork"
    expect_error(
        lambda: validate_pr(
            fork_pr,
            {"README.md": {"status": "modified"}},
            fetch,
        ),
        "not a fork",
    )

    texts[("README.md", head_sha)] = "github_pat_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456\n"
    expect_error(
        lambda: validate_pr(
            maintenance_pr,
            {"README.md": {"status": "modified"}},
            fetch,
        ),
        "possible secret material",
    )

    print("P1_RELEASE_GUARD_SELF_TEST_VALID")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            run_self_test()
        elif args.event:
            run_live(args.event)
        else:
            parser.error("use --self-test or --event")
    except (GuardError, UnicodeDecodeError, KeyError, ValueError) as error:
        print(f"release guard failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
