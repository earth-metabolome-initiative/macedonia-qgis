# `mcdn_000100` duplicate-label quarantine

Status: **quarantined and unresolved**, documented 2026-08-13.

Two distinct field samples were given the printed identifier `mcdn_000100`.
They must not be collapsed into one observation, and the held-out observation
must not be assigned a replacement identifier until its physical custody is
resolved.

| Evidence | Manu sample | Jovana sample |
| --- | --- | --- |
| Collector | Emmanuel Defossez | Jovana Angelova |
| Material | Aboveground Bryophyta | Whole *Hypericum perforatum* organism |
| Field record time | 2026-08-10 13:22:02 local | 2026-08-10 12:32:46 local |
| Coordinates | 42.18734913 N, 21.12764786 E | 42.18738729 N, 21.12758783 E |
| UUID | `67c6df7b-7538-438b-ae4c-d5881a98bd35` | `6cb125a1-8496-427d-a84b-fd3f4dd30260` |
| Photo evidence | Bryophyte; GPS time about 13:22 local | *Hypericum*; GPS time about 12:43 local |
| Current row status | Retained in active GeoPackage | Held only in Jovana's device export |

Both sample-code photographs visibly show `000100`, so this is a physical
duplicate-label event rather than only a database collision. No downstream
inventory, shipping, storage, extraction, or analytical record for this code
was found in the EMI workspace.

## Verified photo-set locations

The digital photo collision was separated on 2026-08-13 and verified by SHA-256
against the two previously inspected sets:

- `qgis/macedonia/DCIM/macedonia/mcdn_000100_01.jpg` through `_05.jpg` are
  Manu's bryophyte photo set. These are the canonical paths referenced by the
  active Manu row, so QGIS now displays the correct attachments for that row.
- `qgis/macedonia/DCIM/mcdn_000100_jovana/mcdn_000100_01.jpg` through `_05.jpg`
  are Jovana's *Hypericum* photo set. This quarantine directory is deliberately
  outside `DCIM/macedonia/` and is not referenced by the active database.
- The former repository-root copies `qgis/mcdn_000100_01.jpg` through `_05.jpg`
  were Manu's set and were moved into their canonical directory; they no longer
  exist at the old location.

Neither current photo set may be overwritten, renamed, or deleted while the
case is unresolved. Jovana's quarantined folder must not be changed into a
normal attachment path unless her held-out observation receives a reviewed,
unique identity and the physical chain of custody is documented.

## Quarantine decision

- The active observation database contains 206 unique observations and keeps
  Manu's existing `mcdn_000100` row unchanged.
- Jovana's colliding row is not present in the active database. Its authoritative
  source remains `data/macedonia_backup/jovana/data.gpkg`.
- Do not reuse Jovana's UUID or upload her row under `mcdn_000100`.
- Do not assign the proposed rescue ID `mcdn_999997` unless the project owner
  explicitly reopens the decision after checking physical custody.
- Treat every physical or analytical item labelled `mcdn_000100` as
  quarantined until its contents identify it as bryophyte or *Hypericum* and
  its current storage or processing history is recorded.

If both physical samples are found, create a reviewed accession/collision
record that preserves the printed field code, collector, UUID, photo set, new
unique database identifier, and complete chain of custody. If Jovana's sample
cannot be found, retain her device observation and photographs as evidence and
record the physical sample as not located; do not infer that it became Manu's
sample.

## QFieldCloud operational warning

The 18 non-conflicting rescued observations were appended to the local
GeoPackage. Before any Cloud pull or ordinary synchronization, QFieldSync must
upload `qgis/macedonia/observations.gpkg` by selecting **Local file**. Selecting
**Cloud file** first can replace the rescued database with the older Cloud
copy. This quarantine does not authorize uploading Jovana's colliding row.
