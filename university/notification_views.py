from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Room, Sensor, SensorData, TeacherNotification
from .notification_services import get_notification_feed


def normalize_room(value):
    if value is None:
        return ""
    raw = str(value).strip().lower()
    raw = raw.replace("ауд.", "").replace("ауд", "")
    raw = raw.replace(" ", "")
    if raw.startswith("пр"):
        raw = raw[2:]
    return "".join(ch for ch in raw if ch.isalnum())


def get_room_by_name(room_name):
    normalized = normalize_room(room_name)
    if not normalized:
        return None

    for room in Room.objects.prefetch_related("sensor_set__sensor_type").all():
        if normalize_room(room.name) == normalized:
            return room
    return None


def apply_manual_environment_settings(notification, cleaned_settings):
    room = get_room_by_name(notification.room_name)
    if room is None:
        return False, "Кабинет не найден в локальной БД."

    sensors = room.sensor_set.select_related("sensor_type").all()
    changed = 0

    desired_temp = cleaned_settings.get("temperature")
    desired_humidity = cleaned_settings.get("humidity")
    light_on = cleaned_settings.get("light_on")
    conditioner_on = cleaned_settings.get("conditioner_on")

    for sensor in sensors:
        sensor_type_name = ((sensor.sensor_type.name if sensor.sensor_type else "") or "").lower()
        full_name = f"{sensor_type_name} {sensor.name}".lower()
        new_value = None

        if desired_temp is not None and "темп" in full_name:
            new_value = float(desired_temp)
        elif desired_humidity is not None and "влаж" in full_name:
            new_value = float(desired_humidity)
        elif "свет" in full_name:
            new_value = 1.0 if light_on else 0.0
            sensor.status = "active" if light_on else "disabled"
        elif "конди" in full_name:
            new_value = 1.0 if conditioner_on else 0.0
            sensor.status = "active" if conditioner_on else "disabled"

        if new_value is None:
            continue

        sensor.last_value = new_value
        sensor.save(update_fields=["last_value", "status", "last_updated"])
        SensorData.objects.create(sensor=sensor, value=new_value)
        changed += 1

    payload = notification.payload or {}
    payload["manual_settings"] = {
        "temperature": str(desired_temp) if desired_temp is not None else "",
        "humidity": str(desired_humidity) if desired_humidity is not None else "",
        "light_on": bool(light_on),
        "conditioner_on": bool(conditioner_on),
        "applied": changed > 0,
    }
    notification.payload = payload
    notification.action_choice = "manual"
    notification.status = "read"
    notification.read_at = timezone.now()
    notification.action_at = timezone.now()
    notification.save(update_fields=["payload", "action_choice", "status", "read_at", "action_at"])

    if changed == 0:
        return False, "Подходящие датчики для изменения не найдены."
    return True, f"Параметры среды сохранены и применены к {changed} датчикам."


@login_required
def notifications_page(request):
    items = get_notification_feed(request.user)
    return render(request, "notifications.html", {"notifications": items})


@login_required
def manual_setup_form(request, pk):
    item = get_object_or_404(TeacherNotification, pk=pk, user=request.user)

    if request.method == "POST":
        temp_raw = (request.POST.get("temperature") or "").strip()
        humidity_raw = (request.POST.get("humidity") or "").strip()
        light_on = request.POST.get("light_on") == "on"
        conditioner_on = request.POST.get("conditioner_on") == "on"

        temperature = None
        humidity = None

        try:
            if temp_raw:
                temperature = Decimal(temp_raw)
        except InvalidOperation:
            messages.error(request, "Температура указана неверно.")
            return render(request, "notification_manual_setup.html", {"item": item})

        try:
            if humidity_raw:
                humidity = Decimal(humidity_raw)
        except InvalidOperation:
            messages.error(request, "Влажность указана неверно.")
            return render(request, "notification_manual_setup.html", {"item": item})

        temp_min = item.temperature_min or Decimal("18.0")
        temp_max = item.temperature_max or Decimal("26.0")

        if temperature is not None and not (temp_min <= temperature <= temp_max):
            messages.error(
                request,
                f"Температура должна быть в диапазоне от {temp_min} до {temp_max} °C.",
            )
            return render(request, "notification_manual_setup.html", {"item": item})

        if humidity is not None and not (Decimal("30.0") <= humidity <= Decimal("70.0")):
            messages.error(request, "Влажность должна быть в диапазоне от 30 до 70%.")
            return render(request, "notification_manual_setup.html", {"item": item})

        ok, message = apply_manual_environment_settings(
            item,
            {
                "temperature": temperature,
                "humidity": humidity,
                "light_on": light_on,
                "conditioner_on": conditioner_on,
            },
        )

        if ok:
            messages.success(request, message)
            return redirect("university:notifications")

        messages.warning(request, message)
        return redirect("university:notifications")

    return render(request, "notification_manual_setup.html", {"item": item})


@login_required
@require_POST
def mark_notification_read(request, pk):
    item = get_object_or_404(TeacherNotification, pk=pk, user=request.user)
    if item.status == "unread":
        item.status = "read"
        item.read_at = timezone.now()
        item.save(update_fields=["status", "read_at"])
    return redirect(request.POST.get("next") or "/notifications/")


@login_required
def choose_manual_setup(request, pk):
    return redirect("university:notification_manual_form", pk=pk)


@login_required
@require_POST
def choose_algorithm_setup(request, pk):
    item = get_object_or_404(TeacherNotification, pk=pk, user=request.user)
    item.action_choice = "algorithm"
    item.status = "read"
    item.read_at = timezone.now()
    item.action_at = timezone.now()
    payload = item.payload or {}
    payload["manual_settings"] = payload.get("manual_settings", {})
    payload["decision"] = "algorithm"
    item.payload = payload
    item.save(update_fields=["payload", "action_choice", "status", "read_at", "action_at"])
    messages.success(request, "Выбор сохранён: кабинет будет подготовлен алгоритмом.")
    return redirect(request.POST.get("next") or "/notifications/")
