"""Versioned local data releases and an SQLite review audit trail."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from uuid import uuid4

from routing_files import load_routing_files, read_local_files

MANIFEST = "manifest.json"
AUDIT_COLUMNS = """
    CREATE TABLE IF NOT EXISTS rule_reviews (
        review_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        dataset_revision TEXT NOT NULL,
        region TEXT NOT NULL,
        change_reference TEXT NOT NULL,
        comment TEXT NOT NULL,
        proposal_json TEXT NOT NULL,
        outcome TEXT NOT NULL CHECK (outcome IN ('Blocked', 'Preview only')),
        evidence_json TEXT NOT NULL
    )
"""


def manifest_for(routes, copies):
    return {
        "fininrout_sha256": sha256(routes).hexdigest(),
        "artrules_sha256": sha256(copies).hexdigest() if copies is not None else None,
    }


def dataset_revision(manifest):
    return sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def load_release(directory):
    # Resolve the active symlink once. Both files come from the same release.
    release = Path(directory).expanduser().resolve(strict=True)
    with (release / MANIFEST).open("rb") as source:
        data = source.read(4097)
    if len(data) > 4096:
        raise ValueError("Release manifest exceeds its size limit.")
    expected = json.loads(data)
    routes, copies = read_local_files(release)
    manifest = manifest_for(routes, copies)
    if expected != manifest:
        raise ValueError("Release file checksums do not match the manifest.")
    dataset = load_routing_files(routes, copies)
    if not dataset.rules:
        raise ValueError("A production release must contain at least one FININROUT rule.")
    return dataset, dataset_revision(manifest)


def publish_release(source, root):
    """Validate a staged pair and switch the active release with one rename."""
    root = Path(root).expanduser().resolve()
    routes, copies = read_local_files(source)
    dataset = load_routing_files(routes, copies)
    if not dataset.rules:
        raise ValueError("A production release must contain at least one FININROUT rule.")
    releases = root / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    manifest = manifest_for(routes, copies)
    revision = dataset_revision(manifest)
    release = releases / revision
    if not release.exists():
        with tempfile.TemporaryDirectory(prefix=".stage-", dir=releases) as stage:
            staged = Path(stage) / "release"
            staged.mkdir(mode=0o750)
            (staged / "fininrout.csv").write_bytes(routes)
            if copies is not None:
                (staged / "artrules.csv").write_bytes(copies)
            (staged / MANIFEST).write_text(json.dumps(manifest) + "\n", encoding="utf-8")
            try:
                staged.rename(release)
            except OSError:
                if not release.is_dir():
                    raise
    _, verified_revision = load_release(release)
    if verified_revision != revision:
        raise ValueError("Existing release contents do not match the requested revision.")
    temp_link = root / f".current-{uuid4().hex}"
    try:
        temp_link.symlink_to(Path("releases") / revision, target_is_directory=True)
        temp_link.replace(root / "current")
    finally:
        temp_link.unlink(missing_ok=True)
    return revision


def open_audit(path):
    return sqlite3.connect(path, timeout=5)


def init_audit(path):
    if not path.is_absolute():
        raise ValueError("ROUTING_AUDIT_DB must be an absolute file path.")
    if not path.parent.is_dir():
        raise ValueError("The audit database parent directory must exist.")
    with closing(open_audit(path)) as connection, connection:
        connection.execute(AUDIT_COLUMNS)
        # Probe the write lock even when the schema already exists.
        connection.execute("BEGIN IMMEDIATE")


def log_review(path, revision, change_reference, comment, proposal, result):
    reference = change_reference.strip()
    comment = comment.strip()
    if not (1 <= len(reference) <= 80 and 1 <= len(comment) <= 500):
        raise ValueError("Enter a change reference and a review comment before submitting.")
    review_id = uuid4().hex
    evidence = [{"type": item["type"], "line": item["line"], "requested_mt": item["requested_mt"]}
                for item in result.get("findings", ())]
    if result["status"] == "Preview only":
        evidence = result["draft_rules"]
    with closing(open_audit(path)) as connection, connection:
        connection.execute(
            """INSERT INTO rule_reviews (
                   review_id, created_at, dataset_revision, region, change_reference, comment,
                   proposal_json, outcome, evidence_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (review_id, datetime.now(timezone.utc).isoformat(timespec="seconds"), revision,
             proposal["region"], reference, comment, json.dumps(proposal),
             result["status"], json.dumps(evidence)),
        )
    return review_id


def production_paths():
    data = os.environ.get("ROUTING_DATA_DIR")
    audit = os.environ.get("ROUTING_AUDIT_DB")
    if not data or not audit:
        raise ValueError("Set ROUTING_DATA_DIR and ROUTING_AUDIT_DB for production mode.")
    return Path(data).expanduser(), Path(audit).expanduser()


def check_production():
    data, audit = production_paths()
    dataset, revision = load_release(data)
    init_audit(audit)
    return dataset, revision, audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    publish = commands.add_parser("publish", help="Validate and activate a local CSV release.")
    publish.add_argument("source")
    publish.add_argument("root")
    commands.add_parser("check", help="Check dataset and audit database readiness.")
    args = parser.parse_args()
    try:
        if args.command == "publish":
            print(publish_release(args.source, args.root))
        else:
            dataset, revision, _ = check_production()
            print(f"Ready: {len(dataset.rules)} rules, revision {revision}")
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
