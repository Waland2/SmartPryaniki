from django.apps import AppConfig
from django.db.models.signals import post_migrate


class UniversityConfig(AppConfig):
    name = 'university'

    def ready(self):
        post_migrate.connect(
            install_archive_job_after_migrate,
            sender=self,
            dispatch_uid="university.install_archive_job_after_migrate",
        )


def install_archive_job_after_migrate(sender, **kwargs):
    from .database_archive import install_postgres_archive_job

    install_postgres_archive_job()
