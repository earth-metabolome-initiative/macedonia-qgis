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
```

The regional fetch is deliberately not filtered by iconic taxon, so all
observed kingdoms remain candidates. Resolve them with Catalogue of Life and
include major higher ranks in the QField lookup:

```bash
uv run python scripts/build_col_taxon_lookup.py

ogr2ogr -f GPKG qgis/macedonia/species_list.gpkg \
  qgis/macedonia/species_list.csv -nln species_list -nlt NONE \
  -overwrite -oo EMPTY_STRING_AS_NULL=YES
```

The resolver is pinned to the published Catalogue of Life 2026-07-17 XR
release (ChecklistBank dataset `315834`, DOI `10.48580/dgykv`) rather than the
mutable CoL working project. Review rows whose `col_match_type` is
`unresolved`; they remain usable under their iNaturalist name but have no CoL
identifier or classification. Do not accept a genus-level CoL match as a
species resolution.

## Rebuilding the lightweight offline satellite map

The locally generated offline background is a Google Satellite zoom-18 mosaic.
At the field area's latitude its nominal ground resolution is about 0.44
m/pixel. The raster is ignored by Git. Exact endpoint, tile range, count,
requested bounds, and attribution are stored beside it in
`qgis/macedonia/optimized_maps/macedonia_google_satellite_z18.metadata.txt`.
Review the provider's terms before redistributing the imagery.

Rebuild the JPEG-compressed tiled GeoTIFF and its internal overviews with:

```bash
python3 scripts/build_google_offline_basemap.py \
  --output qgis/macedonia/optimized_maps/macedonia_google_satellite_z18.tif \
  --force
```

The buffered raster extent is `20.777,41.971,20.902,42.063`. It is deliberately
larger than the field AOI, remains visible at every map scale, and uses internal
overviews for fast zoomed-out rendering. Rebuilding requires network access;
the provider can change the imagery or endpoint. The raster is transferred by
the QField packaging/deployment workflow, never through Git or Git LFS.

The online satellite layer remains underneath it as a connected fallback.
Generated MBTiles are still prohibited. If another high-resolution source is
used for a future mission, keep generated MBTiles out of repository history and
prune them with `scripts/prune_mbtiles_to_polygon.py` before deployment.

## Protecting attachments with on-demand downloads

The project automatically pushes local changes to QFieldCloud every 15 minutes
while QField is running and connected. On the active QFieldCloud project,
enable **Settings → On demand attachment files download**. This keeps a photo
on its collecting device and in QFieldCloud without automatically copying every
photo to every other device. A different device can still open and download an
attachment when it is online.

Treat this as a bandwidth setting, not as a backup. Before enabling it on an
existing deployment:

1. On every collecting device, open QField, push/synchronize, and wait for a
   successful upload. Do not uninstall QField or clear its project data.
2. Export the active project's QFieldCloud file inventory as JSON and audit it
   against the live observation database:

   ```bash
   python3 scripts/audit_observation_attachments.py \
     --database qgis/macedonia/observations.gpkg \
     --cloud-files-json /path/to/qfieldcloud-files.json
   ```

3. Keep an independent downloaded copy of `DCIM/macedonia/` outside this Git
   repository. Verify that copy and write a checksum manifest:

   ```bash
   python3 scripts/audit_observation_attachments.py \
     --database qgis/macedonia/observations.gpkg \
     --attachments-root /path/to/archive-root \
     --manifest-out /path/to/archive-manifest.json
   ```

The archive root must contain `DCIM/macedonia/`. The audit fails on missing or
empty required references, unexpected names, duplicate references, missing
inventory files, or zero-byte files. Only a successful Cloud audit plus a
successful independent-archive audit is grounds to remove a local copy, and
field-device originals should normally be retained for the mission.

## Recovering a QField device export

Keep every phone export in its own directory outside the Git repository. Never
combine or overwrite phone archives. A preferred export has this structure:

```text
phone-or-collector-name/
├── data.gpkg
├── deltafile.json
└── DCIM/
    └── macedonia/
        └── mcdn_######_01.jpg
```

Copying the phone's `DCIM` directory directly into the project is unnecessary:
the rescue tool reads it from the device export, checks for filename/content
collisions, and installs only attachments belonging to new observations. The
project's `DCIM` directory remains ignored by Git.

Close QGIS, then perform the default read-only dry run:

```bash
python3 scripts/merge_qfield_device_export.py \
  /path/to/phone-or-collector-name
```

The tool auto-detects QFieldCloud's hashed observation table. It requires the
same `mcdn_######` and UUID identity, schema, geometry, attachment naming, and
media files as the main project. Identical records are skipped. A reused sample
ID, reused UUID, changed existing record, missing attachment, truncated media,
or same attachment name with different content stops the operation without
changing the project.

After reviewing the proposed IDs, apply the same command explicitly:

```bash
python3 scripts/merge_qfield_device_export.py \
  /path/to/phone-or-collector-name \
  --apply \
  --report-out /path/to/external-recovery-log/phone-or-collector-name.json
```

Both dry runs and applied merges refuse to start while QGIS has the target open;
copying a live SQLite file can capture an inconsistent in-progress index. The
merge is append-only. It builds and fully validates a temporary candidate,
verifies that the main database did not change during the run, installs missing
attachments without overwriting different content, and atomically replaces the
main GeoPackage. Process one phone at a time, commit the validated
`observations.gpkg` after each phone, and retain the original phone export and
external JSON report until the entire mission has been reconciled. Reports and
phone backups must not be committed.

For legacy exports whose pictures were already copied into the project's
ignored `DCIM` directory, the default fallback uses that directory. A separate
photo source can be supplied explicitly with `--source-attachments-root`.

## Release checklist

1. Confirm the project opens without broken vector layers.
2. Create a test feature whose ID matches `mcdn_######`.
3. Confirm all six attachment paths use `DCIM/macedonia/`.
4. Confirm collector, subject, and species relations populate correctly.
5. Test collection with a person who has no ORCID or iNaturalist username.
6. Run `uv run ruff check .` and `uv run pytest`.
7. Test a QFieldCloud download in airplane mode and confirm the Google z18
   layer remains visible when the online satellite layer cannot connect.
8. Check repository size before committing; do not add field photos, sync
   backups, or generated MBTiles.
9. Run the attachment audit against the current QFieldCloud inventory and the
   independent archive; both must pass before retiring any device-local copy.
