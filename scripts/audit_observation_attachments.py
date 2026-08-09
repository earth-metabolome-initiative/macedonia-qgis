from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

PICTURE_FIELDS = (
    "picture_environment",
    "picture_full_organism",
    "picture_detail",
    "picture_sampled_part",
    "picture_sample_code",
    "picture_free",
)
REQUIRED_PICTURE_FIELDS = PICTURE_FIELDS[:5]


@dataclass(frozen=True)
class InventoryFile:
    path: str
    size: int | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class AuditResult:
    observation_count: int
    references: frozenset[str]
    inventory: frozenset[str]
    errors: tuple[str, ...]


def normalize_path(value: str) -> str:
    return str(PurePosixPath(value.replace("\\", "/").removeprefix("./")))


def read_references(database: Path) -> tuple[int, list[str], list[str]]:
    fields_sql = ", ".join(PICTURE_FIELDS)
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            f"SELECT sample_id, {fields_sql} FROM observations ORDER BY sample_id"
        ).fetchall()

    references: list[str] = []
    errors: list[str] = []
    for row in rows:
        sample_id = row[0]
        for index, (field, value) in enumerate(zip(PICTURE_FIELDS, row[1:]), start=1):
            if not value:
                if field in REQUIRED_PICTURE_FIELDS:
                    errors.append(f"{sample_id}: required attachment is empty: {field}")
                continue
            path = normalize_path(value)
            expected = f"DCIM/macedonia/{sample_id}_{index:02}.jpg"
            if path != expected:
                errors.append(f"{sample_id}: {field} is {path!r}, expected {expected!r}")
            references.append(path)

    duplicates = sorted(path for path, count in Counter(references).items() if count > 1)
    errors.extend(f"attachment path is referenced more than once: {path}" for path in duplicates)
    return len(rows), references, errors


def _inventory_items(payload: Any) -> list[InventoryFile]:
    if isinstance(payload, str):
        return [InventoryFile(normalize_path(payload))]
    if isinstance(payload, list):
        return [item for value in payload for item in _inventory_items(value)]
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("name"), str):
        return [
            InventoryFile(
                normalize_path(payload["name"]),
                payload.get("size") if isinstance(payload.get("size"), int) else None,
                payload.get("sha256")
                if isinstance(payload.get("sha256"), str)
                else None,
            )
        ]
    for key in ("results", "files", "cloud_files"):
        if key in payload:
            return _inventory_items(payload[key])
    return []


def inventory_from_json(path: Path) -> dict[str, InventoryFile]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {item.path: item for item in _inventory_items(payload)}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory_from_directory(root: Path) -> dict[str, InventoryFile]:
    inventory: dict[str, InventoryFile] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = normalize_path(path.relative_to(root).as_posix())
        inventory[relative] = InventoryFile(relative, path.stat().st_size, sha256(path))
    return inventory


def audit(
    database: Path,
    inventory: dict[str, InventoryFile] | None = None,
) -> AuditResult:
    observation_count, reference_list, errors = read_references(database)
    references = frozenset(reference_list)
    inventory_paths = frozenset(inventory or {})
    if inventory is not None:
        errors.extend(
            f"referenced attachment is missing from inventory: {path}"
            for path in sorted(references - inventory_paths)
        )
        errors.extend(
            f"attachment file is empty: {path}"
            for path, item in sorted(inventory.items())
            if path in references and item.size == 0
        )
    return AuditResult(
        observation_count,
        references,
        inventory_paths,
        tuple(errors),
    )


def write_manifest(
    output: Path,
    result: AuditResult,
    inventory: dict[str, InventoryFile],
) -> None:
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "observation_count": result.observation_count,
        "referenced_attachment_count": len(result.references),
        "files": [
            {
                "path": path,
                "size": inventory[path].size,
                "sha256": inventory[path].sha256,
            }
            for path in sorted(result.references & result.inventory)
        ],
    }
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit observation attachment references against cloud or archive files."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("qgis/macedonia/observations.gpkg"),
    )
    inventory_group = parser.add_mutually_exclusive_group()
    inventory_group.add_argument("--cloud-files-json", type=Path)
    inventory_group.add_argument("--attachments-root", type=Path)
    parser.add_argument("--manifest-out", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    inventory: dict[str, InventoryFile] | None = None
    if args.cloud_files_json:
        inventory = inventory_from_json(args.cloud_files_json)
    elif args.attachments_root:
        inventory = inventory_from_directory(args.attachments_root)

    result = audit(args.database, inventory)
    print(f"Observations: {result.observation_count}")
    print(f"Referenced attachments: {len(result.references)}")
    if inventory is not None:
        print(f"Inventory files: {len(result.inventory)}")
        print(f"Verified referenced files: {len(result.references & result.inventory)}")
    if result.errors:
        for error in result.errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)
    if args.manifest_out:
        if inventory is None:
            raise SystemExit("--manifest-out requires an inventory source")
        write_manifest(args.manifest_out, result, inventory)
        print(f"Manifest: {args.manifest_out}")
    print("Attachment audit passed")


if __name__ == "__main__":
    main()
