from __future__ import annotations

import sqlite3
import struct
from pathlib import Path

import pytest

from scripts import merge_qfield_device_export as rescue

SOURCE_TABLE = "device_observations_hash"


def create_geopackage(path: Path, table: str, *, target: bool) -> None:
    fields = ", ".join(f"{field} TEXT" for field in rescue.PICTURE_FIELDS)
    primary_key = "fid INTEGER PRIMARY KEY, " if target else "fid_1 INTEGER PRIMARY KEY, "
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE gpkg_geometry_columns "
            "(table_name TEXT, column_name TEXT, geometry_type_name TEXT, "
            "srs_id INTEGER, z INTEGER, m INTEGER)"
        )
        connection.execute(
            "CREATE TABLE gpkg_contents (table_name TEXT, last_change TEXT)"
        )
        connection.execute("INSERT INTO gpkg_contents VALUES (?, '')", (table,))
        connection.execute(
            f'CREATE TABLE "{table}" ('
            f"{primary_key}geom BLOB, sample_id TEXT, uuid_qfield TEXT, {fields})"
        )
        connection.execute(
            "INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', 'POINT', 4326, 0, 0)",
            (table,),
        )
        if target:
            connection.execute(
                "CREATE TABLE rtree_observations_geom "
                "(id INTEGER PRIMARY KEY, minx REAL, maxx REAL, miny REAL, maxy REAL)"
            )
            connection.execute(
                "CREATE TRIGGER observations_spatial_index AFTER INSERT ON observations "
                "WHEN new.geom IS NOT NULL AND NOT ST_IsEmpty(new.geom) BEGIN "
                "INSERT INTO rtree_observations_geom VALUES "
                "(new.fid, ST_MinX(new.geom), ST_MaxX(new.geom), "
                "ST_MinY(new.geom), ST_MaxY(new.geom)); END"
            )


def point_geometry(x: float = 21.1284, y: float = 42.1859) -> bytes:
    return (
        b"GP\x00\x01"
        + struct.pack("<i", 4326)
        + b"\x01"
        + struct.pack("<I", 1)
        + struct.pack("<dd", x, y)
    )


def observation_values(sample_id: str, uuid: str) -> tuple[object, ...]:
    pictures = [
        f"DCIM/macedonia/{sample_id}_{number:02}.jpg" for number in range(1, 6)
    ]
    return (point_geometry(), sample_id, uuid, *pictures, None)


def insert_observation(path: Path, table: str, sample_id: str, uuid: str) -> None:
    fields = ", ".join(rescue.PICTURE_FIELDS)
    placeholders = ", ".join("?" for _ in range(9))
    with sqlite3.connect(path) as connection:
        rescue.register_spatial_trigger_functions(connection)
        connection.execute(
            f'INSERT INTO "{table}" (geom, sample_id, uuid_qfield, {fields}) '
            f"VALUES ({placeholders})",
            observation_values(sample_id, uuid),
        )


def write_photos(root: Path, sample_id: str) -> None:
    for number in range(1, 6):
        path = root / f"DCIM/macedonia/{sample_id}_{number:02}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xff\xd8photo\xff\xd9")


def test_plan_rescue_finds_identical_and_new_observations(tmp_path: Path) -> None:
    target = tmp_path / "observations.gpkg"
    source = tmp_path / "data.gpkg"
    create_geopackage(target, "observations", target=True)
    create_geopackage(source, SOURCE_TABLE, target=False)
    insert_observation(
        target,
        "observations",
        "mcdn_000001",
        "00000000-0000-4000-8000-000000000001",
    )
    insert_observation(
        source,
        SOURCE_TABLE,
        "mcdn_000001",
        "00000000-0000-4000-8000-000000000001",
    )
    insert_observation(
        source,
        SOURCE_TABLE,
        "mcdn_000002",
        "00000000-0000-4000-8000-000000000002",
    )
    write_photos(tmp_path, "mcdn_000002")

    plan = rescue.plan_rescue(source, target, tmp_path)

    assert plan.conflicts == ()
    assert plan.common_ids == ("mcdn_000001",)
    assert plan.new_ids == ("mcdn_000002",)
    assert len(plan.attachments) == 5
    assert {item.media_type for item in plan.attachments} == {"image/jpeg"}


def test_plan_rescue_rejects_different_existing_record(tmp_path: Path) -> None:
    target = tmp_path / "observations.gpkg"
    source = tmp_path / "data.gpkg"
    create_geopackage(target, "observations", target=True)
    create_geopackage(source, SOURCE_TABLE, target=False)
    insert_observation(
        target,
        "observations",
        "mcdn_000001",
        "00000000-0000-4000-8000-000000000001",
    )
    insert_observation(
        source,
        SOURCE_TABLE,
        "mcdn_000001",
        "00000000-0000-4000-8000-000000000009",
    )

    plan = rescue.plan_rescue(source, target, tmp_path)

    assert any("sample ID collision mcdn_000001" in item for item in plan.conflicts)
    assert plan.new_ids == ()


