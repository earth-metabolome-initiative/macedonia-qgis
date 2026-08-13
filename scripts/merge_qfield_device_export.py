from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import struct
import subprocess
import tempfile
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
IDENTITY_FIELDS = ("sample_id", "uuid_qfield")
SAMPLE_ID_PATTERN = re.compile(r"mcdn_[0-9]{6}")
UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
)


class RescueError(RuntimeError):
    pass


@dataclass(frozen=True)
class Attachment:
    relative_path: str
    size: int
    sha256: str
    media_type: str


@dataclass(frozen=True)
class RescuePlan:
    source_table: str
    source_count: int
    target_count: int
    common_ids: tuple[str, ...]
    new_ids: tuple[str, ...]
    existing_differences: tuple[str, ...]
    conflicts: tuple[str, ...]
    attachments: tuple[Attachment, ...]
    compared_columns: tuple[str, ...]
    source_rows: dict[str, dict[str, Any]]
    target_rows: dict[str, dict[str, Any]]


def quote_identifier(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def connect_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [
        row[1]
        for row in connection.execute(
            f"PRAGMA table_info({quote_identifier(table)})"
        )
    ]


def find_observation_table(connection: sqlite3.Connection) -> str:
    required = {*IDENTITY_FIELDS, *PICTURE_FIELDS}
    candidates: list[str] = []
    for row in connection.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'gpkg_%' AND name NOT LIKE 'rtree_%'"
    ):
        table = row[0]
        if required <= set(table_columns(connection, table)):
            candidates.append(table)
    if len(candidates) != 1:
        raise RescueError(
            "expected exactly one observation-like table in device data.gpkg; "
            f"found {candidates or 'none'}"
        )
    return candidates[0]


def geometry_column(connection: sqlite3.Connection, table: str) -> str:
    row = connection.execute(
        "SELECT column_name FROM gpkg_geometry_columns WHERE table_name = ?",
        (table,),
    ).fetchone()
    if row is None:
        raise RescueError(f"table {table!r} has no registered GeoPackage geometry")
    return row[0]


def geometry_metadata(connection: sqlite3.Connection, table: str) -> tuple[Any, ...]:
    row = connection.execute(
        "SELECT column_name, geometry_type_name, srs_id, z, m "
        "FROM gpkg_geometry_columns WHERE table_name = ?",
        (table,),
    ).fetchone()
    if row is None:
        raise RescueError(f"table {table!r} has no registered GeoPackage geometry")
    return tuple(row)


