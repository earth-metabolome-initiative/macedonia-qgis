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

The repository stores only the small AOI polygon and coordinate CSV. It does
not commit imagery, field photographs, QFieldSync backups, or generated
MBTiles. The QGIS project uses an online satellite layer as the source for a
QFieldSync offline export. Generate a bounded offline basemap only when
packaging the field project, then prune it to the AOI with
`scripts/prune_mbtiles_to_polygon.py` as documented in `CONTRIB.md`.

## Taxonomic workflow

The default regional iNaturalist query uses the buffered field bounds
`41.981,20.787,42.053,20.892` (south, west, north, east):

```bash
uv sync
uv run python scripts/fetch_inaturalist_species.py
```

The default output is
`data/inaturalist/macedonia_species_observations.csv`. To rebuild a richer
lookup with Global Names resolution and higher taxa, follow the commands in
`CONTRIB.md`.

Build the compact direct lookup with:

```bash
uv run python scripts/build_lightweight_species_lookup.py
ogr2ogr -f GPKG qgis/macedonia/species_list.gpkg \
  qgis/macedonia/species_list.csv -nln species_list -nlt NONE \
  -overwrite -oo EMPTY_STRING_AS_NULL=YES
```

## Checks

```bash
uv run ruff check .
uv run pytest
```
