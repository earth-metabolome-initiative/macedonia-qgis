from __future__ import annotations

import csv

import pytest

from scripts.build_lightweight_species_lookup import build_lookup


def test_build_lookup_maps_qfield_fields_and_sorts(tmp_path) -> None:
    source = tmp_path / "species.csv"
    output = tmp_path / "lookup.csv"
    source.write_text(
        "taxon_id,scientific_name,rank,common_name\n"
        "2,Zeta plant,species,Zeta\n"
        "1,Alpha plant,species,Alpha\n",
        encoding="utf-8",
    )

    assert build_lookup(source, output) == 2
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert [row["ScientificName"] for row in rows] == ["Alpha plant", "Zeta plant"]
    assert rows[0]["lookup_type"] == "species"
    assert rows[0]["MatchedCanonical"] == "Alpha plant"
    assert rows[0]["TaxonId"] == "1"
    assert rows[0]["inat_taxon_id"] == "1"


def test_build_lookup_requires_identifiers(tmp_path) -> None:
    source = tmp_path / "species.csv"
    source.write_text("name\nAlpha plant\n", encoding="utf-8")

    with pytest.raises(ValueError, match="scientific_name, taxon_id"):
        build_lookup(source, tmp_path / "lookup.csv")
