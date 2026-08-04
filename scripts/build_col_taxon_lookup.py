#!/usr/bin/env python3
"""Build the offline QField taxon lookup using Catalogue of Life classifications."""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_INPUT = Path("data/inaturalist/macedonia_species_observations.csv")
DEFAULT_OUTPUT = Path("qgis/macedonia/species_list.csv")
COL_DATASET_KEY = 315834
COL_RELEASE = "Catalogue of Life 2026-07-17 XR"
COL_DOI = "10.48580/dgykv"
COL_SEARCH_API = f"https://api.checklistbank.org/dataset/{COL_DATASET_KEY}/nameusage/search"
COL_MATCH_API = f"https://api.checklistbank.org/dataset/{COL_DATASET_KEY}/match/nameusage"
COL_DATASET_URL = f"https://www.checklistbank.org/dataset/{COL_DATASET_KEY}"

MAJOR_RANKS = ("domain", "kingdom", "phylum", "class", "order", "family", "genus")
RANK_ORDER = {rank: index for index, rank in enumerate(MAJOR_RANKS)}
ANIMAL_ICONIC_TAXA = {
    "Actinopterygii",
    "Amphibia",
    "Animalia",
    "Arachnida",
    "Aves",
    "Insecta",
    "Mammalia",
    "Mollusca",
    "Reptilia",
}

SOURCE_FIELDS = [
    "taxon_id",
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
]

OUTPUT_FIELDS = [
    "lookup_type",
    "inat_taxon_id",
    *SOURCE_FIELDS[1:],
    "ScientificName",
    "MatchedCanonical",
    "TaxonId",
    "MatchedName",
    "CurrentName",
    "MatchType",
    "DataSourceId",
    "DataSourceTitle",
    "ClassificationPath",
    "Error",
    "taxon_level",
    "taxon_rank",
    "taxon_rank_source",
    "source_species_count",
    *MAJOR_RANKS,
    "col_status",
    "col_match_type",
    "col_usage_id",
    "col_dataset_key",
    "col_release_doi",
    "col_source_url",
    "resolver",
]


@dataclass(frozen=True)
class Taxon:
    id: str
    name: str
    rank: str


@dataclass(frozen=True)
class Resolution:
    query_name: str
    accepted: Taxon
    lineage: tuple[Taxon, ...]
    status: str
    match_type: str


def expected_kingdom(iconic_taxon_name: str) -> str | None:
    if iconic_taxon_name in ANIMAL_ICONIC_TAXA:
        return "Animalia"
    if iconic_taxon_name in {"Plantae", "Fungi", "Protozoa", "Chromista"}:
        return iconic_taxon_name
    return None


def classification_kingdom(item: dict[str, Any]) -> str:
    for taxon in item.get("classification") or []:
        if str(taxon.get("rank", "")).casefold() == "kingdom":
            return str(taxon.get("name", ""))
    return ""


def exact_query_name(item: dict[str, Any]) -> str:
    usage = item.get("usage") or {}
    name = usage.get("name") or {}
    return str(name.get("scientificName") or "")


def item_to_resolution(item: dict[str, Any], query_name: str) -> Resolution:
    usage = item.get("usage") or {}
    status = str(usage.get("status") or "")
    accepted_usage = usage.get("accepted") if status != "accepted" else None
    accepted_usage = accepted_usage if isinstance(accepted_usage, dict) else usage
    accepted_name = accepted_usage.get("name") or {}
    accepted = Taxon(
        id=str(accepted_usage.get("id") or item.get("id") or ""),
        name=str(accepted_name.get("scientificName") or exact_query_name(item)),
        rank=str(accepted_name.get("rank") or "species"),
    )

    lineage: list[Taxon] = []
    for entry in item.get("classification") or []:
        taxon = Taxon(
            id=str(entry.get("id") or ""),
            name=str(entry.get("name") or ""),
            rank=str(entry.get("rank") or ""),
        )
        if not taxon.name:
            continue
        lineage.append(taxon)
        if taxon.id == accepted.id:
            break

    if not lineage or lineage[-1].id != accepted.id:
        lineage.append(accepted)
    return Resolution(
        query_name=query_name,
        accepted=accepted,
        lineage=tuple(lineage),
        status=status,
        match_type="exact",
    )


