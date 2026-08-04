# Macedonia QField project

Project slug: `macedonia`

Sample identifier prefix: `mcdn_`

This repository contains the QGIS/QField project for the EMI field mission in
the Šar Planina / Popova Shapka area of North Macedonia. It is templated from
the Manaslu project while excluding Manaslu observations, photographs,
QFieldSync state, and regional taxonomic data.

## Main files

- QGIS/QField project: `qgis/macedonia/macedonia.qgs`
- Empty active observation layer: `qgis/macedonia/observations.gpkg`
- Regional species lookup: `qgis/macedonia/species_list.gpkg`
- Collector lookup: `qgis/macedonia/collector_list.gpkg`
- Observation subject lookup: `qgis/macedonia/observation_subject.gpkg`
- Field-area polygon: `qgis/macedonia/optimized_maps/Macedonia-EMI.gpkg`
- Locally generated offline satellite map (ignored by Git):
  `qgis/macedonia/optimized_maps/macedonia_google_satellite_z18.tif`
- Orientation coordinates: `data/field_locations.csv`
- Original field email: `docs/original_field_email.txt`
- Template handoff notes: `TEMPLATE_NOTES.md`

## QField conventions

- Sample identifiers must match `mcdn_######`.
- QField image paths are based only on the sample identifier, for example
  `DCIM/macedonia/mcdn_001234_01.jpg`.
- Taxon names populate lookup/display fields but are not used in image names.
- `uuid_qfield` is generated with QGIS `uuid('WithoutBraces')`.
- ORCID and iNaturalist username fields are optional because students and
  external collaborators may not have them.

## Lightweight map strategy

The local project uses a buffered Google Satellite zoom-18 GeoTIFF for sharp
offline orientation at every map scale. Its nominal ground resolution near the
field area is about 0.44 m/pixel. The generated raster is deliberately ignored
by Git; only its QGIS configuration, reproducible builder, and provenance are
versioned. The live online satellite layer remains available as a fallback
when connected.

Field photographs, QFieldSync backups, and generated MBTiles remain excluded.
See `CONTRIB.md` for source provenance, rebuilding, and deployment checks.

## Taxonomic workflow

The default regional iNaturalist query uses the buffered field bounds
`41.981,20.787,42.053,20.892` (south, west, north, east):

```bash
uv sync
uv run python scripts/fetch_inaturalist_species.py
```

The default output is
`data/inaturalist/macedonia_species_observations.csv`. This source query does
not restrict iconic taxa, so locally observed plants, animals, fungi, and
protists are retained.

Resolve the names and classifications with the pinned Catalogue of Life
2026-07-17 XR release, then build the compact field lookup:

```bash
uv run python scripts/build_col_taxon_lookup.py
ogr2ogr -f GPKG qgis/macedonia/species_list.gpkg \
  qgis/macedonia/species_list.csv -nln species_list -nlt NONE \
  -overwrite -oo EMPTY_STRING_AS_NULL=YES
```

The field list contains every regional species plus its Catalogue of Life
domain, kingdom, phylum, class, order, family, and genus. The pinned release is
ChecklistBank dataset `315834`, DOI `10.48580/dgykv`. An unmatched source name
is retained explicitly as an iNaturalist fallback instead of being discarded
or silently assigned to a fuzzy match.

## Checks

```bash
uv run ruff check .
uv run pytest
```
