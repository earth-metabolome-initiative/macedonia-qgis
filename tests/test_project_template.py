from __future__ import annotations

import csv
import json
import re
import shutil
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
PROJECT = ROOT / "qgis/macedonia/macedonia.qgs"
QUARANTINED_SAMPLE_ID = "mcdn_000100"
QUARANTINED_MANU_UUID = "67c6df7b-7538-438b-ae4c-d5881a98bd35"
QUARANTINED_JOVANA_UUID = "6cb125a1-8496-427d-a84b-fd3f4dd30260"


def test_project_is_valid_xml_and_uses_macedonia_identifiers() -> None:
    root = ET.parse(PROJECT).getroot()
    project_text = PROJECT.read_text(encoding="utf-8")

    assert "mnsl_" not in project_text
    assert "^mcdn_[0-9]{6}$" in project_text
    assert project_text.count("DCIM/macedonia/") == 6
    assert "optimized_maps/basemap.mbtiles" not in project_text
    species_layer = next(
        layer
        for layer in root.findall(".//maplayer")
        if layer.findtext("layername") == "species_list"
    )
    assert species_layer.findtext("previewExpression") == (
        '"ScientificName" || \' — \' || coalesce("taxon_rank", \'unranked\')'
    )
    assert any(
        option.get("value") == "1000"
        for option in root.findall(".//Option[@name='FetchLimitNumber']")
    )


def test_online_basemap_is_preserved_by_qfieldcloud_packaging() -> None:
    root = ET.parse(PROJECT).getroot()
    basemap = next(
        layer
        for layer in root.findall(".//maplayer")
        if layer.findtext("layername") == "google-earth-connection"
    )
    cloud_action = basemap.find(
        ".//Option[@name='QFieldSync/cloud_action']"
    )

    assert basemap.findtext("provider") == "wms"
    assert cloud_action is not None
    assert cloud_action.get("value") == "no_action"


def test_qfield_automatically_pushes_field_edits() -> None:
    root = ET.parse(PROJECT).getroot()

    assert root.findtext(".//forceAutoPush") == "1"
    assert root.findtext(".//forceAutoPushIntervalMins") == "15"


def test_ignored_offline_satellite_is_configured_for_qfield_packaging() -> None:
    root = ET.parse(PROJECT).getroot()
    basemap = next(
        layer
        for layer in root.findall(".//maplayer")
        if layer.findtext("layername")
        == "satellite (offline — Google z18)"
    )
    cloud_action = basemap.find(
        ".//Option[@name='QFieldSync/cloud_action']"
    )

    assert "qgis/macedonia/optimized_maps/macedonia_google_satellite_*.tif" in (
        ROOT / ".gitignore"
    ).read_text(encoding="utf-8")
    assert basemap.findtext("provider") == "gdal"
    assert basemap.get("hasScaleBasedVisibilityFlag") == "0"
    assert basemap.findtext("datasource") == (
        "./optimized_maps/macedonia_google_satellite_z18.tif"
    )
    assert cloud_action is not None
    assert cloud_action.get("value") == "no_action"


def test_active_observations_are_preserved_and_paths_match_identity() -> None:
    legacy_picture_paths = {
        ("mcdn_000356", 4): "DCIM/macedonia/mcdn_000370_04.jpg",
    }
    seen_legacy_paths: set[tuple[str, int]] = set()
    database = ROOT / "qgis/macedonia/observations.gpkg"
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT sample_id, uuid_qfield, picture_environment, "
            "picture_full_organism, picture_detail, picture_sampled_part, "
            "picture_sample_code, picture_free FROM observations"
        ).fetchall()

    sample_ids = {row[0] for row in rows}
    assert {"mcdn_000001", "mcdn_000002", "mcdn_000003", "mcdn_000004"} <= sample_ids
    assert len(sample_ids) == len(rows)
    assert len({row[1] for row in rows}) == len(rows)
    for row in rows:
        sample_id, uuid_qfield, *pictures = row
        assert re.fullmatch(r"mcdn_[0-9]{6}", sample_id)
        assert re.fullmatch(
            r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",
            uuid_qfield,
        )
        for number, picture in enumerate(pictures, start=1):
            if picture:
                key = (sample_id, number)
                expected = legacy_picture_paths.get(
                    key, f"DCIM/macedonia/{sample_id}_{number:02}.jpg"
                )
                assert picture == expected
                if key in legacy_picture_paths:
                    seen_legacy_paths.add(key)
    assert seen_legacy_paths == set(legacy_picture_paths)