def select_resolution(
    payload: dict[str, Any], query_name: str, kingdom: str | None
) -> Resolution | None:
    exact = [
        item
        for item in payload.get("result") or []
        if exact_query_name(item).casefold() == query_name.casefold()
    ]
    if not exact:
        return None

    def score(item: dict[str, Any]) -> tuple[int, int, int]:
        usage = item.get("usage") or {}
        name = usage.get("name") or {}
        return (
            int(kingdom is not None and classification_kingdom(item) == kingdom),
            int(str(name.get("rank", "")).casefold() == "species"),
            int(str(usage.get("status", "")).casefold() == "accepted"),
        )

    selected = max(exact, key=score)
    if kingdom and classification_kingdom(selected) != kingdom:
        return None
    return item_to_resolution(selected, query_name)


def match_payload_to_resolution(
    payload: dict[str, Any], query_name: str, kingdom: str | None
) -> Resolution | None:
    usage = payload.get("usage") or {}
    if not payload.get("match") or str(usage.get("rank", "")).casefold() != "species":
        return None

    raw_classification = usage.get("classification") or []
    classification = list(reversed(raw_classification))
    matched_kingdom = next(
        (
            str(taxon.get("name") or "")
            for taxon in classification
            if str(taxon.get("rank", "")).casefold() == "kingdom"
        ),
        "",
    )
    if kingdom and matched_kingdom != kingdom:
        return None

    lineage_items = [
            Taxon(
                id=str(taxon.get("id") or ""),
                name=str(taxon.get("name") or ""),
                rank=str(taxon.get("rank") or ""),
            )
            for taxon in classification
            if taxon.get("name")
        ]
    if str(usage.get("status", "")).casefold() == "accepted":
        lineage_items.append(
            Taxon(
                id=str(usage.get("id") or payload.get("id") or ""),
                name=str(usage.get("name") or query_name),
                rank=str(usage.get("rank") or "species"),
            )
        )
    if not lineage_items:
        return None
    lineage = tuple(lineage_items)
    return Resolution(
        query_name=query_name,
        accepted=lineage[-1],
        lineage=lineage,
        status=str(usage.get("status") or ""),
        match_type=str(payload.get("type") or "match"),
    )


def fetch_resolution(
    query_name: str,
    kingdom: str | None,
    *,
    attempts: int = 3,
    timeout: float = 30,
) -> Resolution | None:
    params = {
        "scientificName": query_name,
        "rank": "species",
        "verbose": "true",
    }
    if kingdom:
        params["kingdom"] = kingdom
    url = f"{COL_MATCH_API}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "EMI-macedonia-qgis/1.0"})
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
            return match_payload_to_resolution(payload, query_name, kingdom)
        except (OSError, TimeoutError, json.JSONDecodeError):
            if attempt + 1 == attempts:
                raise
            time.sleep(2**attempt)
    return None


def lineage_fields(lineage: Iterable[Taxon]) -> dict[str, str]:
    values = {rank: "" for rank in MAJOR_RANKS}
    for taxon in lineage:
        if taxon.rank in values:
            values[taxon.rank] = taxon.name
    return values


def species_row(source: dict[str, str], resolution: Resolution | None) -> dict[str, str]:
    original_name = source["scientific_name"].strip()
    row = {field: "" for field in OUTPUT_FIELDS}
    row.update({field: source.get(field, "") for field in SOURCE_FIELDS[1:]})
    row["lookup_type"] = "species"
    row["inat_taxon_id"] = source.get("taxon_id", "")
    row["taxon_level"] = "species"
    row["taxon_rank"] = source.get("rank") or "species"
    row["source_species_count"] = "1"
    row["col_dataset_key"] = str(COL_DATASET_KEY)
    row["col_release_doi"] = COL_DOI
    row["col_source_url"] = COL_DATASET_URL
    row["resolver"] = COL_RELEASE

    if resolution is None:
        row.update(
            {
                "ScientificName": original_name,
                "MatchedCanonical": original_name,
                "MatchedName": original_name,
                "CurrentName": original_name,
                "MatchType": "unresolved",
                "taxon_rank_source": "iNaturalist fallback",
                "col_match_type": "unresolved",
                "Error": "No exact Catalogue of Life match in the expected kingdom",
            }
        )
        return row

    classification_path = "|".join(taxon.name for taxon in resolution.lineage)
    row.update(lineage_fields(resolution.lineage))
    row.update(
        {
            "ScientificName": resolution.accepted.name,
            "MatchedCanonical": resolution.accepted.name,
            "MatchedName": resolution.query_name,
            "CurrentName": resolution.accepted.name,
            "TaxonId": resolution.accepted.id,
            "MatchType": resolution.match_type,
            "ClassificationPath": classification_path,
            "taxon_rank": resolution.accepted.rank,
            "taxon_rank_source": "Catalogue of Life",
            "col_status": resolution.status,
            "col_match_type": resolution.match_type,
            "col_usage_id": resolution.accepted.id,
        }
    )
    return row


