import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from university.schedule_import_services import sync_schedule


class Command(BaseCommand):
    help = "Синхронизация расписания занятий с API в базу данных"

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Выполнить синхронизацию один раз и завершить работу",
        )

        parser.add_argument(
            "--interval",
            type=int,
            default=21600,
            help="Интервал синхронизации в секундах. По умолчанию 21600 = 6 часов",
        )

        parser.add_argument(
            "--days-ahead",
            type=int,
            default=14,
            help="На сколько дней вперёд загружать расписание из API",
        )

        parser.add_argument(
            "--keep-past-days",
            type=int,
            default=7,
            help="Сколько дней хранить прошедшие занятия",
        )

    def handle(self, *args, **options):
        run_once = options["once"]
        interval = options["interval"]
        days_ahead = options["days_ahead"]
        keep_past_days = options["keep_past_days"]

        self.stdout.write(
            self.style.SUCCESS(
                f"Сервис синхронизации расписания запущен. "
                f"Интервал: {interval} сек.; "
                f"загрузка на {days_ahead} дней вперёд."
            )
        )

        while True:
            self.sync_once(days_ahead, keep_past_days)

            if run_once:
                break

            time.sleep(interval)

    def sync_once(self, days_ahead, keep_past_days):
        now = timezone.localtime()
        self.stdout.write(f"\nСинхронизация расписания: {now:%d.%m.%Y %H:%M:%S}")

        stats = sync_schedule(
            days_ahead=days_ahead,
            keep_past_days=keep_past_days,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово. "
                f"Преподавателей: {stats['teachers']}; "
                f"создано: {stats['created']}; "
                f"обновлено: {stats['updated']}; "
                f"пропущено: {stats['skipped']}; "
                f"ошибок: {stats['errors']}; "
                f"отменено неактуальных: {stats['cancelled_stale']}; "
                f"удалено старых: {stats['deleted_old']}."
            )
        )