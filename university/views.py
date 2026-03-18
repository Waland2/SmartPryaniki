from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render

from .models import Room, SensorData


@staff_member_required
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


@staff_member_required
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


@staff_member_required
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


@staff_member_required
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
