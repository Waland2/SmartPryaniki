from django.core.management.base import BaseCommand
from university.models import TeacherNotification


class Command(BaseCommand):
    help = "Удаляет все уведомления"

    def handle(self, *args, **kwargs):
        count, _ = TeacherNotification.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(f"Удалено уведомлений: {count}")
        )