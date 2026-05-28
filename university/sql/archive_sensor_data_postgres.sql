-- This file is installed automatically after Django migrations when the
-- active database backend is PostgreSQL. SQLite skips it.

CREATE EXTENSION IF NOT EXISTS pg_cron;

CREATE OR REPLACE PROCEDURE archive_first_two_weeks_sensor_data()
LANGUAGE plpgsql
AS $$
DECLARE
    archive_from timestamptz;
    archive_to timestamptz;
    archive_file text := '/var/lib/postgresql/smart_pryaniki_sensor_archive.csv';
BEGIN
    archive_from := date_trunc('month', now());
    archive_to := archive_from + interval '14 days';

    CREATE TEMP TABLE sensor_data_to_archive ON COMMIT DROP AS
    SELECT id, sensor_id, value, created_at
    FROM university_sensordata
    WHERE created_at >= archive_from
      AND created_at < archive_to;

    EXECUTE format(
        $copy$
        COPY (
            SELECT id, sensor_id, value, created_at
            FROM sensor_data_to_archive
            ORDER BY created_at, id
        )
        TO PROGRAM %L
        WITH (FORMAT csv, HEADER false)
        $copy$,
        'tee -a ' || archive_file
    );

    DELETE FROM university_sensordata
    WHERE id IN (
        SELECT id
        FROM sensor_data_to_archive
    );
END;
$$;

SELECT cron.unschedule(jobid)
FROM cron.job
WHERE jobname = 'archive-first-two-weeks-sensor-data';

SELECT cron.schedule(
    'archive-first-two-weeks-sensor-data',
    '10 0 15 * *',
    'CALL archive_first_two_weeks_sensor_data();'
);
