# Template handoff notes

This project was derived from `/Users/pma/git_repos/EMI/manaslu-qgis` on
2026-08-03. Use it as the newer baseline for the next EMI QField project.

## Improvements carried forward

- The observation form, relations, attachment naming, automatic UUID,
  coordinate defaults, taxon resolution scripts, iNaturalist fetcher, tests,
  and polygon-aware MBTiles pruning logic are retained.
- Mission records, photos, `.qfieldsync` state, backups, and country-specific
  Manaslu/Nepal taxon outputs are deliberately excluded.
- New observation stores begin empty. Never copy observations from a previous
  mission into a new template.
- ORCID and iNaturalist username are optional so students and external
  collaborators without accounts can collect records.
- The observation preview now uses the current `taxon_name_final` field rather
  than the stale `TaxonomicName` expression inherited from Manaslu.
- Only a buffered AOI, orientation-point CSV, and regional species lookup are
  versioned. Offline imagery is generated at packaging time and ignored.
- `build_lightweight_species_lookup.py` provides a compact, no-resolver
  fallback that maps iNaturalist scientific names and IDs into the three QField
  relation fields. Use the full resolver workflow when provenance-quality
  canonicalization or higher taxa are required.
- Original stakeholder location text is retained verbatim under `docs/` so
  later geographic interpretations remain auditable.
- `tests/test_project_template.py` guards the prefix, attachment paths, empty
  observation store, absence of a committed-basemap reference, and containment
  of all supplied coordinates within the AOI.

## New-project substitution checklist

Replace all of the following together: repository/project slug, QGIS project
title and layer IDs, sample prefix and regex, `DCIM/<project>/` attachment
paths, polygon filename/layer name, project extents, QFieldSync AOI/export
directory, iNaturalist defaults, collector list, README/CONTRIB examples, and
RO-Crate labels. Then run a case-insensitive search for the prior mission name,
prefix, country, coordinates, and absolute paths.

Do not mechanically copy binary GeoPackages that contain observations. Create
an empty schema copy and verify its feature count is zero. Do not copy a prior
country's species database; fetch the new AOI or country and rebuild it.

## Known follow-ups

- The field dates were supplied as 7–11 August without a year; do not invent
  one in metadata.
- Dr. Danijela Mišić's ORCID and iNaturalist username were not supplied.
- Student names and identifiers were not supplied; the collector list contains
  a generic `Student participant` option.
- The two Wikiloc tracks are referenced in the original email but their GPX
  geometry is not vendored. Add verified GPX tracks only if licensing and
  offline-size requirements permit it.
- Always inspect the source repository's dirty state. Manaslu contained field
  photos and sync artifacts that were not appropriate template inputs.