def load_rows(
    connection: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    selected = ", ".join(quote_identifier(column) for column in columns)
    rows: dict[str, dict[str, Any]] = {}
    duplicate_ids: list[str] = []
    for raw_row in connection.execute(
        f"SELECT {selected} FROM {quote_identifier(table)} ORDER BY sample_id"
    ):
        row = dict(raw_row)
        sample_id = row["sample_id"]
        if sample_id in rows:
            duplicate_ids.append(sample_id)
        rows[sample_id] = row
    return rows, duplicate_ids


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_attachment_path(value: str) -> str:
    return str(PurePosixPath(value.replace("\\", "/").removeprefix("./")))


def inspect_attachment(
    root: Path,
    relative_path: str,
) -> Attachment:
    normalized = normalize_attachment_path(relative_path)
    root = root.resolve()
    path = (root / normalized).resolve()
    if not path.is_relative_to(root):
        raise RescueError(f"attachment escapes the attachment root: {relative_path!r}")
    if not path.is_file():
        raise RescueError(f"referenced attachment is missing: {normalized}")
    size = path.stat().st_size
    if size == 0:
        raise RescueError(f"referenced attachment is empty: {normalized}")
    with path.open("rb") as handle:
        header = handle.read(16)
        handle.seek(-2, os.SEEK_END)
        trailer = handle.read(2)
    if header.startswith(b"\xff\xd8") and trailer == b"\xff\xd9":
        media_type = "image/jpeg"
    elif header[4:8] == b"ftyp":
        media_type = "video-or-heif/iso-bmff"
    elif header.startswith(b"\x89PNG\r\n\x1a\n"):
        media_type = "image/png"
    else:
        raise RescueError(f"attachment has an unrecognized media header: {normalized}")
    return Attachment(normalized, size, sha256_file(path), media_type)


def validate_identity(sample_id: str, row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(sample_id, str) or SAMPLE_ID_PATTERN.fullmatch(sample_id) is None:
        errors.append(f"invalid sample ID: {sample_id!r}")
    uuid = row.get("uuid_qfield")
    if not isinstance(uuid, str) or UUID_PATTERN.fullmatch(uuid) is None:
        errors.append(f"{sample_id}: invalid uuid_qfield: {uuid!r}")
    return errors


def validate_row(sample_id: str, row: dict[str, Any]) -> list[str]:
    errors = validate_identity(sample_id, row)
    for number, field in enumerate(PICTURE_FIELDS, start=1):
        value = row.get(field)
        if not value:
            if field in REQUIRED_PICTURE_FIELDS:
                errors.append(f"{sample_id}: required attachment is empty: {field}")
            continue
        normalized = normalize_attachment_path(str(value))
        expected = f"DCIM/macedonia/{sample_id}_{number:02}.jpg"
        if normalized != expected:
            errors.append(f"{sample_id}: {field} is {normalized!r}, expected {expected!r}")
    return errors


def plan_rescue(
    source: Path,
    target: Path,
    source_attachments_root: Path,
    target_attachments_root: Path | None = None,
) -> RescuePlan:
    with connect_read_only(source) as source_db, connect_read_only(target) as target_db:
        source_table = find_observation_table(source_db)
        source_geometry = geometry_column(source_db, source_table)
        target_geometry = geometry_column(target_db, "observations")
        target_columns = table_columns(target_db, "observations")
        source_columns = set(table_columns(source_db, source_table))
        attribute_columns = [column for column in target_columns if column != "fid"]
        if target_geometry not in attribute_columns:
            raise RescueError("target observation geometry column is missing")
        missing = set(attribute_columns) - source_columns
        if missing:
            raise RescueError(f"device observation schema is missing columns: {sorted(missing)}")
        if source_geometry != target_geometry:
            raise RescueError(
                f"geometry column mismatch: device={source_geometry!r}, target={target_geometry!r}"
            )
        source_geometry_metadata = geometry_metadata(source_db, source_table)
        target_geometry_metadata = geometry_metadata(target_db, "observations")
        if source_geometry_metadata != target_geometry_metadata:
            raise RescueError(
                "geometry metadata mismatch: "
                f"device={source_geometry_metadata!r}, target={target_geometry_metadata!r}"
            )
        compared_columns = tuple(attribute_columns)
        source_rows, duplicate_ids = load_rows(
            source_db, source_table, compared_columns
        )
        target_rows, target_duplicate_ids = load_rows(
            target_db, "observations", compared_columns
        )

    conflicts = [f"duplicate device sample ID: {value}" for value in duplicate_ids]
    conflicts.extend(
        f"duplicate target sample ID: {value}" for value in target_duplicate_ids
    )
    source_uuids: dict[str, str] = {}
    target_uuids: dict[str, str] = {}
    for sample_id, row in target_rows.items():
        uuid = row["uuid_qfield"]
        if uuid in target_uuids:
            conflicts.append(
                f"duplicate target UUID {uuid}: {target_uuids[uuid]} and {sample_id}"
            )
        target_uuids[uuid] = sample_id
    for sample_id, row in source_rows.items():
        conflicts.extend(validate_identity(sample_id, row))
        uuid = row["uuid_qfield"]
        if uuid in source_uuids:
            conflicts.append(
                f"duplicate device UUID {uuid}: {source_uuids[uuid]} and {sample_id}"
            )
        source_uuids[uuid] = sample_id

    common_ids: list[str] = []
    new_ids: list[str] = []
    existing_differences: list[str] = []
    for sample_id, source_row in source_rows.items():
        target_row = target_rows.get(sample_id)
        if target_row is not None:
            if source_row["uuid_qfield"] != target_row["uuid_qfield"]:
                conflicts.append(
                    f"sample ID collision {sample_id}: device UUID "
                    f"{source_row['uuid_qfield']} != target UUID {target_row['uuid_qfield']}"
                )
                continue
            changed = [
                column
                for column in compared_columns
                if source_row[column] != target_row[column]
            ]
            if changed:
                existing_differences.append(
                    f"existing observation differs {sample_id}: {', '.join(changed)}"
                )
            else:
                common_ids.append(sample_id)
            continue
        uuid = source_row["uuid_qfield"]
        if uuid in target_uuids:
            conflicts.append(
                f"UUID collision {uuid}: device sample {sample_id} != "
                f"target sample {target_uuids[uuid]}"
            )
            continue
        new_ids.append(sample_id)

    for sample_id in new_ids:
        conflicts.extend(validate_row(sample_id, source_rows[sample_id]))

    attachments: dict[str, Attachment] = {}
    if not conflicts:
        for sample_id in new_ids:
            for field in PICTURE_FIELDS:
                value = source_rows[sample_id][field]
                if value:
                    item = inspect_attachment(source_attachments_root, str(value))
                    attachments[item.relative_path] = item

        if target_attachments_root is not None:
            for item in attachments.values():
                target_path = target_attachments_root / item.relative_path
                if target_path.exists():
                    target_item = inspect_attachment(
                        target_attachments_root, item.relative_path
                    )
                    if target_item.sha256 != item.sha256:
                        conflicts.append(
                            "attachment filename collision with different content: "
                            f"{item.relative_path}"
                        )

    return RescuePlan(
        source_table=source_table,
        source_count=len(source_rows),
        target_count=len(target_rows),
        common_ids=tuple(sorted(common_ids)),
        new_ids=tuple(sorted(new_ids)),
        existing_differences=tuple(sorted(existing_differences)),
        conflicts=tuple(conflicts),
        attachments=tuple(attachments[path] for path in sorted(attachments)),
        compared_columns=compared_columns,
        source_rows=source_rows,
        target_rows=target_rows,
    )


def process_using(path: Path) -> str | None:
    executable = shutil.which("lsof")
    if executable is None:
        return None
    result = subprocess.run(
        [executable, str(path.resolve())],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def ensure_target_is_closed(target: Path) -> None:
    wal = Path(f"{target}-wal")
    shm = Path(f"{target}-shm")
    journal = Path(f"{target}-journal")
    for path in (target, wal, shm, journal):
        usage = process_using(path)
        if usage:
            first_line = usage.splitlines()[0]
            raise RescueError(
                f"target is open in another process ({first_line}); close QGIS first"
            )
    if journal.exists():
        raise RescueError(f"target has an active SQLite rollback journal: {journal}")
    if wal.exists() and wal.stat().st_size > 0:
        raise RescueError(f"target has an uncheckpointed SQLite WAL: {wal}")
    # SQLite can leave an empty WAL and its SHM file behind after a clean close.
    # With no process holding any database file, those inert sidecars are safe.


def gpkg_point_coordinates(value: bytes | None) -> tuple[float, float] | None:
    if value is None:
        return None
    data = bytes(value)
    if len(data) < 13 or data[:2] != b"GP":
        raise RescueError("observation has an invalid GeoPackage geometry header")
    flags = data[3]
    if flags & 0b00010000:
        return None
    envelope_code = (flags >> 1) & 0b111
    envelope_doubles = {0: 0, 1: 4, 2: 6, 3: 6, 4: 8}.get(envelope_code)
    if envelope_doubles is None:
        raise RescueError("observation has an unsupported GeoPackage envelope")
    offset = 8 + envelope_doubles * 8
    if len(data) < offset + 21:
        raise RescueError("observation has a truncated point geometry")
    wkb_order = "<" if data[offset] == 1 else ">"
    geometry_type = struct.unpack_from(f"{wkb_order}I", data, offset + 1)[0]
    if geometry_type % 1000 != 1 and geometry_type & 0xFF != 1:
        raise RescueError("rescued observation geometry is not a point")
    return struct.unpack_from(f"{wkb_order}dd", data, offset + 5)


def register_spatial_trigger_functions(connection: sqlite3.Connection) -> None:
    def coordinate(value: bytes | None, index: int) -> float | None:
        coordinates = gpkg_point_coordinates(value)
        return None if coordinates is None else coordinates[index]

    connection.create_function(
        "ST_IsEmpty", 1, lambda value: int(gpkg_point_coordinates(value) is None)
    )
    connection.create_function("ST_MinX", 1, lambda value: coordinate(value, 0))
    connection.create_function("ST_MaxX", 1, lambda value: coordinate(value, 0))
    connection.create_function("ST_MinY", 1, lambda value: coordinate(value, 1))
    connection.create_function("ST_MaxY", 1, lambda value: coordinate(value, 1))


def insert_new_rows(candidate: Path, plan: RescuePlan) -> None:
    columns = ", ".join(quote_identifier(column) for column in plan.compared_columns)
    placeholders = ", ".join("?" for _ in plan.compared_columns)
    statement = f"INSERT INTO observations ({columns}) VALUES ({placeholders})"
    with sqlite3.connect(candidate) as connection:
        register_spatial_trigger_functions(connection)
        for sample_id in plan.new_ids:
            row = plan.source_rows[sample_id]
            try:
                connection.execute(
                    statement,
                    tuple(row[column] for column in plan.compared_columns),
                )
            except sqlite3.IntegrityError as error:
                raise RescueError(f"cannot append {sample_id}: {error}") from error
        connection.execute(
            "UPDATE gpkg_contents SET last_change = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
            "WHERE table_name = 'observations'"
        )


def validate_candidate(
    candidate: Path,
    plan: RescuePlan,
    source_attachments_root: Path,
    target_attachments_root: Path,
) -> None:
    with connect_read_only(candidate) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RescueError(f"candidate GeoPackage integrity check failed: {integrity}")
        rows, duplicate_ids = load_rows(connection, "observations", plan.compared_columns)
        if duplicate_ids:
            raise RescueError(f"candidate contains duplicate sample IDs: {duplicate_ids}")
        uuid_count = connection.execute(
            "SELECT count(DISTINCT uuid_qfield) FROM observations"
        ).fetchone()[0]
        if len(rows) != plan.target_count + len(plan.new_ids):
            raise RescueError("candidate observation count is not the expected count")
        if uuid_count != len(rows):
            raise RescueError("candidate contains duplicate UUIDs")
        for sample_id, original in plan.target_rows.items():
            if rows.get(sample_id) != original:
                raise RescueError(f"candidate changed an existing observation: {sample_id}")
        for sample_id in plan.new_ids:
            if rows.get(sample_id) != plan.source_rows[sample_id]:
                raise RescueError(f"candidate did not preserve rescued observation: {sample_id}")
        for sample_id, row in rows.items():
            if sample_id in plan.new_ids:
                row_errors = validate_row(sample_id, row)
                if row_errors:
                    raise RescueError("; ".join(row_errors))
            for field in PICTURE_FIELDS:
                value = row[field]
                if value:
                    root = (
                        source_attachments_root
                        if sample_id in plan.new_ids
                        else target_attachments_root
                    )
                    inspect_attachment(root, str(value))


def build_candidate(
    target: Path,
    source_attachments_root: Path,
    target_attachments_root: Path,
    plan: RescuePlan,
) -> Path:
    descriptor, candidate_name = tempfile.mkstemp(
        prefix=f".{target.stem}.rescue-",
        suffix=target.suffix,
        dir=target.parent,
    )
    os.close(descriptor)
    candidate = Path(candidate_name)
    try:
        shutil.copy2(target, candidate)
        if plan.new_ids:
            insert_new_rows(candidate, plan)
        validate_candidate(
            candidate,
            plan,
            source_attachments_root,
            target_attachments_root,
        )
    except Exception:
        candidate.unlink(missing_ok=True)
        raise
    return candidate


def install_attachments(
    plan: RescuePlan,
    source_root: Path,
    target_root: Path,
) -> None:
    for attachment in plan.attachments:
        source = source_root / attachment.relative_path
        target = target_root / attachment.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if sha256_file(target) != attachment.sha256:
                raise RescueError(
                    "attachment changed after validation: "
                    f"{attachment.relative_path}"
                )
            continue
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.rescue-",
            dir=target.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output, source.open("rb") as input_file:
                shutil.copyfileobj(input_file, output)
                output.flush()
                os.fsync(output.fileno())
            if sha256_file(temporary) != attachment.sha256:
                raise RescueError(
                    f"attachment changed while copying: {attachment.relative_path}"
                )
            try:
                os.link(temporary, target)
            except FileExistsError:
                if sha256_file(target) != attachment.sha256:
                    raise RescueError(
                        "attachment appeared with different content while copying: "
                        f"{attachment.relative_path}"
                    )
        finally:
            temporary.unlink(missing_ok=True)


def delta_summary(source: Path) -> dict[str, int] | None:
    delta_path = source.with_name("deltafile.json")
    if not delta_path.is_file():
        return None
    payload = json.loads(delta_path.read_text(encoding="utf-8-sig"))
    return {
        "deltas": len(payload.get("deltas", [])),
        "files": len(payload.get("files", [])),
    }


def report_payload(
    args: argparse.Namespace,
    plan: RescuePlan,
    before_sha256: str,
    candidate_sha256: str,
    applied: bool,
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "device": args.device_name or args.device_export.name,
        "source": str(args.data_gpkg),
        "source_attachments_root": str(args.source_attachments_root),
        "source_sha256": sha256_file(args.data_gpkg),
        "source_table": plan.source_table,
        "deltafile": delta_summary(args.data_gpkg),
        "target": str(args.database),
        "target_sha256_before": before_sha256,
        "target_sha256_candidate": candidate_sha256,
        "applied": applied,
        "source_observation_count": plan.source_count,
        "target_observation_count_before": plan.target_count,
        "target_observation_count_after": plan.target_count + len(plan.new_ids),
        "identical_existing_ids": list(plan.common_ids),
        "target_versions_preserved": list(plan.existing_differences),
        "rescued_ids": list(plan.new_ids),
        "attachments": [attachment.__dict__ for attachment in plan.attachments],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Safely recover new observations from an exported QField data.gpkg. "
            "The default is a complete dry run; --apply atomically installs the candidate."
        )
    )
    parser.add_argument("device_export", type=Path)
    parser.add_argument("--data-gpkg", type=Path)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("qgis/macedonia/observations.gpkg"),
    )
    parser.add_argument(
        "--attachments-root",
        type=Path,
        default=Path("qgis/macedonia"),
    )
    parser.add_argument(
        "--source-attachments-root",
        type=Path,
        help=(
            "root containing the phone's DCIM directory; defaults to the device "
            "export when it contains DCIM, otherwise --attachments-root"
        ),
    )
    parser.add_argument("--device-name")
    parser.add_argument("--report-out", type=Path)
    parser.add_argument(
        "--keep-target-existing",
        action="store_true",
        help=(
            "preserve the target version when the same sample ID and UUID have "
            "different attributes, while still appending genuinely new rows"
        ),
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.data_gpkg is None:
        args.data_gpkg = args.device_export / "data.gpkg"
    if args.source_attachments_root is None:
        args.source_attachments_root = (
            args.device_export
            if (args.device_export / "DCIM").is_dir()
            else args.attachments_root
        )
    return args


def main() -> None:
    args = parse_args()
    candidate: Path | None = None
    try:
        if not args.data_gpkg.is_file():
            raise RescueError(f"device GeoPackage not found: {args.data_gpkg}")
        if not args.database.is_file():
            raise RescueError(f"target GeoPackage not found: {args.database}")
        ensure_target_is_closed(args.database)
        plan = plan_rescue(
            args.data_gpkg,
            args.database,
            args.source_attachments_root,
            args.attachments_root,
        )
        print(f"Device observations: {plan.source_count}")
        print(f"Main observations before: {plan.target_count}")
        print(f"Identical existing observations: {len(plan.common_ids)}")
        print(f"New observations: {len(plan.new_ids)}")
        if plan.new_ids:
            print(f"New sample IDs: {', '.join(plan.new_ids)}")
        print(f"Verified new attachment files: {len(plan.attachments)}")
        if plan.existing_differences:
            for difference in plan.existing_differences:
                print(f"EXISTING DIFFERENCE: {difference}")
            if not args.keep_target_existing:
                raise RescueError(
                    "existing observations changed; nothing was changed. Review them, "
                    "then use --keep-target-existing to preserve the target versions"
                )
            print(
                "Target versions of differing existing observations will be preserved"
            )
        if plan.conflicts:
            for conflict in plan.conflicts:
                print(f"CONFLICT: {conflict}")
            raise RescueError("rescue has conflicts; nothing was changed")

        before_sha256 = sha256_file(args.database)
        candidate = build_candidate(
            args.database,
            args.source_attachments_root,
            args.attachments_root,
            plan,
        )
        candidate_sha256 = sha256_file(candidate)
        if sha256_file(args.database) != before_sha256:
            raise RescueError("target changed during validation; nothing was changed")

        applied = False
        if args.apply and plan.new_ids:
            install_attachments(
                plan,
                args.source_attachments_root,
                args.attachments_root,
            )
            validate_candidate(
                candidate,
                plan,
                args.attachments_root,
                args.attachments_root,
            )
            with candidate.open("rb") as handle:
                os.fsync(handle.fileno())
            os.replace(candidate, args.database)
            candidate = None
            applied = True
            print(f"Applied: main database now has {plan.target_count + len(plan.new_ids)} observations")
            print(
                "NEXT: do not pull/synchronize from Cloud. In QFieldSync, upload "
                "observations.gpkg by choosing the Local file first."
            )
        elif args.apply:
            print("Applied: no new observations; target was already up to date")
        else:
            print(
                "Dry run passed: validated candidate would contain "
                f"{plan.target_count + len(plan.new_ids)} observations"
            )
            print("Nothing was changed; use --apply only after closing QGIS")

        if args.report_out:
            payload = report_payload(
                args,
                plan,
                before_sha256,
                candidate_sha256,
                applied,
            )
            args.report_out.write_text(
                json.dumps(payload, indent=2) + "\n", encoding="utf-8"
            )
            print(f"Report: {args.report_out}")
    except (OSError, sqlite3.Error, subprocess.CalledProcessError, RescueError) as error:
        raise SystemExit(f"ERROR: {error}") from error
    finally:
        if candidate is not None:
            candidate.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
