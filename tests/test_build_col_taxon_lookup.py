from __future__ import annotations

import csv

from scripts.build_col_taxon_lookup import (
    Resolution,
    Taxon,
    build_lookup,
    expected_kingdom,
    match_payload_to_resolution,
    select_resolution,
)


def test_expected_kingdom_covers_non_plant_iconic_taxa() -> None:
    assert expected_kingdom("Plantae") == "Plantae"
    assert expected_kingdom("Fungi") == "Fungi"
    assert expected_kingdom("Insecta") == "Animalia"
    assert expected_kingdom("Aves") == "Animalia"
    assert expected_kingdom("Protozoa") == "Protozoa"


def test_select_resolution_prefers_exact_accepted_name_in_expected_kingdom() -> None:
    payload = {
        "result": [
            {
                "id": "wrong",
                "classification": [
                    {"id": "animals", "name": "Animalia", "rank": "kingdom"},
                    {"id": "wrong", "name": "Abies alba", "rank": "species"},
                ],
                "usage": {
                    "id": "wrong",
                    "status": "accepted",
                    "name": {"scientificName": "Abies alba", "rank": "species"},
                },
            },
            {
                "id": "abies",
                "classification": [
                    {"id": "plants", "name": "Plantae", "rank": "kingdom"},
                    {"id": "genus", "name": "Abies", "rank": "genus"},
                    {"id": "abies", "name": "Abies alba", "rank": "species"},
                ],
                "usage": {
                    "id": "abies",
                    "status": "accepted",
                    "name": {"scientificName": "Abies alba", "rank": "species"},
                },
            },
        ]
    }

    resolution = select_resolution(payload, "Abies alba", "Plantae")

    assert resolution is not None
    assert resolution.accepted.id == "abies"
    assert [taxon.name for taxon in resolution.lineage] == [
        "Plantae",
        "Abies",
        "Abies alba",
    ]


def test_match_payload_accepts_col_variant_and_reverses_classification() -> None:
    payload = {
        "match": True,
        "type": "variant",
        "usage": {
            "id": "species",
            "name": "Zygaena (Zygaena) filipendulae",
            "rank": "species",
            "status": "accepted",
            "classification": [
                {"id": "genus", "name": "Zygaena", "rank": "genus"},
                {"id": "kingdom", "name": "Animalia", "rank": "kingdom"},
                {"id": "domain", "name": "Eukaryota", "rank": "domain"},
            ],
        },
    }

    resolution = match_payload_to_resolution(payload, "Zygaena filipendulae", "Animalia")

    assert resolution is not None
    assert resolution.match_type == "variant"
    assert [taxon.name for taxon in resolution.lineage] == [
        "Eukaryota",
        "Animalia",
        "Zygaena",
        "Zygaena (Zygaena) filipendulae",
    ]


def test_match_payload_uses_accepted_parent_for_synonym() -> None:
    payload = {
        "match": True,
        "type": "variant",
        "usage": {
            "id": "synonym",
            "name": "Veronica kindlii",
            "rank": "species",
            "status": "synonym",
            "classification": [
                {
                    "id": "accepted-subspecies",
                    "name": "Veronica orsiniana subsp. orsiniana",
                    "rank": "subspecies",
                },
                {"id": "accepted-species", "name": "Veronica orsiniana", "rank": "species"},
                {"id": "genus", "name": "Veronica", "rank": "genus"},
                {"id": "kingdom", "name": "Plantae", "rank": "kingdom"},
            ],
        },
    }

    resolution = match_payload_to_resolution(payload, "Veronica kindlii", "Plantae")

    assert resolution is not None
    assert resolution.status == "synonym"
    assert resolution.accepted == Taxon(
        "accepted-subspecies", "Veronica orsiniana subsp. orsiniana", "subspecies"
    )


def test_build_lookup_includes_multiple_kingdoms_and_genera(tmp_path) -> None:
    source = tmp_path / "species.csv"
    output = tmp_path / "lookup.csv"
    source.write_text(
        "taxon_id,scientific_name,rank,common_name,iconic_taxon_name\n"
        "1,Abies alba,species,silver fir,Plantae\n"
        "2,Vulpes vulpes,species,red fox,Mammalia\n"
        "3,Amanita muscaria,species,fly agaric,Fungi\n",
        encoding="utf-8",
    )

    classifications = {
        "Abies alba": ("Plantae", "Abies"),
        "Vulpes vulpes": ("Animalia", "Vulpes"),
        "Amanita muscaria": ("Fungi", "Amanita"),
    }

    def fake_resolver(name: str, kingdom: str | None) -> Resolution:
        expected, genus = classifications[name]
        assert kingdom == expected
        lineage = (
            Taxon(f"{expected}-id", expected, "kingdom"),
            Taxon(f"{genus}-id", genus, "genus"),
            Taxon(f"{name}-id", name, "species"),
        )
        return Resolution(name, lineage[-1], lineage, "accepted", "exact")

    total, resolved, higher = build_lookup(
        source, output, resolver=fake_resolver, workers=2
    )

    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    by_name = {row["ScientificName"]: row for row in rows}

    assert total == 9
    assert resolved == 3
    assert higher == 6
    assert {"Plantae", "Animalia", "Fungi", "Abies", "Vulpes", "Amanita"} <= by_name.keys()
    assert by_name["Abies"]["taxon_rank"] == "genus"
    assert by_name["Vulpes vulpes"]["kingdom"] == "Animalia"
    assert by_name["Amanita muscaria"]["resolver"] == "Catalogue of Life 2026-07-17 XR"
