import datetime

from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import moderator_or_admin_required
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

    return render(request, "schedule.html", {
        "schedule": prepared_schedule,
        "group": group,
        "teacher": teacher,
        "today": today,
        "selected_day": selected_day,
        "warning": warning,
        "date_from": date_from,
        "date_to": date_to,
    })