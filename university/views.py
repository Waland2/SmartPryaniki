import datetime
import re
from functools import wraps

from django.core.cache import cache
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import moderator_or_admin_required
from accounts.models import UserProfile
from .models import Room, SensorData
from api_client import APIClient


PAIR_TIMES = {
    "1": "9:00-10:30",
    "2": "10:40-12:10",
    "3": "12:20-13:50",
    "4": "14:30-16:00",
    "5": "16:10-17:40",
    "6": "17:50-19:20",
}

MONTHS_SHORT = {
    1: "Янв.",
    2: "Фев.",
    3: "Мар.",
    4: "Апр.",
    5: "Мая",
    6: "Июн.",
    7: "Июл.",
    8: "Авг.",
    9: "Сент.",
    10: "Окт.",
    11: "Нояб.",
    12: "Дек.",
}

DAY_KEYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

DAY_LABELS_RU = {
    "monday": "Понедельник",
    "tuesday": "Вторник",
    "wednesday": "Среда",
    "thursday": "Четверг",
    "friday": "Пятница",
    "saturday": "Суббота",
    "sunday": "Воскресенье",
}

SCHEDULE_CACHE_TTL = 300
ROOM_INDEX_CACHE_TTL = 300
ROOMS_CACHE_TTL = 900


def teacher_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("/accounts/login/")

        profile = getattr(request.user, "profile", None)
        if profile and profile.role == "teacher":
            return view_func(request, *args, **kwargs)

        return redirect("/schedule/")

    return _wrapped_view


def format_date_range(start_date, end_date):
    start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    return f"{start.day} {MONTHS_SHORT[start.month]} - {end.day} {MONTHS_SHORT[end.month]}"


def build_pair_signature(pair):
    subject_name = (pair.get("subject") or {}).get("name", "").strip()
    subject_type = (pair.get("subject_type") or {}).get("type", "").strip()
    location_name = (pair.get("location") or {}).get("name", "").strip()
    teachers = tuple((teacher.get("full_name") or "").strip() for teacher in pair.get("teachers", []))
    rooms = tuple((room.get("number") or "").strip() for room in pair.get("rooms", []))
    start_date = (pair.get("start_date") or "").strip()
    end_date = (pair.get("end_date") or "").strip()

    return (
        subject_name,
        subject_type,
        location_name,
        teachers,
        rooms,
        start_date,
        end_date,
    )


def deduplicate_schedule(schedule):
    deduplicated = {}

    for day, lessons in (schedule or {}).items():
        if not lessons:
            continue

        new_lessons = {}

        for number, pairs in lessons.items():
            if not pairs:
                continue

            unique_pairs = []
            seen = set()

            for pair in pairs:
                signature = build_pair_signature(pair)
                if signature in seen:
                    continue
                seen.add(signature)
                unique_pairs.append(pair)

            if unique_pairs:
                new_lessons[number] = unique_pairs

        if new_lessons:
            deduplicated[day] = new_lessons

    return deduplicated


def is_virtual_room(value):
    raw = (value or "").strip().lower()
    normalized = raw.replace(" ", "").replace(".", "")
    return normalized in {"сдо", "lms", "webinar", "teams", "zoom", "online", "онлайн"}


def prepare_schedule_for_template(schedule):
    prepared = []

    for day, lessons in (schedule or {}).items():
        if not lessons:
            continue

        day_pairs = []

        for number, pairs in lessons.items():
            if not pairs:
                continue

            prepared_pairs = []

            for pair in pairs:
                location_name = ((pair.get("location") or {}).get("name") or "").strip()
                rooms = pair.get("rooms") or []
                show_rooms = location_name.lower() != "webinar"

                prepared_rooms = []
                for room in rooms:
                    room_number = (room.get("number") or "").strip()
                    prepared_rooms.append({
                        "number": room_number,
                        "popup_available": bool(room_number) and not is_virtual_room(room_number),
                    })

                prepared_pairs.append({
                    "subject_name": ((pair.get("subject") or {}).get("name") or "").strip(),
                    "subject_type": ((pair.get("subject_type") or {}).get("type") or "").strip(),
                    "teachers": pair.get("teachers") or [],
                    "location_name": location_name,
                    "rooms": prepared_rooms,
                    "show_rooms": show_rooms,
                    "date_range": format_date_range(pair["start_date"], pair["end_date"]),
                })

            day_pairs.append({
                "number": str(number),
                "time": PAIR_TIMES.get(str(number), ""),
                "items": prepared_pairs,
            })

        if day_pairs:
            prepared.append({
                "key": day,
                "label": DAY_LABELS_RU.get(day, day),
                "pairs": day_pairs,
            })

    return prepared


