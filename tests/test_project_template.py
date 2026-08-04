from __future__ import annotations

import csv
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
PROJECT = ROOT / "qgis/macedonia/macedonia.qgs"


def test_project_is_valid_xml_and_uses_macedonia_identifiers() -> None:
    ET.parse(PROJECT)
    project_text = PROJECT.read_text(encoding="utf-8")

    assert "mnsl_" not in project_text
    assert "^mcdn_[0-9]{6}$" in project_text
    assert project_text.count("DCIM/macedonia/") == 6
    assert "optimized_maps/basemap.mbtiles" not in project_text
    assert "ScientificName&quot; || ' — ' || coalesce(&quot;taxon_rank&quot;" in project_text
    assert 'value="1000" name="FetchLimitNumber"' in project_text


def test_template_observations_are_empty() -> None:
    database = ROOT / "qgis/macedonia/observations.gpkg"
    with sqlite3.connect(database) as connection:
        count = connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]

    assert count == 0


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


def test_geopackage_rejects_malformed_and_duplicate_identity() -> None:
    database = ROOT / "qgis/macedonia/observations.gpkg"
    with sqlite3.connect(database) as connection:
        # GeoPackage spatial-index triggers expect functions supplied by
        # QGIS/OGR. These inserts have null geometry, so minimal stubs let
        # plain Python SQLite exercise the identity triggers in isolation.
        connection.create_function("ST_IsEmpty", 1, lambda _geometry: 1)
        connection.create_function("ST_MinX", 1, lambda _geometry: None)
        connection.create_function("ST_MaxX", 1, lambda _geometry: None)
        connection.create_function("ST_MinY", 1, lambda _geometry: None)
        connection.create_function("ST_MaxY", 1, lambda _geometry: None)
        connection.execute("SAVEPOINT identity_test")
        try:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO observations(sample_id, uuid_qfield) VALUES (?, ?)",
                    ("mcdn_1", "00000000-0000-4000-8000-000000000001"),
                )

            connection.execute(
                "INSERT INTO observations(sample_id, uuid_qfield) VALUES (?, ?)",
                ("mcdn_000001", "00000000-0000-4000-8000-000000000001"),
            )

            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO observations(sample_id, uuid_qfield) VALUES (?, ?)",
                    ("mcdn_000001", "00000000-0000-4000-8000-000000000002"),
                )

            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO observations(sample_id, uuid_qfield) VALUES (?, ?)",
                    ("mcdn_000002", "00000000-0000-4000-8000-000000000001"),
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
        "picture_panel",
        "picture_general",
        "picture_detail",
        "picture_cut",
        "picture_panel_label",
        "picture_free",
        "x_coord",
        "y_coord",
        "date",
    }
    assert all(
        duplicate_policies[field] == "DefaultValue" for field in protected_fields
    )


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
