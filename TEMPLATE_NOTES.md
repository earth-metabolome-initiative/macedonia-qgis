# Template handoff notes

This project was derived from `/Users/pma/git_repos/EMI/manaslu-qgis` on
2026-08-03. Field collection has started, so its observation store is active
mission data and must never be emptied. Use the documented configuration as a
baseline for the next EMI project, but create a separate empty schema copy.

## Improvements carried forward

- The observation form, relations, attachment naming, automatic UUID,
  coordinate defaults, taxon resolution scripts, iNaturalist fetcher, tests,
  and polygon-aware MBTiles pruning logic are retained.
- Mission records, photos, `.qfieldsync` state, backups, and country-specific
  Manaslu/Nepal taxon outputs are deliberately excluded.
- New observation stores begin empty. Never copy Macedonia's active field
  observations into a new mission template, and never empty the Macedonia
  store while deriving that template.
- ORCID and iNaturalist username are optional so students and external
  collaborators without accounts can collect records.
- The collector lookup now stores email alongside name, institution, ORCID,
  and normalized `@username` iNaturalist handles, and its CSV is tested against
  the GeoPackage to prevent roster drift. This preserves all supplied contact
  details while retaining `fullname` as the observation relation key. The
  migration caveat is to preserve existing full-name spellings when field data
  already references them, then repackage/re-download QField so devices receive
  the expanded lookup schema; existing observation metadata is not
  retroactively rewritten when contact details change.
- The observation preview now uses the current `taxon_name_final` field rather
  than the stale `TaxonomicName` expression inherited from Manaslu.
- A reproducible builder and exact source provenance are versioned for the
  offline satellite background, while the generated GeoTIFF itself stays
  ignored. Field photographs, QFieldSync state, generated rasters, and
  generated MBTiles remain excluded.
- `build_lightweight_species_lookup.py` provides a compact, no-resolver
  fallback that maps iNaturalist scientific names and IDs into the three QField
  relation fields. Use the full resolver workflow when provenance-quality
  canonicalization or higher taxa are required.
- Original stakeholder location text is retained verbatim under `docs/` so
  later geographic interpretations remain auditable.
- `tests/test_project_template.py` guards the prefix, attachment paths, active
  observation identities and picture-path consistency, ignored offline-raster
  reference, absence of generated MBTiles, and containment of all supplied
  coordinates within the AOI.
- The sample-ID tab is always visible. Do not make its visibility depend on
  attachment fields: copied or restored attachment values can otherwise hide
  the scanner before a valid sample ID has been entered.
- Observation duplication resets all attributes to their defaults, including
  the sample ID, UUID, attachment paths, coordinates, and timestamp. This
  prevents a copied feature from silently inheriting another sample's identity
  or metadata.
- Picture fields use semantic names: `picture_environment`,
  `picture_full_organism`, `picture_detail`, `picture_sampled_part`,
  `picture_sample_code`, and `picture_free`. Their `_01.jpg` through `_06.jpg`
  attachment numbering remains stable, and the first five remain required. The
  migration caveat is that renaming GeoPackage columns changes the offline
  schema: upload the updated project and replace/re-download existing QField
  copies before collecting or syncing further edits; old-schema deltas must not
  be merged into the renamed project.
- `observations.gpkg` enforces valid, unique `mcdn_######` sample IDs and valid,
  unique UUIDs with database indexes and triggers in addition to QGIS form
  constraints. Reapply `scripts/harden_observations.sql` after rebuilding the
  GeoPackage schema. The migration caveat is that invalid offline deltas will
  now fail explicitly instead of creating malformed records; test a full
  QFieldCloud download/edit/push cycle and resolve rejected legacy deltas
  before field deployment.
- The offline taxon lookup now resolves regional iNaturalist names against the
  pinned Catalogue of Life 2026-07-17 XR release and includes domain, kingdom,
  phylum, class, order, family, and genus choices. The source fetch remains
  unfiltered by iconic taxon so animals, fungi, protists, and plants are all
  retained. Pinning a published CoL release makes rebuilds reproducible; for a
  future project, deliberately update the dataset key, release label, DOI, and
  tests together after checking coverage. Never substitute the mutable CoL
  working dataset without documenting that migration caveat.
- QField displays the scientific name together with its rank and fetches the
  complete lightweight lookup. `build_col_taxon_lookup.py` keeps unmatched
  source species as explicit fallbacks rather than silently accepting a
  higher-rank or wrong-kingdom match.
- The online basemap uses the QFieldCloud `no_action` layer action so raw
  repository deployments retain direct access to the tile service. The
  `remove` action caused QFieldCloud packaging to strip the only background
  layer, while QFieldSync's "use current project as template" conversion
  silently corrected it. Existing projects must change the basemap cloud
  action to direct access, upload the project again, and re-download it on
  devices; this does not create an offline basemap.
- The offline background is a locally generated Google Satellite zoom-18 mosaic
  stored as a tiled, JPEG-compressed GeoTIFF with internal overviews. It replaces the 10 m
  Sentinel-2 experiment, whose pixelation was inadequate for field navigation,
  and avoids QFieldCloud basemap generation, which the server disables. Its
  nominal ground resolution here is about 0.44 m/pixel and the layer has no scale
  visibility limit, so the overview pyramid supports every zoom level. The
  migration caveat is that the tile endpoint and imagery can change, rebuilding
  requires network access, redistribution terms must be reviewed, and the
  generated TIFF must remain ignored by Git and be transferred separately by
  the QField packaging/deployment workflow. Future AOIs must update the raster,
  metadata, relative layer reference, and tests together.
- QField automatically pushes edits every 15 minutes, and the repository
  includes a read-only attachment auditor for checking observation references
  against a QFieldCloud inventory or an independently downloaded archive. The
  intended on-demand attachment download mode is server-side and is not stored
  in the QGIS project; the current self-hosted deployment does not expose that
  feature, so all-device attachment downloads remain expected until the server
  is deliberately upgraded and tested. Automatic pushing and audits remain
  useful independently. Never delete a device-local original merely because a
  Cloud file listing contains its name.
- `merge_qfield_device_export.py` provides an append-only, dry-run-first rescue
  path for exports from devices that cannot synchronize. It auto-detects the
  hashed QFieldCloud observations table, rejects identity/content conflicts,
  verifies and collision-checks attachments, validates a temporary candidate,
  refuses a live QGIS database even for dry runs, and uses atomic replacement only with
  `--apply`. The migration caveat is that schema changes or legitimate edits to
  existing observations are intentionally not auto-merged; preserve every
  original per-device export outside Git and resolve reported conflicts before
  changing the mission database. For reviewed same-ID-and-UUID attribute
  differences, `--keep-target-existing` can explicitly preserve the newer base
  version while appending only absent rows. A rescue append is a local file
  change, not a QFieldCloud delta: freeze synchronization, start from the latest
  Cloud file, merge all exports, then explicitly select **Local file** for the
  observation GeoPackage in QFieldSync before any further pull. Otherwise the
  older Cloud file can replace the rescued rows.

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
