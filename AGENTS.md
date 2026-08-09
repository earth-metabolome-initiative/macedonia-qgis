# Agent notes

Read `TEMPLATE_NOTES.md` before using this repository as a template.

- Preserve the `mcdn_######` identifier contract and `DCIM/macedonia/` paths.
- This is now an active field project. Preserve every existing record in
  `observations.gpkg`; never empty, replace, or rebuild it from a blank template.
  When deriving a new mission template, create a separate empty schema copy
  instead of copying Macedonia observations.
- Do not add field imagery, `.qfieldsync`, backup files, or generated MBTiles.
- Keep `docs/original_field_email.txt` verbatim.
- Update `TEMPLATE_NOTES.md` whenever a reusable improvement is made, including
  the reason and any migration caveat for the next project.
- Run the Python tests and scan for stale mission names/prefixes before handoff.