def get_default_week_range():
    today = datetime.date.today()

    if today.weekday() == 6:
        next_monday = today + datetime.timedelta(days=1)
        start_date = next_monday
        end_date = next_monday + datetime.timedelta(days=5)
    else:
        start_date = today - datetime.timedelta(days=today.weekday())
        end_date = start_date + datetime.timedelta(days=6)

    return start_date, end_date


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


def parse_date_safe(value):
    return datetime.datetime.strptime(value, "%Y-%m-%d").date()


def _is_bad_api_response(data):
    return (not data) or (isinstance(data, dict) and data.get("success") is False) or not (data.get("result") if isinstance(data, dict) else None)


def _get_schedule_by_teacher_cached(teacher_name):
    teacher_name = (teacher_name or "").strip()
    if not teacher_name:
        return None

    cache_key = f"teacher_schedule::{teacher_name}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    api = APIClient()
    try:
        data = api.get_schedule_by_teacher(teacher_name)
    except Exception:
        data = None

    if _is_bad_api_response(data):
        data = None

    cache.set(cache_key, data, SCHEDULE_CACHE_TTL)
    return data


def _get_schedule_by_group_cached(group_name):
    group_name = (group_name or "").strip()
    if not group_name:
        return None

    cache_key = f"group_schedule::{group_name}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    api = APIClient()
    try:
        data = api.get_schedule(group_name)
    except Exception:
        data = None

    if _is_bad_api_response(data):
        data = None

    cache.set(cache_key, data, SCHEDULE_CACHE_TTL)
    return data


def get_lessons_for_teacher_on_date(teacher_name, selected_date):
    data = _get_schedule_by_teacher_cached(teacher_name)
    if not data:
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

            result.append({
                "lesson_number": str(number),
                "start_time": PAIR_TIMES.get(str(number), "").split("-")[0] if PAIR_TIMES.get(str(number)) else "",
                "end_time": PAIR_TIMES.get(str(number), "").split("-")[1] if PAIR_TIMES.get(str(number)) else "",
                "subject": ((pair.get("subject") or {}).get("name") or "").strip(),
                "room": room_number,
                "group": group_number,
                "teacher": teacher_display,
            })

    result.sort(key=lambda item: (item.get("lesson_number", ""), item.get("start_time", "")))
    return result


def get_room_model_by_input(room_value):
    normalized = normalize_room(room_value)
    if not normalized:
        return None

    catalog = _get_rooms_catalog()
    room = catalog["normalized_map"].get(normalized)
    if room is not None:
        return room

    room_code = extract_room_code(room_value)
    if room_code:
        room = catalog["code_map"].get(room_code)
        if room is not None:
            return room

    return None


