#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

OWNER = "zavx0z"
PACKAGE = "proizvodstvo1-react-portal"
API_ROOT = "https://api.github.com"
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
SEQ_TAG_RE = re.compile(r"(?:deployed-)?seq-([1-9][0-9]*)")
SOURCE_TAG_RE = re.compile(r"sha-[0-9a-f]{40}")
BOOTSTRAP_TAG_RE = re.compile(r"bootstrap-sha-[0-9a-f]{40}")
ALLOWED_TAG_RE = re.compile(
    rf"(?:{SEQ_TAG_RE.pattern}|{SOURCE_TAG_RE.pattern}|{BOOTSTRAP_TAG_RE.pattern})"
)


class CleanupError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise CleanupError(message)


def parse_time(value: str) -> dt.datetime:
    if not isinstance(value, str):
        fail("package version timestamp is not a string")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        fail(f"invalid package version timestamp {value!r}: {error}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


@dataclass(frozen=True)
class Version:
    version_id: int
    digest: str
    created_at: dt.datetime
    tags: tuple[str, ...]

    @property
    def deployed_sequences(self) -> tuple[int, ...]:
        result: list[int] = []
        for tag in self.tags:
            match = re.fullmatch(r"deployed-seq-([1-9][0-9]*)", tag)
            if match:
                result.append(int(match.group(1)))
        return tuple(sorted(result))


def parse_version(raw: dict) -> Version:
    try:
        version_id = int(raw["id"])
        digest = str(raw["name"])
        created_at = parse_time(raw["created_at"])
        metadata = raw["metadata"]
        container = metadata["container"]
        tags_raw = container.get("tags", [])
    except (KeyError, TypeError, ValueError) as error:
        fail(f"unexpected GHCR package version shape: {error}")

    if not DIGEST_RE.fullmatch(digest):
        fail(f"unexpected GHCR version digest: {digest!r}")
    if not isinstance(tags_raw, list) or not all(isinstance(item, str) for item in tags_raw):
        fail(f"unexpected GHCR tags for version {version_id}")
    tags = tuple(sorted(set(tags_raw)))
    unknown = [tag for tag in tags if not ALLOWED_TAG_RE.fullmatch(tag)]
    if unknown:
        fail(f"unknown tags on GHCR version {version_id}: {unknown}")
    return Version(version_id, digest, created_at, tags)


class GitHubPackagesAPI:
    def __init__(self, token: str):
        if not token:
            fail("GH_TOKEN is required")
        self.token = token

    def request(self, method: str, path: str):
        request = urllib.request.Request(
            API_ROOT + path,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + self.token,
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "proizvodstvo1-ghcr-cleanup",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status == 204:
                    return None
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise FileNotFoundError(path) from error
            detail = error.read().decode("utf-8", "replace")[:500]
            fail(f"GitHub Packages API {method} {path} failed: HTTP {error.code}: {detail}")

    def list_versions(self) -> list[Version]:
        versions: list[Version] = []
        for page in range(1, 101):
            path = (
                f"/users/{OWNER}/packages/container/{PACKAGE}/versions"
                f"?per_page=100&page={page}"
            )
            try:
                raw = self.request("GET", path)
            except FileNotFoundError:
                if page == 1:
                    return []
                break
            if not isinstance(raw, list):
                fail("GHCR versions response is not a list")
            versions.extend(parse_version(item) for item in raw)
            if len(raw) < 100:
                break
        else:
            fail("GHCR version inventory exceeded pagination safety bound")
        return versions

    def delete_version(self, version_id: int) -> None:
        path = f"/users/{OWNER}/packages/container/{PACKAGE}/versions/{version_id}"
        self.request("DELETE", path)


def read_protected_digests(path: str | None) -> set[str]:
    if not path:
        return set()
    file = pathlib.Path(path)
    if not file.exists():
        fail(f"protected digest file does not exist: {path}")
    result: set[str] = set()
    for line in file.read_text("utf-8").splitlines():
        value = line.strip()
        if not value:
            continue
        if "@" in value:
            value = value.rsplit("@", 1)[1]
        if not DIGEST_RE.fullmatch(value):
            fail(f"invalid protected digest: {value!r}")
        result.add(value)
    return result


@dataclass
class Plan:
    keep_ids: set[int]
    delete: list[Version]
    protected_reasons: dict[int, list[str]]


def build_plan(
    versions: list[Version],
    protected_digests: set[str],
    now: dt.datetime,
    keep_deployed: int,
    grace_hours: int,
) -> Plan:
    if keep_deployed < 1:
        fail("keep_deployed must be >= 1")
    if grace_hours < 1:
        fail("grace_hours must be >= 1")

    reasons: dict[int, list[str]] = {item.version_id: [] for item in versions}

    deployed_ranked = sorted(
        (
            (max(item.deployed_sequences), item)
            for item in versions
            if item.deployed_sequences
        ),
        key=lambda pair: (pair[0], pair[1].created_at, pair[1].version_id),
        reverse=True,
    )
    for _, item in deployed_ranked[:keep_deployed]:
        reasons[item.version_id].append("recent-successful-deployment")

    grace = dt.timedelta(hours=grace_hours)
    for item in versions:
        age = now - item.created_at
        if age < dt.timedelta(0):
            fail(f"GHCR version {item.version_id} has a future created_at")
        if age <= grace:
            reasons[item.version_id].append("grace-window")
        if item.digest in protected_digests:
            reasons[item.version_id].append("vps-state")

    keep_ids = {version_id for version_id, why in reasons.items() if why}
    delete = [item for item in versions if item.version_id not in keep_ids]
    delete.sort(key=lambda item: (item.created_at, item.version_id))
    return Plan(keep_ids=keep_ids, delete=delete, protected_reasons=reasons)


def evidence(plan: Plan, versions: list[Version], prefix: str = "") -> None:
    print(f"{prefix}GHCR_VERSIONS_TOTAL={len(versions)}")
    print(f"{prefix}GHCR_VERSIONS_RETAINED={len(plan.keep_ids)}")
    print(f"{prefix}GHCR_DELETE_CANDIDATES={len(plan.delete)}")
    if plan.delete:
        print(
            f"{prefix}GHCR_DELETE_IDS="
            + ",".join(str(item.version_id) for item in plan.delete)
        )
    retained_digests = [
        item.digest for item in versions if item.version_id in plan.keep_ids
    ]
    print(f"{prefix}GHCR_RETAINED_DIGESTS=" + ",".join(retained_digests))


def run(
    apply: bool,
    protected_file: str | None,
    keep_deployed: int,
    grace_hours: int,
    max_delete: int,
) -> int:
    if max_delete < 1 or max_delete > 50:
        fail("max_delete must be between 1 and 50")
    token = os.environ.get("GH_TOKEN", "")
    api = GitHubPackagesAPI(token)
    versions = api.list_versions()
    if not versions:
        print("GHCR_CLEANUP_STATUS=OK")
        print("GHCR_PACKAGE_STATE=ABSENT_OR_EMPTY")
        return 0

    protected = read_protected_digests(protected_file)
    now = dt.datetime.now(dt.timezone.utc)
    plan = build_plan(versions, protected, now, keep_deployed, grace_hours)
    evidence(plan, versions)

    if not apply:
        print("GHCR_CLEANUP_STATUS=PLAN_ONLY")
        return 0

    batch = plan.delete[:max_delete]
    for item in batch:
        api.delete_version(item.version_id)
        print(f"GHCR_DELETED_VERSION_ID={item.version_id}")
        print(f"GHCR_DELETED_DIGEST={item.digest}")

    remaining = len(plan.delete) - len(batch)
    if remaining:
        print(f"GHCR_REMAINING_DELETE_CANDIDATES={remaining}")
        print("GHCR_CLEANUP_STATUS=CLEANUP_BLOCKED")
        return 2

    print("GHCR_CLEANUP_STATUS=OK")
    return 0


def self_test() -> None:
    now = dt.datetime(2026, 8, 30, 12, 0, tzinfo=dt.timezone.utc)

    def version(version_id: int, seq: int | None, hours_old: int, digest_char: str) -> Version:
        tags: list[str] = [f"sha-{'a' * 40}", f"seq-{version_id}"]
        if seq is not None:
            tags.append(f"deployed-seq-{seq}")
        return Version(
            version_id=version_id,
            digest="sha256:" + digest_char * 64,
            created_at=now - dt.timedelta(hours=hours_old),
            tags=tuple(tags),
        )

    versions = [
        version(1, 1, 240, "1"),
        version(2, 2, 200, "2"),
        version(3, 3, 160, "3"),
        version(4, 4, 120, "4"),
        version(5, 5, 80, "5"),
        version(6, 6, 60, "6"),
        version(7, None, 60, "7"),
        version(8, None, 12, "8"),
    ]
    protected = {versions[0].digest}
    plan = build_plan(versions, protected, now, keep_deployed=5, grace_hours=48)
    kept = {item.version_id for item in versions if item.version_id in plan.keep_ids}
    assert kept == {1, 2, 3, 4, 5, 6, 8}
    assert [item.version_id for item in plan.delete] == [7]

    bootstrap = parse_version(
        {
            "id": 98,
            "name": "sha256:" + "8" * 64,
            "created_at": "2026-08-30T00:00:00Z",
            "metadata": {
                "container": {
                    "tags": [
                        "bootstrap-sha-" + "b" * 40,
                        "sha-" + "b" * 40,
                    ]
                }
            },
        }
    )
    assert bootstrap.tags == (
        "bootstrap-sha-" + "b" * 40,
        "sha-" + "b" * 40,
    )

    for invalid_bootstrap_tag in (
        "bootstrap-sha-" + "B" * 40,
        "bootstrap-sha-" + "b" * 39,
        "bootstrap-sha-" + "b" * 41,
    ):
        try:
            parse_version(
                {
                    "id": 97,
                    "name": "sha256:" + "7" * 64,
                    "created_at": "2026-08-30T00:00:00Z",
                    "metadata": {"container": {"tags": [invalid_bootstrap_tag]}},
                }
            )
        except CleanupError as error:
            assert "unknown tags" in str(error)
        else:
            raise AssertionError("inexact bootstrap GHCR tag was accepted")

    try:
        parse_version(
            {
                "id": 99,
                "name": "sha256:" + "9" * 64,
                "created_at": "2026-08-01T00:00:00Z",
                "metadata": {"container": {"tags": ["mystery-tag"]}},
            }
        )
    except CleanupError as error:
        assert "unknown tags" in str(error)
    else:
        raise AssertionError("unknown GHCR tag was accepted")

    print("P1_GHCR_CLEANUP_SELF_TEST_VALID")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--protected-file")
    parser.add_argument("--keep-deployed", type=int, default=5)
    parser.add_argument("--grace-hours", type=int, default=48)
    parser.add_argument("--max-delete", type=int, default=50)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            return 0
        return run(
            apply=args.apply,
            protected_file=args.protected_file,
            keep_deployed=args.keep_deployed,
            grace_hours=args.grace_hours,
            max_delete=args.max_delete,
        )
    except (CleanupError, AssertionError, OSError, UnicodeError) as error:
        print(f"GHCR cleanup failed: {error}", file=sys.stderr)
        print("GHCR_CLEANUP_STATUS=CLEANUP_BLOCKED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
