from pathlib import Path
import logging

from django.conf import settings
from django.db import connection
from django.db.utils import DatabaseError


logger = logging.getLogger(__name__)


def install_postgres_archive_job():
    if connection.vendor != "postgresql":
        return

    if not getattr(settings, "INSTALL_POSTGRES_ARCHIVE_JOB", True):
        return

    if not _pg_cron_is_available():
        logger.warning(
            "pg_cron"
        )
        return

    sql_path = Path(__file__).resolve().parent / "sql" / "archive_sensor_data_postgres.sql"
    sql = sql_path.read_text(encoding="utf-8")

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
    except DatabaseError as exc:
        logger.warning("Could not install PostgreSQL sensor data archive job: %s", exc)


def _pg_cron_is_available():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_available_extensions
                WHERE name = 'pg_cron'
            )
            """
        )
        return cursor.fetchone()[0]