def build_room_info(room_value):
    room = get_room_model_by_input(room_value)
    if not room:
        return {
            "room": canonical_room_name(room_value) or (room_value or ""),
            "floor": "Нету",
            "chairs": "Нету",
            "desks": "Нету",
            "computers": "Нету",
            "windows": "Нету",
            "description": "Нету",
            "conditioners": "Нету",
            "conditioners_count": "Нету",
            "sensors_count": 0,
            "temperature": None,
            "co2": None,
            "humidity": None,
            "light_on": None,
            "conditioner_on": None,
            "updated_at": "Нету",
            "sensor_cards": [],
            "exists_in_db": False,
        }

    sensors = room.sensor_set.select_related("sensor_type").all()
    temperature = None
    co2 = None
    humidity = None
    light_on = False
    conditioner_on = False
    updated_at = None
    sensor_cards = []

    for sensor in sensors:
        sensor_type_name = ((sensor.sensor_type.name if sensor.sensor_type else "") or "").strip()
        sensor_name = sensor_type_name.lower()
        full_name = f"{sensor_name} {sensor.name}".lower()

        if temperature is None and "темп" in full_name:
            temperature = sensor.last_value
        if co2 is None and ("co2" in full_name or "углеки" in full_name):
            co2 = sensor.last_value
        if humidity is None and "влаж" in full_name:
            humidity = sensor.last_value
        if "свет" in full_name:
            light_on = sensor.status == "active" and bool(sensor.last_value if sensor.last_value is not None else 1)
        if "конди" in full_name:
            conditioner_on = sensor.status == "active" and bool(sensor.last_value if sensor.last_value is not None else 1)

        if sensor.last_updated and (updated_at is None or sensor.last_updated > updated_at):
            updated_at = sensor.last_updated

        sensor_cards.append({
            "name": sensor.name,
            "type": sensor_type_name or "Датчик",
            "status": sensor.status,
            "value": "Нету" if sensor.last_value is None else str(sensor.last_value),
        })

    return {
        "room": room.name,
        "floor": room.floor,
        "chairs": room.chairs,
        "desks": room.desks,
        "computers": room.computers,
        "windows": room.windows,
        "description": room.description or "Нету",
        "conditioners": room.conditioners,
        "conditioners_count": room.conditioners,
        "sensors_count": sensors.count(),
        "temperature": temperature,
        "co2": co2,
        "humidity": humidity,
        "light_on": light_on,
        "conditioner_on": conditioner_on,
        "updated_at": updated_at.strftime("%d.%m.%Y %H:%M") if updated_at else "Нету",
        "sensor_cards": sensor_cards,
        "exists_in_db": True,
    }


def build_room_popup_map(schedule):
    room_popup_map = {}

    for lessons in (schedule or {}).values():
        if not lessons:
            continue

        for pairs in lessons.values():
            for pair in pairs or []:
                for room in pair.get("rooms") or []:
                    room_number = (room.get("number") or "").strip()
                    if not room_number or is_virtual_room(room_number):
                        continue

                    canonical_name = canonical_room_name(room_number)
                    if not canonical_name:
                        continue

                    if canonical_name in room_popup_map:
                        continue

                    info = build_room_info(canonical_name)
                    room_popup_map[canonical_name] = {
                        "room": info.get("room") or canonical_name,
                        "exists_in_db": info.get("exists_in_db", False),
                        "floor": info.get("floor"),
                        "chairs": info.get("chairs"),
                        "desks": info.get("desks"),
                        "computers": info.get("computers"),
                        "windows": info.get("windows"),
                        "conditioners": info.get("conditioners"),
                        "description": info.get("description") or "Нету",
                        "sensors_count": info.get("sensors_count", 0),
                        "temperature": info.get("temperature"),
                        "co2": info.get("co2"),
                        "humidity": info.get("humidity"),
                        "light_on": info.get("light_on"),
                        "conditioner_on": info.get("conditioner_on"),
                        "updated_at": info.get("updated_at") or "Нету",
                        "sensor_cards": info.get("sensor_cards") or [],
                    }

    return room_popup_map


def _get_rooms_catalog():
    cache_key = "rooms_catalog_v3"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    rooms = list(Room.objects.all().order_by("name").prefetch_related("sensor_set__sensor_type"))
    normalized_map = {}
    code_map = {}
    available_rooms = []
    seen = set()

    for room in rooms:
        canonical = canonical_room_name(room.name)
        normalized = normalize_room(canonical)
        room_code = extract_room_code(room.name)
        if not normalized:
            continue

        if normalized not in normalized_map:
            normalized_map[normalized] = room

        if room_code and room_code not in code_map:
            code_map[room_code] = room

        if normalized not in seen:
            seen.add(normalized)
            available_rooms.append(canonical)

    data = {
        "rooms": rooms,
        "normalized_map": normalized_map,
        "code_map": code_map,
        "available_rooms": available_rooms,
    }
    cache.set(cache_key, data, ROOMS_CACHE_TTL)
    return data


def get_all_teacher_names():
    cache_key = "teacher_names::all"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    names = []
    for profile in UserProfile.objects.filter(role="teacher"):
        full_name = profile.get_full_name()
        if full_name:
            names.append(full_name)

    names = sorted(set(names))
    cache.set(cache_key, names, ROOMS_CACHE_TTL)
    return names


