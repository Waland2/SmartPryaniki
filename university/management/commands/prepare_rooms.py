import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from university.preparation_services import prepare_room_for_lesson
from university.schedule_services import get_rooms_to_prepare
from university.weather_services import WeatherService


class Command(BaseCommand):
    help = "Постоянная автоматическая подготовка аудиторий перед занятиями"

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Выполнить проверку один раз и завершить работу",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Интервал проверки в секундах. По умолчанию 60 секунд",
        )

    def handle(self, *args, **options):
        run_once = options["once"]
        interval = options["interval"]

        self.stdout.write(
            self.style.SUCCESS(
                f"Сервис подготовки кабинетов запущен. Интервал проверки: {interval} сек."
            )
        )

        while True:
            self.check_rooms()

            if run_once:
                break

            time.sleep(interval)

    def check_rooms(self):
        now = timezone.localtime()
        self.stdout.write(f"\nПроверка расписания: {now:%d.%m.%Y %H:%M:%S}")

        weather_service = WeatherService()
        outdoor_weather = weather_service.get_current_weather()

        rooms_to_prepare = get_rooms_to_prepare()

        if not rooms_to_prepare:
            self.stdout.write("Нет кабинетов для подготовки.")
            return

        for room, lesson in rooms_to_prepare:
            result = prepare_room_for_lesson(room, lesson, outdoor_weather)

            self.stdout.write(
                f"{room.name} | {lesson.lesson_date} {lesson.start_time} | {result['status']}"
            )
