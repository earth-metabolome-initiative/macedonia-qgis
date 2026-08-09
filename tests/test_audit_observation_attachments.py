import json
import sqlite3
from pathlib import Path

from scripts import audit_observation_attachments as attachments


def create_database(path: Path) -> None:
    columns = ", ".join(f"{field} TEXT" for field in attachments.PICTURE_FIELDS)
    with sqlite3.connect(path) as connection:
        connection.execute(f"CREATE TABLE observations (sample_id TEXT, {columns})")
        pictures = [f"DCIM/macedonia/mcdn_000001_{number:02}.jpg" for number in range(1, 7)]
        connection.execute(
            f"INSERT INTO observations VALUES ({', '.join('?' for _ in range(7))})",
            ("mcdn_000001", *pictures),
        )


def test_audit_accepts_complete_cloud_inventory(tmp_path: Path) -> None:
    database = tmp_path / "observations.gpkg"
    create_database(database)
    cloud_json = tmp_path / "files.json"
    cloud_json.write_text(
        json.dumps(
            [
                {"name": f"DCIM/macedonia/mcdn_000001_{number:02}.jpg", "size": 42}
                for number in range(1, 7)
            ]
        ),
        encoding="utf-8",
    )

    result = attachments.audit(database, attachments.inventory_from_json(cloud_json))

    assert result.observation_count == 1
    assert len(result.references) == 6
    assert not result.errors


def test_audit_reports_missing_cloud_file_and_bad_reference(tmp_path: Path) -> None:
    database = tmp_path / "observations.gpkg"
    create_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE observations SET picture_environment = ?",
            ("DCIM/macedonia/wrong.jpg",),
        )
    inventory = {
        f"DCIM/macedonia/mcdn_000001_{number:02}.jpg": attachments.InventoryFile(
            f"DCIM/macedonia/mcdn_000001_{number:02}.jpg", 42
        )
        for number in range(2, 7)
    }

    result = attachments.audit(database, inventory)

    assert any("expected" in error for error in result.errors)
    assert any("missing from inventory" in error for error in result.errors)


def test_directory_inventory_hashes_files(tmp_path: Path) -> None:
    attachment = tmp_path / "DCIM/macedonia/mcdn_000001_01.jpg"
    attachment.parent.mkdir(parents=True)
    attachment.write_bytes(b"photo")

    inventory = attachments.inventory_from_directory(tmp_path)

    item = inventory["DCIM/macedonia/mcdn_000001_01.jpg"]
    assert item.size == 5
    assert item.sha256 == attachments.sha256(attachment)
