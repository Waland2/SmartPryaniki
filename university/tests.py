from datetime import date, time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from university.climate_rules import is_bad_weather_for_ventilation
from university.models import (
    ClimateActionLog,
    Conditioner,
    Room,
    RoomLesson,
    Sensor,
    SensorType,
)
from university.preparation_services import choose_climate_action, prepare_room_for_lesson
from university.schedule_services import is_time_to_prepare


class ClimateRulesTests(TestCase):
    def test_bad_weather_when_outdoor_too_cold(self):
        self.assertTrue(
            is_bad_weather_for_ventilation(
                {
                    "temperature": 10,
                    "weather_main": "clear",
                    "wind_speed": 1,
                }
            )
        )

    def test_good_weather_for_ventilation(self):
        self.assertFalse(
            is_bad_weather_for_ventilation(
                {
                    "temperature": 20,
                    "weather_main": "clear",
                    "wind_speed": 3,
                }
            )
        )

    def test_bad_weather_when_raining(self):
        self.assertTrue(
            is_bad_weather_for_ventilation(
                {
                    "temperature": 20,
                    "weather_main": "rain",
                    "wind_speed": 2,
                }
            )
        )


class PreparationDecisionTests(TestCase):
    def test_choose_ventilation_when_hot_and_outside_cooler(self):
        snapshot = {
            "temperature": 28,
            "summary": {
                "too_hot": True,
                "too_cold": False,
                "needs_ventilation": False,
            },
        }
        outdoor_weather = {
            "temperature": 20,
            "weather_main": "clear",
            "wind_speed": 2,
        }

        decision = choose_climate_action(snapshot, outdoor_weather)
        self.assertEqual(decision["action"], "ventilation")

    def test_choose_cooling_when_hot_but_weather_bad(self):
        snapshot = {
            "temperature": 28,
            "summary": {
                "too_hot": True,
                "too_cold": False,
                "needs_ventilation": False,
            },
        }
        outdoor_weather = {
            "temperature": 12,
            "weather_main": "rain",
            "wind_speed": 2,
        }

        decision = choose_climate_action(snapshot, outdoor_weather)
        self.assertEqual(decision["action"], "conditioner_cool")

    def test_choose_heat_when_cold_and_no_ventilation(self):
        snapshot = {
            "temperature": 16,
            "summary": {
                "too_hot": False,
                "too_cold": True,
                "needs_ventilation": False,
            },
        }
        outdoor_weather = {
            "temperature": 5,
            "weather_main": "clear",
            "wind_speed": 2,
        }

        decision = choose_climate_action(snapshot, outdoor_weather)
        self.assertEqual(decision["action"], "conditioner_heat")

    def test_choose_none_when_only_co2_high_and_weather_bad(self):
        snapshot = {
            "temperature": 22,
            "summary": {
                "too_hot": False,
                "too_cold": False,
                "needs_ventilation": True,
            },
        }
        outdoor_weather = {
            "temperature": 8,
            "weather_main": "snow",
            "wind_speed": 8,
        }

        decision = choose_climate_action(snapshot, outdoor_weather)
        self.assertEqual(decision["action"], "none")


class ScheduleWindowTests(TestCase):
    def test_is_time_to_prepare_true_for_10_minutes(self):
        now = timezone.localtime()
        start_dt = now + timedelta(minutes=10)
        end_dt = now + timedelta(minutes=100)

        lesson = RoomLesson(
            lesson_date=start_dt.date(),
            start_time=start_dt.time().replace(microsecond=0),
            end_time=end_dt.time().replace(microsecond=0),
        )
        self.assertTrue(is_time_to_prepare(lesson))


class FullPreparationTests(TestCase):
    def setUp(self):
        self.room = Room.objects.create(name="101", floor=1, windows=2)
        self.conditioner = Conditioner.objects.create(room=self.room, name="AC-1")

        self.temp_type = SensorType.objects.create(name="температура")
        self.co2_type = SensorType.objects.create(name="co2")
        self.hum_type = SensorType.objects.create(name="влажность")

        self.temp_sensor = Sensor.objects.create(
            room=self.room,
            sensor_type=self.temp_type,
            name="t1",
            last_value=28,
            status="active",
        )
        self.co2_sensor = Sensor.objects.create(
            room=self.room,
            sensor_type=self.co2_type,
            name="c1",
            last_value=500,
            status="active",
        )
        self.hum_sensor = Sensor.objects.create(
            room=self.room,
            sensor_type=self.hum_type,
            name="h1",
            last_value=50,
            status="active",
        )

        self.lesson = RoomLesson.objects.create(
            room=self.room,
            lesson_date=date.today(),
            start_time=time(10, 0),
            end_time=time(11, 30),
            subject="Математика",
        )

    @patch("university.preparation_services.get_room_climate_snapshot")
    @patch.object(Room, "simulate_sensors")
    def test_prepare_room_creates_log_and_opens_window(
            self,
            mock_simulate_sensors,
            mock_get_room_climate_snapshot,
    ):
        mock_simulate_sensors.return_value = []
        mock_get_room_climate_snapshot.return_value = {
            "room": self.room,
            "temperature": 28,
            "humidity": 50,
            "co2": 500,
            "summary": {
                "too_hot": True,
                "too_cold": False,
                "needs_ventilation": False,
            },
        }

        result = prepare_room_for_lesson(
            self.room,
            self.lesson,
            outdoor_weather={
                "temperature": 20,
                "weather_main": "clear",
                "wind_speed": 2,
            },
        )

        self.assertEqual(result["status"], "ok")
        self.room.refresh_from_db()
        self.conditioner.refresh_from_db()

        self.assertTrue(self.room.window_open)
        self.assertFalse(self.conditioner.enabled)
        self.assertEqual(ClimateActionLog.objects.count(), 1)

    @patch("university.preparation_services.get_room_climate_snapshot")
    @patch.object(Room, "simulate_sensors")
    def test_prepare_room_not_repeated_twice(
            self,
            mock_simulate_sensors,
            mock_get_room_climate_snapshot,
    ):
        mock_simulate_sensors.return_value = []
        mock_get_room_climate_snapshot.return_value = {
            "room": self.room,
            "temperature": 28,
            "humidity": 50,
            "co2": 500,
            "summary": {
                "too_hot": True,
                "too_cold": False,
                "needs_ventilation": False,
            },
        }

        first_result = prepare_room_for_lesson(
            self.room,
            self.lesson,
            outdoor_weather={
                "temperature": 20,
                "weather_main": "clear",
                "wind_speed": 2,
            },
        )
        second_result = prepare_room_for_lesson(
            self.room,
            self.lesson,
            outdoor_weather={
                "temperature": 20,
                "weather_main": "clear",
                "wind_speed": 2,
            },
        )

        self.assertEqual(first_result["status"], "ok")
        self.assertEqual(second_result["status"], "skipped")
        self.assertEqual(ClimateActionLog.objects.count(), 1)


from django.test import TestCase

