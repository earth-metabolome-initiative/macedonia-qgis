# Contributing to the Macedonia QField project

## Updating the field footprint

The project uses:

- `qgis/macedonia/optimized_maps/Macedonia-EMI.kml`
- `qgis/macedonia/optimized_maps/Macedonia-EMI.gpkg`

After changing the KML, regenerate the GeoPackage without changing its layer
name:

```bash
ogr2ogr -f GPKG \
  qgis/macedonia/optimized_maps/Macedonia-EMI.gpkg \
  qgis/macedonia/optimized_maps/Macedonia-EMI.kml \
  -nln Macedonia_EMI \
  -overwrite
```

Open `qgis/macedonia/macedonia.qgs` and verify that the polygon and the seven
locations in `data/field_locations.csv` cover the intended daily routes.

## Building the taxon lookup

Fetch the small field-region list:

```bash
uv run python scripts/fetch_inaturalist_species.py
uv run python scripts/build_lightweight_species_lookup.py
```

For a resolved lookup including higher taxa:

```bash
uv run python scripts/resolve_taxa.py \
  --input data/inaturalist/macedonia_species_observations.csv \
  --header scientific_name --dedupe-input --force

uv run python scripts/build_higher_taxa_input.py \
  --input data/inaturalist/macedonia_species_observations_resolved.csv \
  --output data/inaturalist/macedonia_higher_taxa.csv

uv run python scripts/resolve_taxa.py \
  --input data/inaturalist/macedonia_higher_taxa.csv \
  --header scientific_name --dedupe-input --force

uv run python scripts/combine_species_and_higher_taxa.py \
  --species data/inaturalist/macedonia_species_observations_resolved.csv \
  --higher-taxa data/inaturalist/macedonia_higher_taxa_resolved.csv \
  --output qgis/macedonia/species_list.csv

ogr2ogr -f GPKG qgis/macedonia/species_list.gpkg \
  qgis/macedonia/species_list.csv -nln species_list -nlt NONE \
  -overwrite -oo EMPTY_STRING_AS_NULL=YES
```

## Exporting a lightweight offline basemap

In QGIS, use `Project > Properties > QField` and keep the AOI at
`41.981,20.787,42.053,20.892`. Start with zoom levels 14–17 and reduce the
maximum zoom if the export is too large. Export to:

```text
/Users/pma/QField/export/macedonia
```

Prune the rectangular QFieldSync output before deployment:

```bash
python3 scripts/prune_mbtiles_to_polygon.py \
  --mbtiles /Users/pma/QField/export/macedonia/basemap.mbtiles \
  --polygon qgis/macedonia/optimized_maps/Macedonia-EMI.kml \
  --output qgis/macedonia/optimized_maps/basemap.mbtiles \
  --buffer-tiles 1 --force
```

The generated basemap is intentionally ignored by Git. Validate it locally in
QGIS/QField, and transfer it through the field packaging workflow rather than
repository history.

## Release checklist

1. Confirm the project opens without broken vector layers.
2. Create a test feature whose ID matches `mcdn_######`.
3. Confirm all six attachment paths use `DCIM/macedonia/`.
4. Confirm collector, subject, and species relations populate correctly.
5. Test collection with a person who has no ORCID or iNaturalist username.
6. Run `uv run ruff check .` and `uv run pytest`.
7. Check repository size before committing; do not add field photos, sync
   backups, or generated basemap tiles.
