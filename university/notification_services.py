import datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from accounts.models import UserProfile
from api_client import APIClient

from .models import TeacherNotification


PAIR_TIMES = {
    "1": "9:00-10:30",
    "2": "10:40-12:10",
    "3": "12:20-13:50",
    "4": "14:30-16:00",
    "5": "16:10-17:40",
    "6": "17:50-19:20",
}

DAY_KEYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def parse_date_safe(value):
    return datetime.datetime.strptime(value, "%Y-%m-%d").date()


def get_lessons_for_teacher_on_date(teacher_name, selected_date):
    api = APIClient()
    try:
        data = api.get_schedule_by_teacher(teacher_name)
    except Exception:
        return []

    if not data:
        return []

    if isinstance(data, dict) and data.get("success") is False:
        return []

    schedule = data.get("result") or {}
    day_key = DAY_KEYS[selected_date.weekday()]
    day_schedule = schedule.get(day_key) or {}
    result = []

    for number, pairs in day_schedule.items():
        for pair in pairs or []:
            try:
                start_date = parse_date_safe(pair["start_date"])
                end_date = parse_date_safe(pair["end_date"])
            except Exception:
                continue

            if not (start_date <= selected_date <= end_date):
                continue

            rooms = pair.get("rooms") or []
            room_number = ""
            if rooms:
                room_number = (rooms[0].get("number") or "").strip()

            teachers = pair.get("teachers") or []
            teacher_display = teacher_name
            if teachers:
                first_teacher = (teachers[0].get("full_name") or "").strip()
                if first_teacher:
                    teacher_display = first_teacher

            group_data = pair.get("group") or {}
            group_number = (group_data.get("number") or "").strip()

            subject_name = ((pair.get("subject") or {}).get("name") or "").strip()

            result.append({
                "lesson_number": str(number),
                "time": PAIR_TIMES.get(str(number), ""),
                "subject": subject_name,
                "room": room_number,
                "group": group_number,
                "teacher": teacher_display,
            })

    result.sort(key=lambda item: (item.get("lesson_number", ""), item.get("time", "")))
    return result


def build_environment_message(lesson):
    room = lesson.get("room") or "—"
    pair = lesson.get("lesson_number") or "—"
    time_str = lesson.get("time") or "—"
    subject = lesson.get("subject") or "Без названия"
    group = lesson.get("group") or "—"

    return (
        f"На завтра запланировано занятие: {pair} пара ({time_str}), кабинет {room}, "
        f"дисциплина: {subject}, группа: {group}. "
        f"Можно заранее выбрать: настроить среду вручную или оставить решение алгоритму."
    )


def get_notification_window(lesson_date):
    valid_from = timezone.make_aware(
        datetime.datetime.combine(
            lesson_date - datetime.timedelta(days=1),
            datetime.time(hour=18, minute=0),
        )
    )
    valid_until = timezone.make_aware(
        datetime.datetime.combine(
            lesson_date,
            datetime.time(hour=23, minute=0),
        )
    )
    return valid_from, valid_until


@transaction.atomic
def generate_environment_notifications_for_date(target_date, teacher_full_name=None):
    created = 0

    teacher_profiles = UserProfile.objects.select_related("user").filter(role="teacher")

    if teacher_full_name:
        teacher_profiles = [
            profile for profile in teacher_profiles
            if profile.get_full_name().strip() == teacher_full_name.strip()
        ]

    for profile in teacher_profiles:
        teacher_name = profile.get_full_name()
        if not teacher_name:
            continue

        lessons = get_lessons_for_teacher_on_date(teacher_name, target_date)

        for lesson in lessons:
            if not lesson.get("room"):
                continue

            valid_from, valid_until = get_notification_window(target_date)

            notification, was_created = TeacherNotification.objects.get_or_create(
                user=profile.user,
                notification_type="environment_setup",
                lesson_date=target_date,
                lesson_number=lesson.get("lesson_number") or "",
                room_name=lesson.get("room") or "",
                defaults={
                    "title": f"Подготовка кабинета {lesson.get('room')} к занятию",
                    "message": build_environment_message(lesson),
                    "subject_name": lesson.get("subject") or "",
                    "group_name": lesson.get("group") or "",
                    "recommended_temperature": Decimal("22.0"),
                    "temperature_min": Decimal("20.0"),
                    "temperature_max": Decimal("24.0"),
                    "action_choice": "pending",
                    "payload": {
                        "time": lesson.get("time") or "",
                        "source": "daily_generator",
                        "manual_settings": {},
                    },
                    "status": "unread",
                    "show_popup": True,
                    "valid_from": valid_from,
                    "valid_until": valid_until,
                },
            )

            if was_created:
                created += 1

    return created


def get_actual_unread_notifications(user, limit=5):
    now = timezone.now()
    return TeacherNotification.objects.filter(
        user=user,
        status="unread",
        show_popup=True,
        valid_from__lte=now,
        valid_until__gte=now,
    ).order_by("-valid_from", "-created_at")[:limit]


def get_notification_feed(user):
    now = timezone.now()
    return TeacherNotification.objects.filter(
        user=user,
        valid_until__gte=now - datetime.timedelta(days=1),
    ).order_by("-valid_from", "-created_at")
