from datetime import date, time, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
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
    Feedback,
)
from university.preparation_services import choose_climate_action, prepare_room_for_lesson
from university.schedule_services import is_time_to_prepare


def make_schedule_pair(group_number="241-362"):
    return {
        "subject": {"name": "Math"},
        "subject_type": {"type": "Lecture"},
        "location": {"name": "Campus"},
        "teachers": [{"full_name": "Teacher Test"}],
        "rooms": [{"number": "101"}],
        "group": {"number": group_number},
        "start_date": "2026-05-11",
        "end_date": "2026-05-17",
    }


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


class SchedulePageDayFilterTests(TestCase):
    @patch("university.views.APIClient.get_schedule")
    def test_day_selector_filters_schedule_to_selected_day(self, mock_get_schedule):
        mock_get_schedule.return_value = {
            "result": {
                "monday": {"1": [make_schedule_pair()]},
                "wednesday": {"2": [make_schedule_pair()]},
            }
        }

        response = self.client.get(
            "/schedule/",
            {
                "group": "241-362",
                "day": "wednesday",
                "date_from": "2026-05-13",
                "date_to": "2026-05-13",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([day["key"] for day in response.context["schedule"]], ["wednesday"])
        self.assertEqual(response.context["selected_day"], "wednesday")
        self.assertContains(response, '<div class="topbar-title">Расписание</div>', html=True)

    @patch("university.views.APIClient.get_schedule")
    def test_date_filter_excludes_selected_day_without_matching_date(self, mock_get_schedule):
        mock_get_schedule.return_value = {
            "result": {
                "monday": {"1": [make_schedule_pair()]},
            }
        }

        response = self.client.get(
            "/schedule/",
            {
                "group": "241-362",
                "day": "monday",
                "date_from": "2026-05-13",
                "date_to": "2026-05-13",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["schedule"])


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


class RoleAccessTests(TestCase):
    def setUp(self):
        self.room_1 = Room.objects.create(name="101", building=1, floor=1)
        self.room_2 = Room.objects.create(name="201", building=2, floor=2)

        self.global_admin = User.objects.create_superuser("global", password="password")
        self.building_admin = User.objects.create_user("building", password="password", is_staff=True)
        self.building_admin.profile.role = "moderator"
        self.building_admin.profile.building = 1
        self.building_admin.profile.save()

    def test_public_feedback_creates_notification(self):
        response = self.client.post(
            "/feedback/",
            {"name": "Гость", "email": "guest@example.com", "message": "Нужна помощь"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Feedback.objects.filter(name="Гость").exists())

    @patch("university.views._get_rooms_catalog")
    def test_public_rooms_page_is_available(self, mock_get_rooms_catalog):
        mock_get_rooms_catalog.return_value = {"available_rooms": []}

        response = self.client.get("/rooms/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Панель<span> управления</span>", html=True)
        self.assertContains(response, '<div class="topbar-title">Кабинеты</div>', html=True)

    def test_public_feedback_page_has_guest_heading(self):
        response = self.client.get("/feedback/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Панель<span> управления</span>", html=True)
        self.assertContains(response, '<div class="topbar-title">Обратная связь</div>', html=True)

    def test_global_admin_can_open_feedback_notifications(self):
        self.client.force_login(self.global_admin)

        response = self.client.get("/dashboard/feedback/")

        self.assertEqual(response.status_code, 200)

    def test_global_admin_can_delete_feedback_notification(self):
        notification = Feedback.objects.create(name="Guest", message="Delete me")
        self.client.force_login(self.global_admin)

        response = self.client.post(f"/dashboard/feedback/{notification.pk}/delete/")

        self.assertRedirects(response, "/dashboard/feedback/")
        self.assertFalse(Feedback.objects.filter(pk=notification.pk).exists())

    def test_building_admin_cannot_delete_feedback_notification(self):
        notification = Feedback.objects.create(name="Guest", message="Keep me")
        self.client.force_login(self.building_admin)

        response = self.client.post(f"/dashboard/feedback/{notification.pk}/delete/")

        self.assertRedirects(response, "/dashboard/")
        self.assertTrue(Feedback.objects.filter(pk=notification.pk).exists())

    def test_feedback_older_than_30_days_is_deleted_when_notifications_opened(self):
        notification = Feedback.objects.create(name="Guest", message="Expired")
        Feedback.objects.filter(pk=notification.pk).update(
            created_at=timezone.now() - timedelta(days=31),
        )
        self.client.force_login(self.global_admin)

        response = self.client.get("/dashboard/feedback/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Feedback.objects.filter(pk=notification.pk).exists())

    def test_building_admin_cannot_open_feedback_notifications(self):
        self.client.force_login(self.building_admin)

        response = self.client.get("/dashboard/feedback/")

        self.assertRedirects(response, "/dashboard/")

    def test_building_admin_sees_only_own_building_on_dashboard(self):
        self.client.force_login(self.building_admin)

        response = self.client.get("/dashboard/")

        self.assertContains(response, self.room_1.name)
        self.assertNotContains(response, self.room_2.name)

    def test_building_admin_cannot_open_other_building_room(self):
        self.client.force_login(self.building_admin)

        response = self.client.get(f"/dashboard/room/{self.room_2.pk}/")

        self.assertEqual(response.status_code, 404)

    def test_building_admin_room_page_has_no_database_edit_links(self):
        self.client.force_login(self.building_admin)

        response = self.client.get(f"/dashboard/room/{self.room_1.pk}/")

        self.assertNotContains(response, "/admin/university/room/")
        self.assertNotContains(response, "/admin/university/climateactionlog/")

    def test_django_admin_is_global_only(self):
        self.client.force_login(self.building_admin)

        response = self.client.get("/admin/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

