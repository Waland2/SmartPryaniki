import datetime

from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import moderator_or_admin_required
from .models import Room, SensorData
from api_client import APIClient


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
    group = request.GET.get("group")
    teacher = request.GET.get("teacher")
    selected_day = request.GET.get("day")

    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

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

        if (date_from or date_to) and schedule:
            filtered_schedule = {}

            for day, lessons in schedule.items():
                if not lessons:
                    continue

                new_lessons = {}

                for number, pairs in lessons.items():
                    if pairs:
                        filtered_pairs = []

                        for pair in pairs:
                            start = datetime.datetime.strptime(pair["start_date"], "%Y-%m-%d")
                            end = datetime.datetime.strptime(pair["end_date"], "%Y-%m-%d")

                            ok = True

                            if date_from:
                                df = datetime.datetime.strptime(date_from, "%Y-%m-%d")
                                if end < df:
                                    ok = False

                            if date_to:
                                dt = datetime.datetime.strptime(date_to, "%Y-%m-%d")
                                if start > dt:
                                    ok = False

                            if ok:
                                filtered_pairs.append(pair)

                        if filtered_pairs:
                            new_lessons[number] = filtered_pairs

                if new_lessons:
                    filtered_schedule[day] = new_lessons

            schedule = filtered_schedule

        if selected_day and schedule:
            schedule = {selected_day: schedule.get(selected_day)}

    return render(request, "schedule.html", {
        "schedule": schedule,
        "group": group,
        "teacher": teacher,
        "today": today,
        "selected_day": selected_day,
        "warning": warning,
        "date_from": date_from,
        "date_to": date_to
    })