def get_all_group_names_from_known_teachers():
    cache_key = "known_group_names_from_teachers_v1"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    groups = set()

    for teacher_name in get_all_teacher_names():
        data = _get_schedule_by_teacher_cached(teacher_name)
        if not data:
            continue

        schedule = data.get("result") or {}
        for day_schedule in schedule.values():
            if not day_schedule:
                continue

            for pairs in day_schedule.values():
                for pair in pairs or []:
                    group_data = pair.get("group") or {}
                    group_number = (group_data.get("number") or "").strip()
                    if group_number:
                        groups.add(group_number)

    groups = sorted(groups)
    cache.set(cache_key, groups, ROOMS_CACHE_TTL)
    return groups


def get_lessons_for_group_on_date(group_name, selected_date):
    data = _get_schedule_by_group_cached(group_name)
    if not data:
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
            teacher_display = "—"
            if teachers:
                teacher_display = (teachers[0].get("full_name") or "").strip() or "—"

            result.append({
                "lesson_number": str(number),
                "start_time": PAIR_TIMES.get(str(number), "").split("-")[0] if PAIR_TIMES.get(str(number)) else "",
                "end_time": PAIR_TIMES.get(str(number), "").split("-")[1] if PAIR_TIMES.get(str(number)) else "",
                "subject": ((pair.get("subject") or {}).get("name") or "").strip(),
                "room": room_number,
                "group": group_name,
                "teacher": teacher_display,
            })

    result.sort(key=lambda item: (item.get("lesson_number", ""), item.get("start_time", "")))
    return result


def _build_room_schedule_index(selected_date):
    date_key = selected_date.strftime("%Y-%m-%d")
    cache_key = f"room_schedule_index::{date_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    room_lessons_map = {}
    occupied_by_pair = {str(number): {} for number in PAIR_TIMES.keys()}
    group_names = get_all_group_names_from_known_teachers()

    for group_name in group_names:
        lessons = get_lessons_for_group_on_date(group_name, selected_date)

        for lesson in lessons:
            normalized_room = normalize_room(lesson.get("room"))
            if not normalized_room:
                continue

            lesson_key = (
                lesson.get("lesson_number"),
                lesson.get("subject"),
                lesson.get("group"),
                lesson.get("teacher"),
            )

            room_bucket = room_lessons_map.setdefault(normalized_room, {"lessons": [], "seen": set()})
            if lesson_key not in room_bucket["seen"]:
                room_bucket["seen"].add(lesson_key)
                room_bucket["lessons"].append(lesson)

            pair_number = str(lesson.get("lesson_number"))
            pair_bucket = occupied_by_pair.setdefault(pair_number, {})
            if normalized_room not in pair_bucket:
                pair_bucket[normalized_room] = {
                    "room": canonical_room_name(lesson.get("room")),
                    "teacher": lesson.get("teacher") or "—",
                    "subject": lesson.get("subject") or "—",
                    "group": lesson.get("group") or "—",
                    "lesson_number": lesson.get("lesson_number") or "",
                }

    final_room_lessons_map = {}
    for normalized_room, bucket in room_lessons_map.items():
        lessons = bucket["lessons"]
        lessons.sort(key=lambda item: item.get("lesson_number", ""))
        final_room_lessons_map[normalized_room] = lessons

    result = {
        "room_lessons_map": final_room_lessons_map,
        "occupied_by_pair": occupied_by_pair,
        "group_count": len(group_names),
    }
    cache.set(cache_key, result, ROOM_INDEX_CACHE_TTL)
    return result


def get_all_room_lessons_on_date(room_value, selected_date):
    normalized_room = normalize_room(room_value)
    if not normalized_room:
        return []

    index = _build_room_schedule_index(selected_date)
    return index["room_lessons_map"].get(normalized_room, [])


def get_occupied_rooms_for_pair(selected_date, pair_number):
    if not pair_number:
        return []

    index = _build_room_schedule_index(selected_date)
    occupied = list(index["occupied_by_pair"].get(str(pair_number), {}).values())
    occupied.sort(key=lambda item: item["room"])
    return occupied


def get_free_rooms_for_pair(selected_date, pair_number):
    all_rooms = list(_get_rooms_catalog()["available_rooms"])
    occupied = get_occupied_rooms_for_pair(selected_date, pair_number)
    occupied_set = {normalize_room(item["room"]) for item in occupied}

    free_rooms = [room_name for room_name in all_rooms if normalize_room(room_name) not in occupied_set]
    free_rooms.sort()
    return free_rooms