def test_duplicate_label_case_remains_quarantined() -> None:
    database = ROOT / "qgis/macedonia/observations.gpkg"
    with sqlite3.connect(database) as connection:
        active_rows = connection.execute(
            "SELECT uuid_qfield, collector_fullname, taxon_name_final "
            "FROM observations WHERE sample_id = ?",
            (QUARANTINED_SAMPLE_ID,),
        ).fetchall()

    assert active_rows == [
        (QUARANTINED_MANU_UUID, "Emmanuel Defossez", "Bryophyta")
    ]
    assert all(row[0] != QUARANTINED_JOVANA_UUID for row in active_rows)

    documentation = (
        ROOT / "docs/mcdn_000100_quarantine.md"
    ).read_text(encoding="utf-8")
    assert QUARANTINED_MANU_UUID in documentation
    assert QUARANTINED_JOVANA_UUID in documentation
    assert "Held only in Jovana's device export" in documentation


def test_collector_roster_and_csv_match_geopackage() -> None:
    csv_path = ROOT / "qgis/macedonia/collector_list.csv"
    database = ROOT / "qgis/macedonia/collector_list.gpkg"
    with csv_path.open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        gpkg_rows = [
            {key: (value or "") for key, value in dict(row).items()}
            for row in connection.execute(
                "SELECT fullname, firstname, lastname, email, laboratory, ORCID, "
                "iNat_username FROM collector_list ORDER BY fid"
            )
        ]

    expected_emails = {
        "Pierre-Marie Allard": "pierre-marie.allard@unifr.ch",
        "Emmanuel Defossez": "emmanuel.defossez@unine.ch",
        "Olga Gigopulu": "olga.gigopulu@ff.ukim.edu.mk",
        "Gjoshe Stefkov": "gstefkov@yahoo.com",
        "Filip Todorov": "todorov03f@gmail.com",
        "Vladimir Krpach": "vkrpach@gmail.com",
        "Marijana Skoric": "mdevic@ibiss.bg.ac.rs",
        "Suzana Zivkovic": "suzy@ibiss.bg.ac.rs",
        "Jelena Bozunovic": "jelena.boljevic@ibiss.bg.ac.rs",
        "Milos Todorovic": "milos.todorovic@ibiss.bg.ac.rs",
        "Danijela Mišić": "dmisic@ibiss.bg.ac.rs",
        "Tijana Banjanac": "tbanjanac@ibiss.bg.ac.rs",
        "Uros Gasic": "uros.gasic@ibiss.bg.ac.rs",
    }
    by_name = {row["fullname"]: row for row in gpkg_rows}

    assert csv_rows == gpkg_rows
    assert len(gpkg_rows) >= len(expected_emails)
    assert {
        name: by_name[name]["email"] for name in expected_emails
    } == expected_emails
    assert by_name["Pierre-Marie Allard"]["iNat_username"] == "@pmallard"
    assert by_name["Emmanuel Defossez"]["iNat_username"] == "@manu_dfz"
    assert by_name["Olga Gigopulu"]["iNat_username"] == "@olgagigopulu"


def test_observation_identity_is_enforced_by_geopackage() -> None:
    database = ROOT / "qgis/macedonia/observations.gpkg"
    with sqlite3.connect(database) as connection:
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('observations')")
        }
        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'trigger' AND tbl_name = 'observations'"
            )
        }

    assert "observations_sample_id_unique" in indexes
    assert "observations_uuid_qfield_unique" in indexes
    assert {
        "observations_validate_identity_insert",
        "observations_validate_identity_update",
    } <= triggers


def test_geopackage_rejects_malformed_and_duplicate_identity(tmp_path: Path) -> None:
    database = tmp_path / "observations.gpkg"
    shutil.copy2(ROOT / "qgis/macedonia/observations.gpkg", database)
    with sqlite3.connect(database) as connection:
        # GeoPackage spatial-index triggers expect functions supplied by
        # QGIS/OGR. These inserts have null geometry, so minimal stubs let
        # plain Python SQLite exercise the identity triggers in isolation.
        connection.create_function("ST_IsEmpty", 1, lambda _geometry: 1)
        connection.create_function("ST_MinX", 1, lambda _geometry: None)
        connection.create_function("ST_MaxX", 1, lambda _geometry: None)
        connection.create_function("ST_MinY", 1, lambda _geometry: None)
        connection.create_function("ST_MaxY", 1, lambda _geometry: None)
        existing_ids = {
            row[0] for row in connection.execute("SELECT sample_id FROM observations")
        }
        available_numbers = (
            number
            for number in range(999999, -1, -1)
            if f"mcdn_{number:06}" not in existing_ids
        )
        sample_id = f"mcdn_{next(available_numbers):06}"
        other_sample_id = f"mcdn_{next(available_numbers):06}"
        connection.execute("SAVEPOINT identity_test")
        try:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO observations(sample_id, uuid_qfield) VALUES (?, ?)",
                    ("mcdn_1", "00000000-0000-4000-8000-000000000001"),
                )

            connection.execute(
                "INSERT INTO observations(sample_id, uuid_qfield) VALUES (?, ?)",
                (sample_id, "00000000-0000-4000-8000-000000000001"),
            )

            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO observations(sample_id, uuid_qfield) VALUES (?, ?)",
                    (sample_id, "00000000-0000-4000-8000-000000000002"),
                )

            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO observations(sample_id, uuid_qfield) VALUES (?, ?)",
                    (other_sample_id, "00000000-0000-4000-8000-000000000001"),
                )
        finally:
            connection.execute("ROLLBACK TO identity_test")
            connection.execute("RELEASE identity_test")


