import datetime
import re
from django.utils import timezone

from accounts.models import UserProfile
from api_client import APIClient

from .models import Room, RoomLesson


PAIR_TIMES = {
    "1": ("09:00", "10:30"),
    "2": ("10:40", "12:10"),
    "3": ("12:20", "13:50"),
    "4": ("14:30", "16:00"),
    "5": ("16:10", "17:40"),
    "6": ("17:50", "19:20"),
}

DAY_KEYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def parse_date_safe(value):
    return datetime.datetime.strptime(value, "%Y-%m-%d").date()


def parse_time_safe(value):
    return datetime.datetime.strptime(value, "%H:%M").time()


def normalize_room(value):
    if value is None:
        return ""

    raw = str(value).strip().lower()
    raw = raw.replace("ауд.", "").replace("ауд", "")
    raw = raw.replace("аудитория", "").replace("кабинет", "")
    raw = raw.replace(" ", "")
    raw = "".join(ch for ch in raw if ch.isalnum())

    for prefix in ("пр", "pr", "room", "kab"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break

    return raw


def extract_room_code(value):
    normalized = normalize_room(value)
    if not normalized:
        return ""

    match = re.search(r"\d{3,5}", normalized)
    return match.group(0) if match else ""


def canonical_room_name(value):
    normalized = normalize_room(value)
    if not normalized:
        return ""

    room_code = extract_room_code(normalized)
    if room_code:
        return f"Пр{room_code}"

    return normalized.title()


def is_virtual_room(value):
    raw = (value or "").strip().lower()
    normalized = raw.replace(" ", "").replace(".", "")
    return normalized in {"сдо", "lms", "webinar", "teams", "zoom", "online", "онлайн"}


def get_room_model_by_input(room_value):
    normalized = normalize_room(room_value)
    if not normalized:
        return None

    rooms = Room.objects.all()
    for room in rooms:
        room_normalized = normalize_room(room.name)
        if room_normalized == normalized:
            return room

        if extract_room_code(room.name) and extract_room_code(room.name) == extract_room_code(room_value):
            return room

    return None


def iter_dates_for_weekday_in_range(start_date, end_date, weekday_index):
    current = start_date
    while current <= end_date:
        if current.weekday() == weekday_index:
            yield current
        current += datetime.timedelta(days=1)


def build_external_id(teacher_name, lesson_date, pair_number, room_name, subject_name, group_name):
    return "||".join([
        teacher_name or "",
        str(lesson_date),
        str(pair_number),
        room_name or "",
        subject_name or "",
        group_name or "",
    ])


def import_lessons_for_teacher(teacher_name, days_ahead=14):
    teacher_name = (teacher_name or "").strip()
    if not teacher_name:
        return {
            "teacher": teacher_name,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
        }

    api = APIClient()
    data = api.get_schedule_by_teacher(teacher_name)

    if not data or not isinstance(data, dict):
        return {
            "teacher": teacher_name,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 1,
        }

    schedule = data.get("result") or {}
    if not schedule:
        return {
            "teacher": teacher_name,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
        }

    today = datetime.date.today()
    max_date = today + datetime.timedelta(days=days_ahead)

    created_count = 0
    updated_count = 0
    skipped_count = 0
    errors_count = 0

    for day_key, lessons in schedule.items():
        if day_key not in DAY_KEYS:
            continue

        weekday_index = DAY_KEYS.index(day_key)

        for pair_number, pairs in (lessons or {}).items():
            pair_number_str = str(pair_number)

            if pair_number_str not in PAIR_TIMES:
                skipped_count += len(pairs or [])
                continue

            start_time_str, end_time_str = PAIR_TIMES[pair_number_str]
            start_time = parse_time_safe(start_time_str)
            end_time = parse_time_safe(end_time_str)

            for pair in pairs or []:
                try:
                    start_date = parse_date_safe(pair["start_date"])
                    end_date = parse_date_safe(pair["end_date"])
                except Exception:
                    errors_count += 1
                    continue

                actual_start = max(start_date, today)
                actual_end = min(end_date, max_date)

                if actual_start > actual_end:
                    continue

                subject_name = ((pair.get("subject") or {}).get("name") or "").strip()
                group_name = ((pair.get("group") or {}).get("number") or "").strip()

                teachers = pair.get("teachers") or []
                teacher_display = teacher_name
                if teachers:
                    teacher_from_api = (teachers[0].get("full_name") or "").strip()
                    if teacher_from_api:
                        teacher_display = teacher_from_api

                rooms = pair.get("rooms") or []
                if not rooms:
                    skipped_count += 1
                    continue

                for lesson_date in iter_dates_for_weekday_in_range(actual_start, actual_end, weekday_index):
                    for room_data in rooms:
                        room_name_raw = (room_data.get("number") or "").strip()

                        if not room_name_raw:
                            skipped_count += 1
                            continue

                        if is_virtual_room(room_name_raw):
                            skipped_count += 1
                            continue

                        room = get_room_model_by_input(room_name_raw)
                        if room is None:
                            skipped_count += 1
                            continue

                        external_id = build_external_id(
                            teacher_display,
                            lesson_date,
                            pair_number_str,
                            canonical_room_name(room_name_raw),
                            subject_name,
                            group_name,
                        )

                        defaults = {
                            "pair_number": int(pair_number_str),
                            "end_time": end_time,
                            "subject": subject_name,
                            "teacher": teacher_display,
                            "group_name": group_name,
                            "source": "teacher_api",
                            "is_cancelled": False,
                        }

                        lesson, created = RoomLesson.objects.update_or_create(
                            room=room,
                            lesson_date=lesson_date,
                            start_time=start_time,
                            external_id=external_id,
                            defaults=defaults,
                        )

                        if created:
                            created_count += 1
                        else:
                            updated_count += 1

    return {
        "teacher": teacher_name,
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_count,
        "errors": errors_count,
    }


def import_lessons_for_all_teachers(days_ahead=14):
    profiles = (
        UserProfile.objects.filter(role="teacher")
        .select_related("user")
        .order_by("last_name", "first_name", "middle_name")
    )

    stats = {
        "teachers": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "results": [],
    }

    for profile in profiles:
        teacher_name = profile.get_full_name().strip()
        if not teacher_name:
            continue

        result = import_lessons_for_teacher(teacher_name, days_ahead=days_ahead)

        stats["teachers"] += 1
        stats["created"] += result["created"]
        stats["updated"] += result["updated"]
        stats["skipped"] += result["skipped"]
        stats["errors"] += result["errors"]
        stats["results"].append(result)

    return stats
def sync_schedule(days_ahead=14, keep_past_days=7):
    """
    Полная синхронизация расписания с API.

    Загружает расписание на ближайшие days_ahead дней.
    Старые занятия удаляет.
    Неактуальные занятия помечает отменёнными.
    """

    sync_started_at = timezone.now()

    stats = import_lessons_for_all_teachers(days_ahead=days_ahead)

    today = timezone.localdate()
    max_date = today + datetime.timedelta(days=days_ahead)
    old_border = today - datetime.timedelta(days=keep_past_days)

    cancelled_stale = RoomLesson.objects.filter(
        source="teacher_api",
        lesson_date__gte=today,
        lesson_date__lte=max_date,
        is_cancelled=False,
        updated_at__lt=sync_started_at,
    ).update(is_cancelled=True)

    deleted_old, _ = RoomLesson.objects.filter(
        source="teacher_api",
        lesson_date__lt=old_border,
    ).delete()

    stats["cancelled_stale"] = cancelled_stale
    stats["deleted_old"] = deleted_old
    stats["days_ahead"] = days_ahead
    stats["keep_past_days"] = keep_past_days

    return stats