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
                f"Сервис автонастройки кабинетов запущен. "
                f"Интервал проверки: {interval} секунд."
            )
        )

        while True:
            self.check_rooms()

            if run_once:
                break

            time.sleep(interval)

    def format_value(self, value, unit):
        if value is None:
            return f"нет данных {unit}"
        return f"{value} {unit}"

    def print_microclimate_info(self, snapshot):
        temperature = snapshot.get("temperature")
        humidity = snapshot.get("humidity")
        co2 = snapshot.get("co2")
        summary = snapshot.get("summary") or {}

        temperature_summary = summary.get("temperature") or {}
        humidity_summary = summary.get("humidity") or {}
        co2_summary = summary.get("co2") or {}

        self.stdout.write("  Показания датчиков:")

        self.stdout.write(
            f"    Температура: {self.format_value(temperature, '°C')} "
            f"| норма: 18–24 °C "
            f"| статус: {temperature_summary.get('status', 'нет данных')} "
            f"| {temperature_summary.get('reason', '')}"
        )

        self.stdout.write(
            f"    Влажность: {self.format_value(humidity, '%')} "
            f"| норма: 40–60 % "
            f"| статус: {humidity_summary.get('status', 'нет данных')} "
            f"| {humidity_summary.get('reason', '')}"
        )

        self.stdout.write(
            f"    CO2: {self.format_value(co2, 'ppm')} "
            f"| норма: до 800 ppm, критично от 1000 ppm "
            f"| статус: {co2_summary.get('status', 'нет данных')} "
            f"| {co2_summary.get('reason', '')}"
        )

    def print_weather_info(self, outdoor_weather):
        if not outdoor_weather:
            self.stdout.write("  Погода снаружи: нет данных")
            return

        outdoor_temp = outdoor_weather.get("temperature")
        weather_main = outdoor_weather.get("weather_main")
        wind_speed = outdoor_weather.get("wind_speed")

        self.stdout.write("  Погода снаружи:")
        self.stdout.write(
            f"    Температура: {self.format_value(outdoor_temp, '°C')} "
            f"| проветривание запрещено ниже 16 °C"
        )
        self.stdout.write(
            f"    Погодные условия: {weather_main or 'нет данных'} "
            f"| запрещено: дождь, снег, град, гроза"
        )
        self.stdout.write(
            f"    Ветер: {self.format_value(wind_speed, 'м/с')} "
            f"| запрещено: от 10 м/с"
        )

    def check_rooms(self):
        now = timezone.localtime()

        self.stdout.write("")
        self.stdout.write("=" * 80)
        self.stdout.write(f"Проверка расписания: {now:%d.%m.%Y %H:%M:%S}")

        weather_service = WeatherService()
        outdoor_weather = weather_service.get_current_weather()

        rooms_to_prepare = get_rooms_to_prepare()

        if not rooms_to_prepare:
            self.stdout.write("Нет кабинетов для подготовки.")
            return

        for room, lesson in rooms_to_prepare:
            self.stdout.write("-" * 80)
            self.stdout.write(
                f"Кабинет: {room.name} | "
                f"Занятие: {lesson.lesson_date} {lesson.start_time}–{lesson.end_time}"
            )

            result = prepare_room_for_lesson(room, lesson, outdoor_weather)

            snapshot = result.get("snapshot") or {}
            decision = result.get("decision") or {}

            self.print_microclimate_info(snapshot)
            self.print_weather_info(outdoor_weather)

            self.stdout.write("  Решение системы:")
            self.stdout.write(
                f"    Действие: {decision.get('action', 'нет данных')}"
            )
            self.stdout.write(
                f"    Причина: {decision.get('reason', 'нет данных')}"
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"  Статус проверки: {result.get('status', 'нет данных')}"
                )
            )