def test_observation_form_cannot_hide_or_copy_identity() -> None:
    root = ET.parse(PROJECT).getroot()
    observations = next(
        layer
        for layer in root.findall(".//maplayer")
        if layer.findtext("layername") == "observations"
    )

    sample_tab = observations.find(
        ".//attributeEditorContainer[@name='sample_id']"
    )
    assert sample_tab is not None
    assert sample_tab.get("visibilityExpressionEnabled") == "0"
    assert sample_tab.get("visibilityExpression") == ""

    duplicate_policies = {
        policy.get("field"): policy.get("policy")
        for policy in observations.findall("./duplicatePolicies/policy")
    }
    protected_fields = {
        "sample_id",
        "uuid_qfield",
        "picture_environment",
        "picture_full_organism",
        "picture_detail",
        "picture_sampled_part",
        "picture_sample_code",
        "picture_free",
        "x_coord",
        "y_coord",
        "date",
    }
    assert all(
        duplicate_policies[field] == "DefaultValue" for field in protected_fields
    )


def test_picture_field_names_and_attachment_numbering_are_current() -> None:
    expected_fields = {
        "picture_environment": "_01.jpg",
        "picture_full_organism": "_02.jpg",
        "picture_detail": "_03.jpg",
        "picture_sampled_part": "_04.jpg",
        "picture_sample_code": "_05.jpg",
        "picture_free": "_06.jpg",
    }
    database = ROOT / "qgis/macedonia/observations.gpkg"
    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(observations)")}

    root = ET.parse(PROJECT).getroot()
    observations = next(
        layer
        for layer in root.findall(".//maplayer")
        if layer.findtext("layername") == "observations"
    )
    naming_option = observations.find(
        ".//Option[@name='QFieldSync/attachment_naming']"
    )
    assert naming_option is not None
    attachment_naming = json.loads(naming_option.get("value", "{}"))

    assert expected_fields.keys() <= columns
    assert set(attachment_naming) == set(expected_fields)
    assert all(
        suffix in attachment_naming[field]
        for field, suffix in expected_fields.items()
    )
    assert not {
        "picture_panel",
        "picture_general",
        "picture_cut",
        "picture_panel_label",
    } & columns


def test_species_lookup_contains_col_higher_taxa_across_kingdoms() -> None:
    database = ROOT / "qgis/macedonia/species_list.gpkg"
    with sqlite3.connect(database) as connection:
        lookup_counts = dict(
            connection.execute(
                "SELECT lookup_type, COUNT(*) FROM species_list GROUP BY lookup_type"
            )
        )
        kingdoms = {
            row[0]
            for row in connection.execute(
                "SELECT ScientificName FROM species_list WHERE taxon_rank = 'kingdom'"
            )
        }
        genus_count = connection.execute(
            "SELECT COUNT(*) FROM species_list WHERE taxon_rank = 'genus'"
        ).fetchone()[0]
        resolver_count = connection.execute(
            "SELECT COUNT(*) FROM species_list "
            "WHERE resolver = 'Catalogue of Life 2026-07-17 XR'"
        ).fetchone()[0]
        total_count, unique_name_count = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT lower(ScientificName)) FROM species_list"
        ).fetchone()

    assert lookup_counts["species"] == 274
    assert lookup_counts["higher_taxon"] > 0
    assert {"Animalia", "Fungi", "Plantae", "Protozoa"} <= kingdoms
    assert genus_count > 0
    assert resolver_count == total_count
    assert unique_name_count == total_count


def test_all_supplied_locations_fit_inside_aoi() -> None:
    locations = ROOT / "data/field_locations.csv"
    with locations.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 7
    assert all(41.981 <= float(row["latitude"]) <= 42.053 for row in rows)
    assert all(20.787 <= float(row["longitude"]) <= 20.892 for row in rows)
