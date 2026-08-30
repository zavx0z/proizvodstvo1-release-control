#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys

MANIFEST_PATH = pathlib.Path("release/staging.json")
SOURCE_REPOSITORY = "zavx0z/proizvodstvo1"
SOURCE_REF = "refs/heads/ai-dev"
IMAGE_REPOSITORY = "ghcr.io/zavx0z/proizvodstvo1-react-portal"
SHA_RE = re.compile(r"[0-9a-f]{40}")


class PreflightError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise PreflightError(message)


def validate_manifest(path: pathlib.Path) -> dict:
    try:
        raw = path.read_text("utf-8")
    except OSError as error:
        fail(f"cannot read manifest: {error}")

    if len(raw.encode("utf-8")) > 65536:
        fail("manifest is unexpectedly large")
    if "\x00" in raw:
        fail("manifest contains NUL")

    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        fail(f"manifest is not valid JSON: {error}")

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
        fail("manifest keys do not match schema")
    if type(value["schema"]) is not int or value["schema"] != 1:
        fail("schema must be integer 1")
    if value["environment"] != "staging":
        fail("environment must be staging")
    if value["source_repository"] != SOURCE_REPOSITORY:
        fail("source_repository is fixed")
    if value["source_ref"] != SOURCE_REF:
        fail("source_ref is fixed")
    if not isinstance(value["source_sha"], str) or not SHA_RE.fullmatch(value["source_sha"]):
        fail("source_sha must be 40 lowercase hex")
    if type(value["sequence"]) is not int or value["sequence"] < 1:
        fail("sequence must be a positive integer")

    requested_at = value["requested_at"]
    if not isinstance(requested_at, str) or not requested_at.endswith("Z"):
        fail("requested_at must be UTC RFC3339 ending in Z")
    try:
        parsed = dt.datetime.fromisoformat(requested_at[:-1] + "+00:00")
    except ValueError as error:
        fail(f"requested_at is invalid: {error}")
    if parsed.utcoffset() != dt.timedelta(0):
        fail("requested_at must be UTC")

    summary = value["summary"]
    if not isinstance(summary, str) or not 1 <= len(summary) <= 160:
        fail("summary length must be 1..160")
    if "\n" in summary or "\r" in summary or not summary.isprintable():
        fail("summary must be one printable line")

    return value


def git(source_dir: pathlib.Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(source_dir), *args],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except subprocess.CalledProcessError as error:
        fail(f"git {' '.join(args)} failed: {error.output.strip()}")


def validate_source(source_dir: pathlib.Path, manifest: dict) -> None:
    if not source_dir.is_dir() or not (source_dir / ".git").exists():
        fail("private source checkout is missing")

    actual_sha = git(source_dir, "rev-parse", "HEAD")
    if actual_sha != manifest["source_sha"]:
        fail(
            "manifest source_sha does not match checked out ai-dev HEAD: "
            f"manifest={manifest['source_sha']} checkout={actual_sha}"
        )

    if git(source_dir, "status", "--porcelain"):
        fail("private source checkout must be clean")

    required = [
        "package.json",
        "bun.lock",
        "app/ai/package.json",
        "app/ai/Dockerfile.release",
        "app/ai/Dockerfile.release.dockerignore",
        "pkg/institute",
    ]
    missing = [item for item in required if not (source_dir / item).exists()]
    if missing:
        fail(f"source checkout is missing release contract paths: {missing}")


def append_output(path: str | None, key: str, value: str) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{key}={value}\n")


def run(manifest_path: pathlib.Path, source_dir: pathlib.Path | None, output: str | None) -> None:
    manifest = validate_manifest(manifest_path)
    if source_dir is not None:
        validate_source(source_dir, manifest)

    sequence = str(manifest["sequence"])
    source_sha = manifest["source_sha"]
    values = {
        "sequence": sequence,
        "source_sha": source_sha,
        "image_repository": IMAGE_REPOSITORY,
        "candidate_tag": f"seq-{sequence}",
        "source_tag": f"sha-{source_sha}",
        "deployed_tag": f"deployed-seq-{sequence}",
    }
    for key, value in values.items():
        append_output(output, key, value)
    print(
        "P1_PUBLISH_PREFLIGHT_VALID "
        f"sequence={sequence} source_sha={source_sha} source_checked={source_dir is not None}"
    )


def self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "staging.json"
        path.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "environment": "staging",
                    "source_repository": SOURCE_REPOSITORY,
                    "source_ref": SOURCE_REF,
                    "source_sha": "a" * 40,
                    "sequence": 2,
                    "requested_at": "2026-08-30T00:00:00Z",
                    "summary": "self-test",
                }
            ),
            "utf-8",
        )
        value = validate_manifest(path)
        assert value["sequence"] == 2

        bad = json.loads(path.read_text("utf-8"))
        bad["source_sha"] = "BAD"
        path.write_text(json.dumps(bad), "utf-8")
        try:
            validate_manifest(path)
        except PreflightError as error:
            assert "source_sha" in str(error)
        else:
            raise AssertionError("invalid source_sha was accepted")

    print("P1_PUBLISH_PREFLIGHT_SELF_TEST_VALID")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(MANIFEST_PATH))
    parser.add_argument("--source-dir")
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            run(
                pathlib.Path(args.manifest),
                pathlib.Path(args.source_dir) if args.source_dir else None,
                args.github_output,
            )
    except (PreflightError, AssertionError, OSError, UnicodeError) as error:
        print(f"publish preflight failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