def get_room_busy_state(room_value, selected_date, pair_number):
    normalized_room = normalize_room(room_value)
    if not normalized_room or not pair_number:
        return {
            "is_busy": False,
            "matched": None,
            "is_known": False,
        }

    index = _build_room_schedule_index(selected_date)
    pair_bucket = index["occupied_by_pair"].get(str(pair_number), {})
    matched = pair_bucket.get(normalized_room)

    if matched:
        return {
            "is_busy": True,
            "matched": matched,
            "is_known": True,
        }

    if index.get("group_count", 0) == 0:
        return {
            "is_busy": False,
            "matched": None,
            "is_known": False,
        }

    return {
        "is_busy": False,
        "matched": None,
        "is_known": True,
    }


def index_redirect(request):
    if not request.user.is_authenticated:
        return redirect("/accounts/login/")

    if request.user.is_superuser:
        return redirect("/dashboard/")

    profile = getattr(request.user, "profile", None)

    if profile and profile.role == "moderator":
        return redirect("/dashboard/")

    return redirect("/schedule/")


@moderator_or_admin_required
def dashboard_home(request):
    rooms = Room.objects.prefetch_related("sensor_set__sensor_type").all()

    total_rooms = rooms.count()
    total_sensors = sum(room.sensor_set.count() for room in rooms)
    active_sensors = sum(room.sensor_set.filter(status="active").count() for room in rooms)
    error_sensors = sum(room.sensor_set.filter(status="error").count() for room in rooms)

    context = {
        "rooms": rooms,
        "total_rooms": total_rooms,
        "total_sensors": total_sensors,
        "active_sensors": active_sensors,
        "error_sensors": error_sensors,
        "title": "Панель администратора",
    }
    return render(request, "dashboard/home.html", context)


@moderator_or_admin_required
def room_detail(request, room_id):
    room = get_object_or_404(
        Room.objects.prefetch_related("sensor_set__sensor_type"),
        pk=room_id,
    )

    sensors = room.sensor_set.all()
    latest_data = SensorData.objects.filter(sensor__room=room).select_related("sensor")[:20]

    context = {
        "room": room,
        "sensors": sensors,
        "latest_data": latest_data,
        "title": f"Кабинет: {room.name}",
    }
    return render(request, "dashboard/room_detail.html", context)


@moderator_or_admin_required
def room_simulate(request, room_id):
    room = get_object_or_404(
        Room.objects.prefetch_related("sensor_set__sensor_type"),
        pk=room_id,
    )

    results = room.simulate_sensors()

    return render(
        request,
        "dashboard/simulate_result.html",
        {
            "room": room,
            "results": results,
            "title": f"Симуляция: {room.name}",
        },
    )


@moderator_or_admin_required
def room_history(request, room_id):
    room = get_object_or_404(Room, pk=room_id)
    history = (
        SensorData.objects.filter(sensor__room=room)
        .select_related("sensor", "sensor__sensor_type")
        .order_by("-created_at")[:100]
    )

    context = {
        "room": room,
        "history": history,
        "title": f"История показаний: {room.name}",
    }
    return render(request, "dashboard/history.html", context)


