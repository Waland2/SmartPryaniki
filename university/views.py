import datetime

from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import moderator_or_admin_required, teacher_required
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

DAY_LABELS = {
    "monday": "Понедельник",
    "tuesday": "Вторник",
    "wednesday": "Среда",
    "thursday": "Четверг",
    "friday": "Пятница",
    "saturday": "Суббота",
    "sunday": "Воскресенье",
}


def format_date_range(start_date, end_date):
    start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    return f"{start.day} {MONTHS_SHORT[start.month]} - {end.day} {MONTHS_SHORT[end.month]}"


def build_pair_signature(pair):
    subject_name = (pair.get("subject") or {}).get("name", "").strip()
    subject_type = (pair.get("subject_type") or {}).get("type", "").strip()
    location_name = (pair.get("location") or {}).get("name", "").strip()
    teachers = tuple(
        (teacher.get("full_name") or "").strip()
        for teacher in pair.get("teachers", [])
    )
    rooms = tuple(
        (room.get("number") or "").strip()
        for room in pair.get("rooms", [])
    )
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

                prepared_pairs.append({
                    "subject_name": ((pair.get("subject") or {}).get("name") or "").strip(),
                    "subject_type": ((pair.get("subject_type") or {}).get("type") or "").strip(),
                    "teachers": pair.get("teachers") or [],
                    "location_name": location_name,
                    "rooms": rooms,
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
                "label": DAY_LABELS.get(day, day),
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


def parse_date_or_none(value):
    if not value:
        return None
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_time_or_default(value, default_time=None):
    if not value:
        return default_time or datetime.datetime.now().time().replace(second=0, microsecond=0)
    try:
        return datetime.datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return default_time or datetime.datetime.now().time().replace(second=0, microsecond=0)


def normalize_room(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def get_weekday_key(target_date):
    days_map = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    return days_map[target_date.weekday()]


def date_overlaps_pair(pair, target_date):
    start_raw = pair.get("start_date")
    end_raw = pair.get("end_date")

    if not start_raw or not end_raw:
        return False

    start = datetime.datetime.strptime(start_raw, "%Y-%m-%d").date()
    end = datetime.datetime.strptime(end_raw, "%Y-%m-%d").date()
    return start <= target_date <= end


def time_in_pair(selected_time, pair_number):
    slot = PAIR_TIMES.get(str(pair_number))
    if not slot or not selected_time:
        return False

    start_raw, end_raw = slot.split("-")
    start_time = datetime.datetime.strptime(start_raw, "%H:%M").time()
    end_time = datetime.datetime.strptime(end_raw, "%H:%M").time()
    return start_time <= selected_time <= end_time


def get_room_object(room_name):
    if not room_name:
        return None

    normalized = str(room_name).strip()
    normalized_lookup = normalize_room(normalized)
    if not normalized_lookup:
        return None

    rooms = Room.objects.prefetch_related("sensor_set__sensor_type")
    room = rooms.filter(name__iexact=normalized).first()
    if room:
        return room

    for candidate in rooms:
        if normalize_room(candidate.name) == normalized_lookup:
            return candidate

    room = rooms.filter(name__icontains=normalized).first()
    if room:
        return room

    for candidate in rooms:
        if normalized_lookup in normalize_room(candidate.name) or normalize_room(candidate.name) in normalized_lookup:
            return candidate

    return None


def build_room_state(room):
    info = {
        "room": room.name if room else "",
        "floor": room.floor if room else "—",
        "chairs": room.chairs if room else 0,
        "desks": room.desks if room else 0,
        "computers": room.computers if room else 0,
        "conditioners_count": room.conditioners if room else 0,
        "temperature": None,
        "co2": None,
        "humidity": None,
        "light_on": None,
        "conditioner_on": None,
        "updated_at": None,
        "sensors_count": 0,
        "sensor_cards": [],
        "notes": [],
    }

    if not room:
        info["notes"].append("Кабинет не найден в локальной базе.")
        return info

    sensors = list(room.sensor_set.all())
    info["sensors_count"] = len(sensors)

    latest_updated = None

    for sensor in sensors:
        sensor_type_name = (sensor.sensor_type.name or "").strip()
        sensor_type_name_lower = sensor_type_name.lower()
        last_updated = sensor.last_updated
        if last_updated and (latest_updated is None or last_updated > latest_updated):
            latest_updated = last_updated

        current_value = sensor.last_value
        display_value = "—"
        unit = ""

        if current_value is not None:
            display_value = current_value

        if "темпера" in sensor_type_name_lower:
            unit = "°C"
            info["temperature"] = current_value
        elif "co2" in sensor_type_name_lower:
            unit = "ppm"
            info["co2"] = current_value
        elif "влаж" in sensor_type_name_lower:
            unit = "%"
            info["humidity"] = current_value
        elif "включение света" in sensor_type_name_lower or "свет" == sensor_type_name_lower:
            info["light_on"] = bool(current_value)
            display_value = "Включен" if current_value else "Выключен"
        elif "освещ" in sensor_type_name_lower:
            unit = "лк"
            if info["light_on"] is None and current_value is not None:
                info["light_on"] = current_value > 0
        elif "кондиционер" in sensor_type_name_lower:
            info["conditioner_on"] = bool(current_value)
            display_value = "Включен" if current_value else "Выключен"

        if isinstance(display_value, float):
            display_value = round(display_value, 1)

        if isinstance(display_value, (int, float)) and unit:
            display_value = f"{display_value} {unit}"

        info["sensor_cards"].append({
            "name": sensor.name,
            "type": sensor_type_name,
            "status": sensor.get_status_display(),
            "is_working": sensor.is_working,
            "value": display_value,
        })

    if info["conditioner_on"] is None:
        if room.conditioners > 0 and info["temperature"] is not None:
            info["conditioner_on"] = info["temperature"] >= 24
            info["notes"].append("Состояние кондиционера вычислено по температуре, отдельного датчика нет.")
        elif room.conditioners > 0:
            info["notes"].append("Есть кондиционер, но отдельного датчика его состояния нет.")
        else:
            info["conditioner_on"] = False

    if latest_updated:
        info["updated_at"] = latest_updated.strftime("%d.%m.%Y %H:%M")

    return info


def extract_day_pairs_from_teacher_schedule(schedule, target_date):
    weekday_key = get_weekday_key(target_date)
    lessons = (schedule or {}).get(weekday_key) or {}
    result = []

    for number, pairs in lessons.items():
        if not pairs:
            continue

        filtered_pairs = []
        for pair in pairs:
            if date_overlaps_pair(pair, target_date):
                filtered_pairs.append(pair)

        if filtered_pairs:
            result.append({
                "number": str(number),
                "time": PAIR_TIMES.get(str(number), ""),
                "items": filtered_pairs,
            })

    result.sort(key=lambda item: int(item["number"]))
    return weekday_key, result


def build_lesson_uid(pair_number, subject_name, room_name, group_name):
    return "|".join([
        str(pair_number).strip(),
        (subject_name or "").strip(),
        (room_name or "").strip(),
        (group_name or "").strip(),
    ])


def normalize_current_day_pairs(day_pairs, selected_time, selected_uid=None):
    normalized = []
    active_lesson = None
    selected_lesson = None

    for pair_block in day_pairs:
        pair_is_active = time_in_pair(selected_time, pair_block["number"])

        for pair in pair_block["items"]:
            rooms = pair.get("rooms") or []
            teachers = pair.get("teachers") or []
            room_numbers = [room.get("number") for room in rooms if room.get("number")]
            teacher_names = [teacher.get("full_name") for teacher in teachers if teacher.get("full_name")]
            group_name = ((pair.get("group") or {}).get("number") or "").strip()
            first_room = room_numbers[0] if room_numbers else ""
            subject_name = ((pair.get("subject") or {}).get("name") or "").strip()
            uid = build_lesson_uid(pair_block["number"], subject_name, first_room, group_name)
            item = {
                "uid": uid,
                "lesson_number": pair_block["number"],
                "time": pair_block["time"],
                "subject_name": subject_name,
                "subject_type": ((pair.get("subject_type") or {}).get("type") or "").strip(),
                "location_name": ((pair.get("location") or {}).get("name") or "").strip(),
                "rooms": room_numbers,
                "teachers": teacher_names,
                "group": group_name,
                "date_range": format_date_range(pair["start_date"], pair["end_date"]),
                "is_active": pair_is_active,
                "is_selected": False,
            }
            normalized.append(item)
            if pair_is_active and active_lesson is None:
                active_lesson = item
            if selected_uid and uid == selected_uid and selected_lesson is None:
                selected_lesson = item

    if selected_lesson is None:
        selected_lesson = active_lesson or (normalized[0] if normalized else None)

    if selected_lesson:
        selected_lesson["is_selected"] = True
        for lesson in normalized:
            if lesson["uid"] == selected_lesson["uid"]:
                lesson["is_selected"] = True

    return normalized, active_lesson, selected_lesson


def find_room_occupancy(lessons, room_name, selected_time, default_teacher):
    if not room_name:
        return {
            "status": "Кабинет не выбран",
            "teacher": "—",
            "subject": "—",
            "group": "—",
            "lesson_number": "—",
            "time": "—",
        }

    for lesson in lessons:
        if lesson["is_active"] and room_name in lesson["rooms"]:
            return {
                "status": "Занят",
                "teacher": default_teacher,
                "subject": lesson["subject_name"],
                "group": lesson["group"] or "—",
                "lesson_number": lesson["lesson_number"],
                "time": lesson["time"],
            }

    return {
        "status": "Свободен",
        "teacher": "Нет занятия",
        "subject": "—",
        "group": "—",
        "lesson_number": "—",
        "time": selected_time.strftime("%H:%M"),
    }




def get_teacher_full_names():
    names = []
    seen = set()
    for profile in UserProfile.objects.select_related("user").filter(role="teacher"):
        full_name = (profile.get_full_name() or "").strip()
        if full_name and full_name not in seen:
            seen.add(full_name)
            names.append(full_name)
    return names


def find_room_booking_for_pair(target_date, pair_number, room_name):
    if not room_name or not pair_number:
        return {
            "status": "Свободен",
            "teacher": "Нет занятия",
            "subject": "—",
            "group": "—",
            "lesson_number": str(pair_number or "—"),
            "time": PAIR_TIMES.get(str(pair_number), "—"),
        }

    normalized_room = normalize_room(room_name)
    api = APIClient()

    for teacher_name in get_teacher_full_names():
        data = api.get_schedule_by_teacher(teacher_name)
        teacher_schedule = deduplicate_schedule((data or {}).get("result") or {})
        _, day_pairs = extract_day_pairs_from_teacher_schedule(teacher_schedule, target_date)

        for pair_block in day_pairs:
            if str(pair_block["number"]) != str(pair_number):
                continue

            for pair in pair_block["items"]:
                room_numbers = [
                    (room.get("number") or "").strip()
                    for room in (pair.get("rooms") or [])
                    if (room.get("number") or "").strip()
                ]
                if any(normalize_room(room_number) == normalized_room for room_number in room_numbers):
                    return {
                        "status": "Занят",
                        "teacher": teacher_name,
                        "subject": ((pair.get("subject") or {}).get("name") or "").strip() or "—",
                        "group": ((pair.get("group") or {}).get("number") or "").strip() or "—",
                        "lesson_number": str(pair_block["number"]),
                        "time": pair_block.get("time") or PAIR_TIMES.get(str(pair_block["number"]), "—"),
                    }

    return {
        "status": "Свободен",
        "teacher": "Нет занятия",
        "subject": "—",
        "group": "—",
        "lesson_number": str(pair_number or "—"),
        "time": PAIR_TIMES.get(str(pair_number), "—"),
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
    selected_date = request.GET.get("date", "").strip()

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

    selected_date_obj = parse_date_or_none(selected_date)

    if selected_date_obj:
        date_from_obj = selected_date_obj
        date_to_obj = selected_date_obj
        selected_day = get_weekday_key(selected_date_obj)
    elif initial_open:
        default_date_from, default_date_to = get_default_week_range()
        date_from_obj = default_date_from
        date_to_obj = default_date_to
    else:
        date_from_obj = parse_date_or_none(raw_date_from)
        date_to_obj = parse_date_or_none(raw_date_to)

    date_from = date_from_obj.strftime("%Y-%m-%d") if date_from_obj else ""
    date_to = date_to_obj.strftime("%Y-%m-%d") if date_to_obj else ""

    schedule = None
    warning = None

    today_index = datetime.datetime.today().weekday()
    days_map = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    today = days_map[today_index]

    api = APIClient()
    data = None

    if teacher:
        data = api.get_schedule_by_teacher(teacher)
    elif group:
        data = api.get_schedule(group)

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
                            if (pair.get("group") or {}).get("number") == group
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

    return render(request, "schedule.html", {
        "schedule": prepared_schedule,
        "group": group,
        "teacher": teacher,
        "today": today,
        "selected_day": selected_day,
        "selected_date": selected_date,
        "warning": warning,
        "date_from": date_from,
        "date_to": date_to,
    })


@teacher_required
def current_day_view(request):
    profile = getattr(request.user, "profile", None)
    teacher = profile.get_full_name() if profile else request.user.username

    today = datetime.date.today()
    now = datetime.datetime.now()

    selected_date_raw = request.GET.get("date", today.strftime("%Y-%m-%d")).strip()
    selected_pair_number = request.GET.get("pair", "").strip()
    selected_room = request.GET.get("room", "").strip()

    selected_date = parse_date_or_none(selected_date_raw) or today

    api = APIClient()
    data = api.get_schedule_by_teacher(teacher)
    teacher_schedule = data.get("result") if data else {}
    teacher_schedule = deduplicate_schedule(teacher_schedule)

    selected_time = now.time().replace(second=0, microsecond=0) if selected_date == today else datetime.time(9, 0)
    weekday_key, day_pairs = extract_day_pairs_from_teacher_schedule(teacher_schedule, selected_date)
    normalized_schedule, active_lesson, _ = normalize_current_day_pairs(day_pairs, selected_time, None)

    if not selected_pair_number:
        if active_lesson:
            selected_pair_number = active_lesson["lesson_number"]
        elif normalized_schedule:
            selected_pair_number = normalized_schedule[0]["lesson_number"]

    selected_lesson = None
    for lesson in normalized_schedule:
        is_selected = lesson["lesson_number"] == str(selected_pair_number)
        lesson["is_selected"] = is_selected
        if is_selected and selected_lesson is None:
            selected_lesson = lesson

    if selected_lesson and not selected_room and selected_lesson["rooms"]:
        selected_room = selected_lesson["rooms"][0]
    elif active_lesson and not selected_room and active_lesson["rooms"]:
        selected_room = active_lesson["rooms"][0]

    room = get_room_object(selected_room)
    room_info = build_room_state(room)

    occupancy = find_room_booking_for_pair(selected_date, selected_pair_number, selected_room)
    room_schedule_status = occupancy["status"]
    room_teacher_now = occupancy["teacher"]
    room_subject_now = occupancy["subject"]
    room_group_now = occupancy["group"]
    room_pair_now = occupancy["lesson_number"]
    room_time_now = occupancy["time"]

    page_warning = None
    current_pair_message = ""
    if not normalized_schedule:
        page_warning = "На выбранную дату у преподавателя занятий не найдено."
    elif selected_date == today and active_lesson is None:
        current_pair_message = "На данный момент пары нет."

    context = {
        "teacher": teacher,
        "selected_date": selected_date.strftime("%Y-%m-%d"),
        "selected_room": selected_room,
        "selected_pair_number": str(selected_pair_number or ""),
        "selected_day_label": DAY_LABELS.get(weekday_key, weekday_key),
        "today_label": today.strftime("%d.%m.%Y"),
        "now_time": now.strftime("%H:%M"),
        "schedule": normalized_schedule,
        "active_lesson": active_lesson,
        "selected_lesson": selected_lesson,
        "room_info": room_info,
        "room_schedule_status": room_schedule_status,
        "room_teacher_now": room_teacher_now,
        "room_subject_now": room_subject_now,
        "room_group_now": room_group_now,
        "room_pair_now": room_pair_now,
        "room_time_now": room_time_now,
        "warning": page_warning,
        "current_pair_message": current_pair_message,
    }
    return render(request, "current_day.html", context)



def get_global_room_day_lessons(target_date, room_name):
    normalized_room = normalize_room(room_name)
    if not normalized_room:
        return []

    api = APIClient()
    lessons = []
    seen = set()

    for teacher_name in get_teacher_full_names():
        data = api.get_schedule_by_teacher(teacher_name)
        teacher_schedule = deduplicate_schedule((data or {}).get("result") or {})
        _, day_pairs = extract_day_pairs_from_teacher_schedule(teacher_schedule, target_date)

        for pair_block in day_pairs:
            pair_number = str(pair_block["number"])
            pair_time = pair_block.get("time") or PAIR_TIMES.get(pair_number, "")
            for pair in pair_block["items"]:
                room_numbers = [
                    (room.get("number") or "").strip()
                    for room in (pair.get("rooms") or [])
                    if (room.get("number") or "").strip()
                ]
                if not any(normalize_room(room_value) == normalized_room for room_value in room_numbers):
                    continue

                subject_name = ((pair.get("subject") or {}).get("name") or "").strip()
                group_name = ((pair.get("group") or {}).get("number") or "").strip()
                location_name = ((pair.get("location") or {}).get("name") or "").strip()
                subject_type = ((pair.get("subject_type") or {}).get("type") or "").strip()
                first_room = next((room_value for room_value in room_numbers if normalize_room(room_value) == normalized_room), room_numbers[0] if room_numbers else room_name)
                uid = build_lesson_uid(pair_number, subject_name, first_room, group_name)
                key = (pair_number, subject_name, group_name, first_room, teacher_name, pair.get("start_date"), pair.get("end_date"))
                if key in seen:
                    continue
                seen.add(key)

                lessons.append({
                    "uid": uid,
                    "lesson_number": pair_number,
                    "time": pair_time,
                    "subject_name": subject_name,
                    "subject_type": subject_type,
                    "location_name": location_name,
                    "rooms": room_numbers,
                    "teachers": [teacher_name],
                    "teacher": teacher_name,
                    "group": group_name,
                    "date_range": format_date_range(pair["start_date"], pair["end_date"]),
                    "is_active": False,
                    "is_selected": False,
                })

    lessons.sort(key=lambda item: int(item.get("lesson_number") or 0))
    return lessons



def build_room_day_timeline(room_name, lessons, selected_pair_number, active_pair_number):
    slots = []
    selected_slot = None
    active_slot = None
    normalized_room = normalize_room(room_name)

    for pair_number, slot_time in PAIR_TIMES.items():
        matched = [
            lesson for lesson in lessons
            if lesson["lesson_number"] == str(pair_number)
            and any(normalize_room(room) == normalized_room for room in lesson["rooms"])
        ]
        first = matched[0] if matched else None
        is_active = str(active_pair_number or "") == str(pair_number)
        is_selected = str(selected_pair_number or "") == str(pair_number)

        slot = {
            "pair_number": str(pair_number),
            "time": slot_time,
            "is_active": is_active,
            "is_selected": is_selected,
            "is_busy": bool(first),
            "teacher": (first.get("teacher") or "—") if first else "—",
            "subject": first["subject_name"] if first else "Свободно",
            "group": first["group"] if first and first.get("group") else "—",
            "lesson": first,
        }
        slots.append(slot)

        if is_active:
            active_slot = slot
        if is_selected:
            selected_slot = slot

    if selected_slot is None:
        selected_slot = active_slot
    if selected_slot is None:
        selected_slot = next((slot for slot in slots if slot["is_busy"]), None)
    if selected_slot is None and slots:
        selected_slot = slots[0]

    if selected_slot:
        for slot in slots:
            if slot["pair_number"] == selected_slot["pair_number"]:
                slot["is_selected"] = True

    return slots, active_slot, selected_slot


@teacher_required
def rooms_view(request):
    profile = getattr(request.user, "profile", None)
    teacher = profile.get_full_name() if profile else request.user.username

    today = datetime.date.today()
    now = datetime.datetime.now()

    selected_date_raw = request.GET.get("date", today.strftime("%Y-%m-%d")).strip()
    selected_room = request.GET.get("room", "").strip()
    selected_pair_number = request.GET.get("pair", "").strip()

    selected_date = parse_date_or_none(selected_date_raw) or today

    all_rooms = list(Room.objects.order_by("name").values_list("name", flat=True))

    api = APIClient()
    data = api.get_schedule_by_teacher(teacher)
    teacher_schedule = data.get("result") if data else {}
    teacher_schedule = deduplicate_schedule(teacher_schedule)

    selected_time = now.time().replace(second=0, microsecond=0) if selected_date == today else datetime.time(9, 0)
    weekday_key, day_pairs = extract_day_pairs_from_teacher_schedule(teacher_schedule, selected_date)
    normalized_schedule, active_lesson, _ = normalize_current_day_pairs(day_pairs, selected_time, None)
    active_pair_number = active_lesson["lesson_number"] if active_lesson else ""

    room_names_from_schedule = sorted({room for lesson in normalized_schedule for room in lesson["rooms"] if room})
    available_rooms = []
    seen = set()
    for room_name in room_names_from_schedule + all_rooms:
        room_name = (room_name or "").strip()
        room_key = normalize_room(room_name)
        if room_name and room_key not in seen:
            seen.add(room_key)
            available_rooms.append(room_name)

    if not selected_room:
        selected_room = room_names_from_schedule[0] if room_names_from_schedule else (all_rooms[0] if all_rooms else "")

    room_day_lessons = get_global_room_day_lessons(selected_date, selected_room)
    timeline, active_slot, selected_slot = build_room_day_timeline(
        selected_room,
        room_day_lessons,
        selected_pair_number,
        active_pair_number,
    )

    room = get_room_object(selected_room)
    room_info = build_room_state(room)

    selected_lesson = selected_slot["lesson"] if selected_slot else None

    occupancy = find_room_booking_for_pair(selected_date, selected_slot["pair_number"] if selected_slot else selected_pair_number, selected_room)
    room_schedule_status = occupancy["status"]
    room_teacher_now = occupancy["teacher"]
    room_subject_now = occupancy["subject"]
    room_group_now = occupancy["group"]
    room_pair_now = occupancy["lesson_number"]
    room_time_now = occupancy["time"]

    page_warning = None
    if not available_rooms:
        page_warning = "Для преподавателя пока не найдено ни одного кабинета в расписании или локальной базе."
    elif not timeline:
        page_warning = "Не удалось собрать шкалу пар для кабинета."

    context = {
        "teacher": teacher,
        "selected_date": selected_date.strftime("%Y-%m-%d"),
        "selected_room": selected_room,
        "selected_pair_number": selected_slot["pair_number"] if selected_slot else "",
        "selected_day_label": DAY_LABELS.get(weekday_key, weekday_key),
        "now_time": now.strftime("%H:%M"),
        "available_rooms": available_rooms,
        "room_timeline": timeline,
        "selected_room_slot": selected_slot,
        "active_room_slot": active_slot,
        "selected_lesson": selected_lesson,
        "room_info": room_info,
        "room_schedule_status": room_schedule_status,
        "room_teacher_now": room_teacher_now,
        "room_subject_now": room_subject_now,
        "room_group_now": room_group_now,
        "room_pair_now": room_pair_now,
        "room_time_now": room_time_now,
        "warning": page_warning,
    }
    return render(request, "rooms.html", context)
