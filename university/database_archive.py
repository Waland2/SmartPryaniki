from pathlib import Path

from django.db import connection


def install_postgres_archive_job():
    if connection.vendor != "postgresql":
        return

    sql_path = Path(__file__).resolve().parent / "sql" / "archive_sensor_data_postgres.sql"
    sql = sql_path.read_text(encoding="utf-8")

    with connection.cursor() as cursor:
        cursor.execute(sql)