def schedule_view(request):
    group = request.GET.get("group", "").strip()
    selected_day = request.GET.get("day")

    raw_teacher = request.GET.get("teacher")
    raw_date_from = request.GET.get("date_from")
    raw_date_to = request.GET.get("date_to")

    profile = getattr(request.user, "profile", None)
    is_teacher = bool(
        request.user.is_authenticated
        and profile
        and profile.role == "teacher"
    )

    initial_open = request.method == "GET" and not request.GET

    if raw_teacher is None:
        teacher = profile.get_full_name() if is_teacher else ""
    else:
        teacher = raw_teacher.strip()

    if initial_open:
        default_date_from, default_date_to = get_default_week_range()
        date_from_obj = default_date_from
        date_to_obj = default_date_to
    else:
        date_from_obj = None
        date_to_obj = None

        if raw_date_from:
            try:
                date_from_obj = datetime.datetime.strptime(raw_date_from, "%Y-%m-%d").date()
            except ValueError:
                date_from_obj = None

        if raw_date_to:
            try:
                date_to_obj = datetime.datetime.strptime(raw_date_to, "%Y-%m-%d").date()
            except ValueError:
                date_to_obj = None

    date_from = date_from_obj.strftime("%Y-%m-%d") if date_from_obj else ""
    date_to = date_to_obj.strftime("%Y-%m-%d") if date_to_obj else ""

    schedule = None
    warning = None

    today_index = datetime.datetime.today().weekday()
    today = DAY_KEYS[today_index]

    api = APIClient()
    data = None

    try:
        if teacher:
            data = _get_schedule_by_teacher_cached(teacher)
        elif group:
            data = api.get_schedule(group)
            if _is_bad_api_response(data):
                data = None
    except Exception:
        data = None
        warning = "Не удалось получить расписание из API"

    if data:
        schedule = data.get("result")

        if not schedule or all(v is None for v in schedule.values()):
            schedule = None
            warning = "Ничего не найдено по заданным параметрам"

        if teacher and group and schedule:
            filtered_schedule = {}

            for day, lessons in schedule.items():
                if not lessons:
                    continue

                new_lessons = {}

                for number, pairs in (lessons or {}).items():
                    if pairs:
                        filtered_pairs = [
                            pair for pair in pairs
                            if pair["group"]["number"] == group
                        ]

                        if filtered_pairs:
                            new_lessons[number] = filtered_pairs

                if new_lessons:
                    filtered_schedule[day] = new_lessons

            schedule = filtered_schedule

            if not schedule:
                warning = "У этого преподавателя нет занятий с данной группой"

        if (date_from_obj or date_to_obj) and schedule:
            filtered_schedule = {}

            for day, lessons in schedule.items():
                if not lessons:
                    continue

                new_lessons = {}

                for number, pairs in lessons.items():
                    if pairs:
                        filtered_pairs = []

                        for pair in pairs:
                            start = datetime.datetime.strptime(pair["start_date"], "%Y-%m-%d").date()
                            end = datetime.datetime.strptime(pair["end_date"], "%Y-%m-%d").date()

                            ok = True

                            if date_from_obj and end < date_from_obj:
                                ok = False

                            if date_to_obj and start > date_to_obj:
                                ok = False

                            if ok:
                                filtered_pairs.append(pair)

                        if filtered_pairs:
                            new_lessons[number] = filtered_pairs

                if new_lessons:
                    filtered_schedule[day] = new_lessons

            schedule = filtered_schedule

        if selected_day and schedule:
            selected_day_schedule = schedule.get(selected_day)
            schedule = {selected_day: selected_day_schedule} if selected_day_schedule else None

            if not schedule:
                warning = "На выбранный день занятий не найдено"

        if schedule:
            schedule = deduplicate_schedule(schedule)
            if not schedule:
                warning = "Ничего не найдено по заданным параметрам"

    prepared_schedule = prepare_schedule_for_template(schedule) if schedule else None
    room_popup_data = build_room_popup_map(schedule) if schedule else {}

    return render(request, "schedule.html", {
        "schedule": prepared_schedule,
        "group": group,
        "teacher": teacher,
        "today": today,
        "selected_day": selected_day,
        "warning": warning,
        "date_from": date_from,
        "date_to": date_to,
        "room_popup_data": room_popup_data,
    })


