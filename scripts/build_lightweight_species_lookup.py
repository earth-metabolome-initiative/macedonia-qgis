#!/usr/bin/env python3
"""Build a compact QField species lookup directly from an iNaturalist export."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

DEFAULT_INPUT = Path("data/inaturalist/macedonia_species_observations.csv")
DEFAULT_OUTPUT = Path("qgis/macedonia/species_list.csv")

OUTPUT_FIELDS = [
    "lookup_type",
    "inat_taxon_id",
    "scientific_name",
    "rank",
    "common_name",
    "iconic_taxon_name",
    "observations_in_region",
    "inat_observations_global",
    "wikipedia_url",
    "photo_url",
    "photo_license_code",
    "photo_attribution",
    "ScientificName",
    "MatchedCanonical",
    "TaxonId",
]


def build_lookup(input_path: Path, output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        required = {"taxon_id", "scientific_name"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required column(s): {', '.join(sorted(missing))}")

        rows = []
        for source_row in reader:
            scientific_name = source_row["scientific_name"].strip()
            taxon_id = source_row["taxon_id"].strip()
            row = {field: source_row.get(field, "") for field in OUTPUT_FIELDS}
            row.update(
                {
                    "lookup_type": "species",
                    "inat_taxon_id": taxon_id,
                    "ScientificName": scientific_name,
                    "MatchedCanonical": scientific_name,
                    "TaxonId": taxon_id,
                }
            )
            rows.append(row)

    rows.sort(key=lambda row: row["ScientificName"].casefold())
    with output_path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    count = build_lookup(args.input, args.output)
    print(f"Wrote {count} lookup rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
