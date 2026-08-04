-- Idempotent database safeguards for the QField observations layer.
-- Run after creating or rebuilding an empty observations.gpkg schema.

CREATE UNIQUE INDEX IF NOT EXISTS observations_sample_id_unique
ON observations(sample_id);

CREATE UNIQUE INDEX IF NOT EXISTS observations_uuid_qfield_unique
ON observations(uuid_qfield);

DROP TRIGGER IF EXISTS observations_validate_identity_insert;
CREATE TRIGGER observations_validate_identity_insert
BEFORE INSERT ON observations
WHEN
    NEW.sample_id IS NULL
    OR trim(NEW.sample_id) <> NEW.sample_id
    OR length(NEW.sample_id) <> 11
    OR substr(NEW.sample_id, 1, 5) <> 'mcdn_'
    OR substr(NEW.sample_id, 6, 6) NOT GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]'
    OR NEW.uuid_qfield IS NULL
    OR length(NEW.uuid_qfield) <> 36
    OR substr(NEW.uuid_qfield, 9, 1) <> '-'
    OR substr(NEW.uuid_qfield, 14, 1) <> '-'
    OR substr(NEW.uuid_qfield, 19, 1) <> '-'
    OR substr(NEW.uuid_qfield, 24, 1) <> '-'
    OR length(replace(NEW.uuid_qfield, '-', '')) <> 32
    OR lower(replace(NEW.uuid_qfield, '-', '')) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'observation requires a unique mcdn_###### sample ID and valid UUID');
END;

DROP TRIGGER IF EXISTS observations_validate_identity_update;
CREATE TRIGGER observations_validate_identity_update
BEFORE UPDATE OF sample_id, uuid_qfield ON observations
WHEN
    NEW.sample_id IS NULL
    OR trim(NEW.sample_id) <> NEW.sample_id
    OR length(NEW.sample_id) <> 11
    OR substr(NEW.sample_id, 1, 5) <> 'mcdn_'
    OR substr(NEW.sample_id, 6, 6) NOT GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]'
    OR NEW.uuid_qfield IS NULL
    OR length(NEW.uuid_qfield) <> 36
    OR substr(NEW.uuid_qfield, 9, 1) <> '-'
    OR substr(NEW.uuid_qfield, 14, 1) <> '-'
    OR substr(NEW.uuid_qfield, 19, 1) <> '-'
    OR substr(NEW.uuid_qfield, 24, 1) <> '-'
    OR length(replace(NEW.uuid_qfield, '-', '')) <> 32
    OR lower(replace(NEW.uuid_qfield, '-', '')) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'observation requires a unique mcdn_###### sample ID and valid UUID');
END;