@teacher_required
def current_day_view(request):
    profile = getattr(request.user, "profile", None)
    teacher = profile.get_full_name() if profile else ""

    selected_date_str = request.GET.get("date") or datetime.date.today().strftime("%Y-%m-%d")
    selected_pair = (request.GET.get("pair") or "").strip()
    selected_date = parse_date_safe(selected_date_str)

    lessons = get_lessons_for_teacher_on_date(teacher, selected_date)

    current_pair = None
    now_time = datetime.datetime.now().strftime("%H:%M")
    if selected_date == datetime.date.today():
        for lesson in lessons:
            if lesson["start_time"] and lesson["end_time"] and lesson["start_time"] <= now_time <= lesson["end_time"]:
                current_pair = lesson
                break

    selected_lesson = None
    if selected_pair:
        for lesson in lessons:
            if str(lesson.get("lesson_number")) == str(selected_pair):
                selected_lesson = lesson
                break

    if selected_lesson is None:
        selected_lesson = current_pair

    selected_room = canonical_room_name(selected_lesson.get("room")) if selected_lesson else ""
    room_info = build_room_info(selected_room) if selected_room else {
        "room": "",
        "floor": "—",
        "chairs": "—",
        "desks": "—",
        "computers": "—",
        "conditioners_count": "—",
        "sensors_count": 0,
        "temperature": None,
        "light_on": None,
        "conditioner_on": None,
        "updated_at": "—",
        "sensor_cards": [],
    }

    room_schedule_status = "Нет пары"
    room_teacher_now = "—"
    room_subject_now = "—"
    room_group_now = "—"
    room_pair_now = selected_pair if selected_pair else "—"
    room_time_now = PAIR_TIMES.get(str(selected_pair), "—") if selected_pair else "—"

    if selected_lesson:
        room_schedule_status = "Занят"
        room_teacher_now = selected_lesson.get("teacher") or "—"
        room_subject_now = selected_lesson.get("subject") or "—"
        room_group_now = selected_lesson.get("group") or "—"
        room_pair_now = selected_lesson.get("lesson_number") or "—"
        room_time_now = f'{selected_lesson.get("start_time", "—")}-{selected_lesson.get("end_time", "—")}'

    schedule = []
    for lesson in lessons:
        lesson_number = str(lesson.get("lesson_number"))
        is_selected = bool(selected_lesson and lesson_number == str(selected_lesson.get("lesson_number")))
        is_active = bool(current_pair and lesson_number == str(current_pair.get("lesson_number")))
        schedule.append({
            "lesson_number": lesson_number,
            "time": PAIR_TIMES.get(lesson_number, ""),
            "subject_name": lesson.get("subject") or "—",
            "subject_type": "",
            "rooms": [canonical_room_name(lesson.get("room"))] if lesson.get("room") else [],
            "group": lesson.get("group") or "—",
            "is_selected": is_selected,
            "is_active": is_active,
        })

    current_pair_message = None
    if selected_date == datetime.date.today() and current_pair is None:
        current_pair_message = "Сейчас у преподавателя нет текущей пары."

    context = {
        "selected_date": selected_date_str,
        "selected_pair": str(selected_pair),
        "selected_room": selected_room,
        "schedule": schedule,
        "lessons": lessons,
        "current_pair": current_pair,
        "selected_lesson": selected_lesson,
        "no_current_pair": current_pair is None,
        "room_info": room_info,
        "room_lessons": get_all_room_lessons_on_date(selected_room, selected_date) if selected_room else [],
        "room_schedule_status": room_schedule_status,
        "room_teacher_now": room_teacher_now,
        "room_subject_now": room_subject_now,
        "room_group_now": room_group_now,
        "room_pair_now": room_pair_now,
        "room_time_now": room_time_now,
        "pair_times": PAIR_TIMES,
        "today_label": selected_date.strftime("%d.%m.%Y"),
        "now_time": now_time,
        "selected_day_label": DAY_LABELS_RU[DAY_KEYS[selected_date.weekday()]],
        "current_pair_message": current_pair_message,
        "warning": None,
    }
    return render(request, "current_day.html", context)


def build_room_timeline(selected_room, selected_date):
    timeline = []
    room_lessons = get_all_room_lessons_on_date(selected_room, selected_date) if selected_room else []

    lesson_by_pair = {
        str(lesson.get("lesson_number")): lesson
        for lesson in room_lessons
    }

    today = datetime.date.today()
    now_value = datetime.datetime.now().strftime("%H:%M") if selected_date == today else None

    for pair_number, pair_time in PAIR_TIMES.items():
        lesson = lesson_by_pair.get(str(pair_number))
        is_active = False

        if now_value:
            start_time, end_time = pair_time.split("-")
            if start_time <= now_value <= end_time:
                is_active = True

        timeline.append({
            "pair_number": str(pair_number),
            "time": pair_time,
            "is_busy": lesson is not None,
            "is_active": is_active,
            "is_selected": False,
            "subject": lesson.get("subject") if lesson else "—",
            "teacher": lesson.get("teacher") if lesson else "—",
            "group": lesson.get("group") if lesson else "—",
        })

    return timeline


