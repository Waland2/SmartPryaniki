from datetime import date, timedelta

from django.core.management.base import BaseCommand

from university.notification_services import generate_environment_notifications_for_date


class Command(BaseCommand):
    help = "Генерирует уведомления преподавателям о подготовке кабинета"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days-ahead",
            type=int,
            default=1,
            help="На сколько дней вперед создавать уведомления",
        )

    def handle(self, *args, **options):
        days_ahead = options["days_ahead"]
        target_date = date.today() + timedelta(days=days_ahead)

        created = generate_environment_notifications_for_date(target_date)
        self.stdout.write(
            self.style.SUCCESS(
                f"Создано уведомлений: {created} на дату {target_date}"
            )
        )
