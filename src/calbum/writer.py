"""Deterministic JSON writer. See PLAN.md, non-negotiable constraint 1:
sorted object keys, records sorted by album ID, 2-space indent, trailing
newline. Without this, every run emits a giant noise diff and the
git-as-audit-log property is destroyed.

Pydantic's model_dump_json() does NOT sort keys or guarantee this contract —
models must go through model_dump(mode="json") and then this module.

Writes are atomic (temp file + os.replace, decision 10): a killed/crashed run
must never leave a truncated canonical store committed to git history.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from calbum.models import Album


def read_albums(path: Path) -> list[Album]:
    """Read-side counterpart to write_albums. Missing file -> []. A file that
    exists but parses to an empty list is treated as data loss, not a fresh
    start (see PLAN.md constraint 1 / the mass-removal guard's cold-start
    reasoning in poll.py): silently proceeding on a truncated store would
    let every downstream consumer (poll's mass-removal guard, sheets'
    replace-tab) rebuild from nothing without noticing anything was wrong.
    If this is genuinely a fresh start, delete the file first."""
    path = Path(path)
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    if not raw:
        raise SystemExit(
            f"{path} exists but contains zero records. This looks like data "
            "loss, not a fresh start — refusing to proceed. If this is "
            "genuinely a fresh start, delete the file first."
        )
    return [Album.model_validate(rec) for rec in raw]


def dump_albums(albums: list[Album]) -> list[dict]:
    """Serialize albums to plain dicts, sorted by album ID. Pure function —
    no I/O — so it's the piece writer determinism tests exercise directly."""
    return [
        album.model_dump(mode="json")
        for album in sorted(albums, key=lambda a: a.id)
    ]


def write_json_atomic(path: Path, data: object) -> None:
    """Serialize `data` deterministically and write it to `path` atomically.

    Deterministic: sorted keys, 2-space indent, trailing newline.
    Atomic: writes to `path.tmp` in the same directory, then os.replace()
    (atomic on POSIX) — a crash mid-write leaves the previous file intact
    instead of a truncated one.
    """
    path = Path(path)
    text = json.dumps(data, sort_keys=True, indent=2) + "\n"

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)


def write_albums(path: Path, albums: list[Album]) -> None:
    write_json_atomic(path, dump_albums(albums))
