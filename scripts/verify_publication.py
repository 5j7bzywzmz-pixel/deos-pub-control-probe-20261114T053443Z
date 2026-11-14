#!/usr/bin/env python3
"""Fail-closed verification for the disposable publication feasibility probe."""
import hashlib
import json
import os
import re
import subprocess
import sys

SHA = re.compile(r"^[0-9a-f]{40}$")
DEST_REF = "refs/heads/production"
MANIFEST_PATH = "evidence/MANIFEST.json"


def fail(message):
    print(f"REFUSED: {message}", file=sys.stderr)
    raise SystemExit(1)


def git(*args, check=True):
    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        fail(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def git_bytes(*args):
    proc = subprocess.run(["git", *args], capture_output=True)
    if proc.returncode != 0:
        fail(f"git {' '.join(args)} failed: {proc.stderr.decode(errors='replace').strip()}")
    return proc.stdout


def main():
    candidate = os.environ["CANDIDATE"]
    evidence = os.environ["EVIDENCE"]
    expected_old = os.environ["EXPECTED_OLD"]
    destination_ref = os.environ["DESTINATION_REF"]
    repository = os.environ.get("REPOSITORY", "")

    for name, value in (("candidate", candidate), ("evidence", evidence),
                        ("expected_old", expected_old)):
        if not SHA.fullmatch(value):
            fail(f"{name} is not a full 40-hex SHA")

    # Destination is fixed, not caller-selectable.  An input that names any
    # other ref is a destination-substitution attempt.
    if destination_ref != DEST_REF:
        fail(f"destination substitution: {destination_ref!r} != {DEST_REF!r}")

    git("fetch", "--no-tags", "--quiet", "origin", candidate, evidence, destination_ref)

    git("cat-file", "-e", f"{candidate}^{{commit}}")
    git("cat-file", "-e", f"{evidence}^{{commit}}")

    # Exact candidate identity and ancestry.
    candidate_tree = git("rev-parse", f"{candidate}^{{tree}}").stdout.strip()
    parents = git("rev-list", "--parents", "-n", "1", candidate).stdout.split()
    if len(parents) != 2:
        fail("candidate must have exactly one parent")
    expected_parent = parents[1]
    code = git("merge-base", "--is-ancestor", expected_old, candidate, check=False).returncode
    if code != 0:
        fail("candidate is not a fast-forward descendant of expected_old")

    # Evidence is an immutable commit; its manifest must bind this exact
    # candidate, tree, parent and baseline, and every listed file must hash.
    raw_manifest = git_bytes("show", f"{evidence}:{MANIFEST_PATH}")
    try:
        manifest = json.loads(raw_manifest)
    except Exception as exc:
        fail(f"evidence manifest is not JSON: {exc}")
    if manifest.get("candidate") != candidate:
        fail("evidence manifest candidate does not match")
    if manifest.get("candidate_tree") != candidate_tree:
        fail("evidence manifest candidate_tree does not match")
    if manifest.get("expected_parent") != expected_parent:
        fail("evidence manifest expected_parent does not match")
    if manifest.get("expected_old") != expected_old:
        fail("evidence manifest expected_old does not match")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        fail("evidence manifest files must be a non-empty map")
    for path, digest in files.items():
        if not isinstance(path, str) or not path.startswith("evidence/"):
            fail(f"evidence path is not under evidence/: {path!r}")
        if path == MANIFEST_PATH:
            fail("manifest must not list itself")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            fail(f"evidence digest is invalid for {path}")
        actual = hashlib.sha256(git_bytes("show", f"{evidence}:{path}")).hexdigest()
        if actual != digest:
            fail(f"evidence file changed or is altered: {path}")

    # Read the destination immediately before deciding/pushing.
    lines = [line for line in git("ls-remote", "origin", destination_ref).stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        fail("destination ref is not resolvable exactly once")
    sha_part, _, ref_part = lines[0].partition("\t")
    if ref_part != destination_ref or not SHA.fullmatch(sha_part):
        fail("destination ref parse failed")
    remote_head = sha_part
    if remote_head == candidate:
        print("ALREADY_PUBLISHED")
        return
    if remote_head != expected_old:
        fail(f"remote drift: destination is {remote_head}, expected_old is {expected_old}")
    print("VERIFIED_FOR_PUBLICATION")
    print(f"candidate={candidate}")
    print(f"candidate_tree={candidate_tree}")
    print(f"expected_parent={expected_parent}")
    print(f"expected_old={expected_old}")
    print(f"destination_ref={destination_ref}")


if __name__ == "__main__":
    main()
