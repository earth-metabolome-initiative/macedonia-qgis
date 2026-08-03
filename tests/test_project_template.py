from __future__ import annotations

import csv
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parents[1]
PROJECT = ROOT / "qgis/macedonia/macedonia.qgs"


def test_project_is_valid_xml_and_uses_macedonia_identifiers() -> None:
    ET.parse(PROJECT)
    project_text = PROJECT.read_text(encoding="utf-8")

    assert "mnsl_" not in project_text
    assert "^mcdn_[0-9]{6}$" in project_text
    assert project_text.count("DCIM/macedonia/") == 6
    assert "optimized_maps/basemap.mbtiles" not in project_text


def test_template_observations_are_empty() -> None:
    database = ROOT / "qgis/macedonia/observations.gpkg"
    with sqlite3.connect(database) as connection:
        count = connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]

    assert count == 0


def test_all_supplied_locations_fit_inside_aoi() -> None:
    locations = ROOT / "data/field_locations.csv"
    with locations.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 7
    assert all(41.981 <= float(row["latitude"]) <= 42.053 for row in rows)
    assert all(20.787 <= float(row["longitude"]) <= 20.892 for row in rows)