def test_plan_rescue_separates_same_identity_attribute_changes(tmp_path: Path) -> None:
    target = tmp_path / "observations.gpkg"
    source = tmp_path / "data.gpkg"
    create_geopackage(target, "observations", target=True)
    create_geopackage(source, SOURCE_TABLE, target=False)
    sample_id = "mcdn_000001"
    uuid = "00000000-0000-4000-8000-000000000001"
    insert_observation(target, "observations", sample_id, uuid)
    insert_observation(source, SOURCE_TABLE, sample_id, uuid)
    with sqlite3.connect(source) as connection:
        connection.execute(
            f'UPDATE "{SOURCE_TABLE}" SET picture_free = ? WHERE sample_id = ?',
            ("DCIM/macedonia/mcdn_000001_06.jpg", sample_id),
        )

    plan = rescue.plan_rescue(source, target, tmp_path)

    assert plan.conflicts == ()
    assert plan.common_ids == ()
    assert plan.new_ids == ()
    assert plan.existing_differences == (
        "existing observation differs mcdn_000001: picture_free",
    )


def test_plan_rescue_rejects_missing_new_attachment(tmp_path: Path) -> None:
    target = tmp_path / "observations.gpkg"
    source = tmp_path / "data.gpkg"
    create_geopackage(target, "observations", target=True)
    create_geopackage(source, SOURCE_TABLE, target=False)
    insert_observation(
        source,
        SOURCE_TABLE,
        "mcdn_000002",
        "00000000-0000-4000-8000-000000000002",
    )

    with pytest.raises(rescue.RescueError, match="referenced attachment is missing"):
        rescue.plan_rescue(source, target, tmp_path)


def test_inspect_attachment_accepts_iso_base_media(tmp_path: Path) -> None:
    path = tmp_path / "DCIM/macedonia/mcdn_000001_01.jpg"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\x00\x00\x00\x18ftypisomvideo-data")

    attachment = rescue.inspect_attachment(tmp_path, "DCIM/macedonia/mcdn_000001_01.jpg")

    assert attachment.media_type == "video-or-heif/iso-bmff"


def test_gpkg_point_coordinates_reads_little_endian_point() -> None:
    assert rescue.gpkg_point_coordinates(point_geometry()) == pytest.approx(
        (21.1284, 42.1859)
    )


def test_build_candidate_inserts_point_and_spatial_index(tmp_path: Path) -> None:
    target = tmp_path / "observations.gpkg"
    source = tmp_path / "data.gpkg"
    create_geopackage(target, "observations", target=True)
    create_geopackage(source, SOURCE_TABLE, target=False)
    insert_observation(
        source,
        SOURCE_TABLE,
        "mcdn_000002",
        "00000000-0000-4000-8000-000000000002",
    )
    write_photos(tmp_path, "mcdn_000002")
    plan = rescue.plan_rescue(source, target, tmp_path, tmp_path)

    candidate = rescue.build_candidate(target, tmp_path, tmp_path, plan)
    try:
        with sqlite3.connect(candidate) as connection:
            assert connection.execute("SELECT count(*) FROM observations").fetchone()[0] == 1
            assert (
                connection.execute(
                    "SELECT minx, maxx, miny, maxy FROM rtree_observations_geom"
                ).fetchone()
                == pytest.approx((21.1284, 21.1284, 42.1859, 42.1859))
            )
    finally:
        candidate.unlink()


def test_build_candidate_preserves_legacy_picture_path_on_existing_row(
    tmp_path: Path,
) -> None:
    target = tmp_path / "observations.gpkg"
    source = tmp_path / "data.gpkg"
    create_geopackage(target, "observations", target=True)
    create_geopackage(source, SOURCE_TABLE, target=False)
    existing_id = "mcdn_000001"
    existing_uuid = "00000000-0000-4000-8000-000000000001"
    legacy_path = "DCIM/macedonia/mcdn_000370_04.jpg"
    insert_observation(target, "observations", existing_id, existing_uuid)
    insert_observation(source, SOURCE_TABLE, existing_id, existing_uuid)
    write_photos(tmp_path, existing_id)
    for path, table in ((target, "observations"), (source, SOURCE_TABLE)):
        with sqlite3.connect(path) as connection:
            connection.execute(
                f'UPDATE "{table}" SET picture_sampled_part = ? WHERE sample_id = ?',
                (legacy_path, existing_id),
            )
    legacy_photo = tmp_path / legacy_path
    legacy_photo.parent.mkdir(parents=True, exist_ok=True)
    legacy_photo.write_bytes(b"\xff\xd8legacy-photo\xff\xd9")

    insert_observation(
        source,
        SOURCE_TABLE,
        "mcdn_000002",
        "00000000-0000-4000-8000-000000000002",
    )
    write_photos(tmp_path, "mcdn_000002")

    plan = rescue.plan_rescue(source, target, tmp_path, tmp_path)
    assert plan.conflicts == ()
    assert plan.common_ids == (existing_id,)
    assert plan.new_ids == ("mcdn_000002",)

    candidate = rescue.build_candidate(target, tmp_path, tmp_path, plan)
    try:
        with sqlite3.connect(candidate) as connection:
            assert connection.execute(
                "SELECT picture_sampled_part FROM observations WHERE sample_id = ?",
                (existing_id,),
            ).fetchone()[0] == legacy_path
    finally:
        candidate.unlink()


def test_nonempty_wal_blocks_even_dry_run(tmp_path: Path) -> None:
    target = tmp_path / "observations.gpkg"
    target.touch()
    Path(f"{target}-wal").write_bytes(b"pending transaction")

    with pytest.raises(rescue.RescueError, match="uncheckpointed SQLite WAL"):
        rescue.ensure_target_is_closed(target)


def test_inert_wal_sidecars_do_not_block(tmp_path: Path) -> None:
    target = tmp_path / "observations.gpkg"
    target.touch()
    Path(f"{target}-wal").touch()
    Path(f"{target}-shm").touch()

    rescue.ensure_target_is_closed(target)