def higher_taxon_rows(resolutions: Iterable[Resolution | None]) -> list[dict[str, str]]:
    taxa: dict[str, Taxon] = {}
    paths: dict[str, tuple[Taxon, ...]] = {}
    source_species: dict[str, set[str]] = defaultdict(set)
    for resolution in resolutions:
        if resolution is None:
            continue
        for index, taxon in enumerate(resolution.lineage):
            if taxon.rank not in MAJOR_RANKS:
                continue
            key = taxon.id or f"{taxon.rank}:{taxon.name.casefold()}"
            taxa[key] = taxon
            paths.setdefault(key, resolution.lineage[: index + 1])
            source_species[key].add(resolution.accepted.name)

    rows: list[dict[str, str]] = []
    for key, taxon in taxa.items():
        row = {field: "" for field in OUTPUT_FIELDS}
        row.update(lineage_fields(paths[key]))
        row.update(
            {
                "lookup_type": "higher_taxon",
                "scientific_name": taxon.name,
                "rank": taxon.rank,
                "iconic_taxon_name": lineage_fields(paths[key])["kingdom"],
                "ScientificName": taxon.name,
                "MatchedCanonical": taxon.name,
                "MatchedName": taxon.name,
                "CurrentName": taxon.name,
                "TaxonId": taxon.id,
                "MatchType": "classification",
                "ClassificationPath": "|".join(item.name for item in paths[key]),
                "taxon_level": "higher_taxon",
                "taxon_rank": taxon.rank,
                "taxon_rank_source": "Catalogue of Life",
                "source_species_count": str(len(source_species[key])),
                "col_status": "accepted",
                "col_match_type": "classification",
                "col_usage_id": taxon.id,
                "col_dataset_key": str(COL_DATASET_KEY),
                "col_release_doi": COL_DOI,
                "col_source_url": COL_DATASET_URL,
                "resolver": COL_RELEASE,
            }
        )
        rows.append(row)
    return rows


def read_source(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = {"taxon_id", "scientific_name", "iconic_taxon_name"}.difference(
            reader.fieldnames or []
        )
        if missing:
            raise ValueError(f"Missing required column(s): {', '.join(sorted(missing))}")
        return list(reader)


def build_lookup(
    input_path: Path,
    output_path: Path,
    *,
    resolver: Callable[[str, str | None], Resolution | None] = fetch_resolution,
    workers: int = 8,
) -> tuple[int, int, int]:
    source_rows = read_source(input_path)
    queries = [
        (row["scientific_name"].strip(), expected_kingdom(row["iconic_taxon_name"].strip()))
        for row in source_rows
    ]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        resolutions = list(executor.map(lambda query: resolver(*query), queries))

    rows = [
        *higher_taxon_rows(resolutions),
        *(species_row(source, resolution) for source, resolution in zip(source_rows, resolutions)),
    ]
    rows.sort(
        key=lambda row: (
            0 if row["lookup_type"] == "higher_taxon" else 1,
            RANK_ORDER.get(row["taxon_rank"], 99),
            row["ScientificName"].casefold(),
        )
    )
    names: set[str] = set()
    unique_rows: list[dict[str, str]] = []
    for row in rows:
        name_key = row["ScientificName"].casefold()
        if name_key in names:
            continue
        names.add(name_key)
        unique_rows.append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(unique_rows)
    resolved_count = sum(resolution is not None for resolution in resolutions)
    higher_count = sum(row["lookup_type"] == "higher_taxon" for row in unique_rows)
    return len(unique_rows), resolved_count, higher_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=8)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    total, resolved, higher = build_lookup(
        args.input, args.output, workers=max(1, args.workers)
    )
    print(
        f"Wrote {total} lookup rows to {args.output}: "
        f"{higher} higher taxa; {resolved} source species resolved by Catalogue of Life"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