@teacher_required
def rooms_view(request):
    selected_date_str = request.GET.get("date") or datetime.date.today().strftime("%Y-%m-%d")
    selected_pair = (request.GET.get("pair") or "").strip()
    raw_room = (request.GET.get("room") or "").strip()
    show_free_rooms = request.GET.get("show_free_rooms") == "1"

    selected_date = parse_date_safe(selected_date_str)
    selected_room = canonical_room_name(raw_room) if raw_room else ""

    available_rooms = list(_get_rooms_catalog()["available_rooms"])

    if selected_room:
        room_info = build_room_info(selected_room)
    else:
        room_info = {
            "room": "",
            "floor": "—",
            "chairs": "—",
            "desks": "—",
            "computers": "—",
            "conditioners": "—",
            "conditioners_count": "—",
            "sensors_count": 0,
            "temperature": None,
            "co2": None,
            "humidity": None,
            "light_on": None,
            "conditioner_on": None,
            "updated_at": "—",
            "sensor_cards": [],
        }

    room_timeline = build_room_timeline(selected_room, selected_date) if selected_room else [
        {
            "pair_number": str(pair_number),
            "time": pair_time,
            "is_busy": False,
            "is_active": False,
            "is_selected": False,
            "subject": "—",
            "teacher": "—",
            "group": "—",
        }
        for pair_number, pair_time in PAIR_TIMES.items()
    ]

    selected_pair_lesson = None
    for slot in room_timeline:
        if str(slot["pair_number"]) == str(selected_pair):
            slot["is_selected"] = True
            if slot["is_busy"]:
                selected_pair_lesson = slot

    room_schedule_status = "Не выбран кабинет"
    room_teacher_now = "—"
    room_subject_now = "—"
    room_group_now = "—"
    room_pair_now = selected_pair if selected_pair else "—"
    room_time_now = PAIR_TIMES.get(str(selected_pair), "—") if selected_pair else "—"

    busy_state = get_room_busy_state(selected_room, selected_date, selected_pair) if selected_room and selected_pair else None

    if selected_room:
        if show_free_rooms and selected_pair:
            if busy_state and busy_state["is_busy"]:
                room_schedule_status = "Занят"
                room_teacher_now = busy_state["matched"].get("teacher") or "—"
                room_subject_now = busy_state["matched"].get("subject") or "—"
                room_group_now = busy_state["matched"].get("group") or "—"
            elif busy_state and busy_state["is_known"]:
                room_schedule_status = "Свободен"
                room_teacher_now = "Нет занятия"
                room_subject_now = "Нет занятия"
                room_group_now = "—"
            else:
                room_schedule_status = "Не удалось определить"
                room_teacher_now = "Нет данных"
                room_subject_now = "Нет данных"
                room_group_now = "—"
        elif selected_pair_lesson:
            room_schedule_status = "Занят"
            room_teacher_now = selected_pair_lesson.get("teacher") or "—"
            room_subject_now = selected_pair_lesson.get("subject") or "—"
            room_group_now = selected_pair_lesson.get("group") or "—"
        elif selected_pair:
            if busy_state and busy_state["is_known"]:
                room_schedule_status = "Свободен"
                room_teacher_now = "Нет занятия"
                room_subject_now = "Нет занятия"
                room_group_now = "—"
            else:
                room_schedule_status = "Не удалось определить"
                room_teacher_now = "Нет данных"
                room_subject_now = "Нет данных"
                room_group_now = "—"
        else:
            room_schedule_status = "Выбран кабинет"

    free_rooms = get_free_rooms_for_pair(selected_date, selected_pair) if (show_free_rooms and selected_pair) else []

    warning = None
    if show_free_rooms and not selected_pair:
        warning = "Чтобы показать свободные кабинеты, выберите номер пары."

    context = {
        "selected_date": selected_date_str,
        "selected_pair": str(selected_pair),
        "selected_pair_number": str(selected_pair) if selected_pair else "",
        "selected_room": selected_room,
        "available_rooms": available_rooms,
        "room_info": room_info,
        "room_timeline": room_timeline,
        "room_schedule_status": room_schedule_status,
        "room_teacher_now": room_teacher_now,
        "room_subject_now": room_subject_now,
        "room_group_now": room_group_now,
        "room_pair_now": room_pair_now,
        "room_time_now": room_time_now,
        "free_rooms": free_rooms,
        "show_free_rooms": show_free_rooms,
        "selected_day_label": DAY_LABELS_RU[DAY_KEYS[selected_date.weekday()]],
        "warning": warning,
        "pair_times": PAIR_TIMES,
    }
    return render(request, "rooms.html", context)
