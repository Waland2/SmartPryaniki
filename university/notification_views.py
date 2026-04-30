import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Room, SensorData, TeacherNotification

PAIR_START_TIMES = {
    "1": "09:00",
    "2": "10:40",
    "3": "12:20",
    "4": "14:30",
    "5": "16:10",
    "6": "17:50",
}

PAIR_TIME_RANGES = {
    "1": ("09:00", "10:30"),
    "2": ("10:40", "12:10"),
    "3": ("12:20", "13:50"),
    "4": ("14:30", "16:00"),
    "5": ("16:10", "17:40"),
    "6": ("17:50", "19:20"),
}


def get_manual_time_limits(notification):
    lesson_number = str(notification.lesson_number)
    start_str, end_str = PAIR_TIME_RANGES.get(lesson_number, ("09:00", "10:30"))

    lesson_start = datetime.datetime.combine(
        notification.lesson_date,
        datetime.datetime.strptime(start_str, "%H:%M").time(),
    )

    lesson_end = datetime.datetime.combine(
        notification.lesson_date,
        datetime.datetime.strptime(end_str, "%H:%M").time(),
    )

    preparation_start = lesson_start - datetime.timedelta(minutes=10)

    return {
        "preparation_start": preparation_start.strftime("%H:%M"),
        "lesson_start": lesson_start.strftime("%H:%M"),
        "lesson_end": lesson_end.strftime("%H:%M"),
    }


def is_time_in_range(value, start, end):
    if not value:
        return True

    value_time = datetime.datetime.strptime(value, "%H:%M").time()
    start_time = datetime.datetime.strptime(start, "%H:%M").time()
    end_time = datetime.datetime.strptime(end, "%H:%M").time()

    return start_time <= value_time <= end_time


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


def get_room_sensor_capabilities(room):
    capabilities = {
        "temperature": False,
        "humidity": False,
        "light": False,
        "conditioner": False,
        "co2": False,
        "windows": False,
    }

    if room is None:
        return capabilities

    capabilities["conditioner"] = getattr(room, "conditioners", 0) > 0
    capabilities["windows"] = getattr(room, "windows", 0) > 0

    sensors = room.sensor_set.select_related("sensor_type").all()

    for sensor in sensors:
        sensor_type_name = ((sensor.sensor_type.name if sensor.sensor_type else "") or "").lower()
        full_name = f"{sensor_type_name} {sensor.name}".lower()

        if "темп" in full_name:
            capabilities["temperature"] = True
        elif "влаж" in full_name:
            capabilities["humidity"] = True
        elif "свет" in full_name:
            capabilities["light"] = True
        elif "co2" in full_name or "угле" in full_name:
            capabilities["co2"] = True

    return capabilities


def calculate_preparation_time(notification, room):
    lesson_number = str(notification.lesson_number)
    lesson_start_str = PAIR_START_TIMES.get(lesson_number)

    if not lesson_start_str:
        return {
            "start": "Не удалось определить",
            "end": "Не удалось определить",
            "duration": "Не удалось определить",
            "note": "Не удалось определить время начала пары.",
        }

    lesson_start = datetime.datetime.combine(
        notification.lesson_date,
        datetime.datetime.strptime(lesson_start_str, "%H:%M").time(),
    )

    required_minutes = 10

    if room:
        if room.chairs >= 30:
            required_minutes += 3

        if room.computers >= 10:
            required_minutes += 2

        if room.conditioners == 1:
            required_minutes += 2
        elif room.conditioners >= 2:
            required_minutes -= 2

    if required_minutes < 5:
        required_minutes = 5

    before_lesson_minutes = min(required_minutes, 10)
    after_lesson_minutes = max(required_minutes - 10, 0)

    if after_lesson_minutes > 5:
        after_lesson_minutes = 5

    preparation_start = lesson_start - datetime.timedelta(minutes=before_lesson_minutes)
    preparation_end = lesson_start + datetime.timedelta(minutes=after_lesson_minutes)

    if after_lesson_minutes > 0:
        note = (
            f"Подготовка начнётся на перемене за {before_lesson_minutes} минут до пары "
            f"и завершится в первые {after_lesson_minutes} минут занятия."
        )
    else:
        note = f"Подготовка полностью завершится до начала пары за {before_lesson_minutes} минут."

    return {
        "start": preparation_start.strftime("%H:%M"),
        "end": preparation_end.strftime("%H:%M"),
        "duration": f"{before_lesson_minutes + after_lesson_minutes} минут",
        "note": note,
    }


def apply_manual_environment_settings(notification, cleaned_settings):
    room = get_room_by_name(notification.room_name)

    if room is None:
        return False, "Кабинет не найден в локальной БД."

    sensors = room.sensor_set.select_related("sensor_type").all()
    changed = 0

    desired_temp = cleaned_settings.get("temperature")
    desired_humidity = cleaned_settings.get("humidity")
    light_on = cleaned_settings.get("light_on")
    light_level = cleaned_settings.get("light_level")
    conditioner_on = cleaned_settings.get("conditioner_on")
    window_state = cleaned_settings.get("window_state")
    algorithm_for_missing = cleaned_settings.get("algorithm_for_missing")
    conditioner_start = cleaned_settings.get("conditioner_start")
    conditioner_end = cleaned_settings.get("conditioner_end")
    window_start = cleaned_settings.get("window_start")
    window_end = cleaned_settings.get("window_end")
    light_start = cleaned_settings.get("light_start")
    light_end = cleaned_settings.get("light_end")

    for sensor in sensors:
        sensor_type_name = ((sensor.sensor_type.name if sensor.sensor_type else "") or "").lower()
        full_name = f"{sensor_type_name} {sensor.name}".lower()
        new_value = None

        if desired_temp is not None and "темп" in full_name:
            new_value = float(desired_temp)

        elif desired_humidity is not None and "влаж" in full_name:
            new_value = float(desired_humidity)

        elif "свет" in full_name:
            new_value = float(light_level if light_on and light_level is not None else 0)
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
    payload.pop("algorithm_result", None)
    payload.pop("manual_settings", None)

    manual_settings = {
        "temperature": str(desired_temp) if desired_temp is not None else "",
        "humidity": str(desired_humidity) if desired_humidity is not None else "",
        "light_on": bool(light_on),
        "light_level": light_level if light_on and light_level is not None else 0,
        "conditioner_on": bool(conditioner_on),
        "window_state": window_state,
        "algorithm_for_missing": bool(algorithm_for_missing),
        "missing_handled_by_algorithm": [],
        "applied_sensor_count": changed,
        "room_conditioners": getattr(room, "conditioners", 0),
        "room_windows": getattr(room, "windows", 0),
        "room_computers": getattr(room, "computers", 0),
        "temperature_control_by_algorithm": False,
        "conditioner_start": conditioner_start,
        "conditioner_end": conditioner_end,
        "window_start": window_start,
        "window_end": window_end,
        "light_start": light_start,
        "light_end": light_end,
        "algorithm_details": {},
    }

    if algorithm_for_missing:
        time_limits = get_manual_time_limits(notification)

        # Температура оставлена алгоритму
        if desired_temp is None:
            manual_settings["missing_handled_by_algorithm"].append("Температура")
            manual_settings["temperature"] = str(notification.recommended_temperature)
            manual_settings["algorithm_details"]["temperature"] = (
                f"Алгоритм установит температуру {notification.recommended_temperature}°C."
            )

            if getattr(room, "conditioners", 0) > 0:
                manual_settings["conditioner_on"] = True
                manual_settings["conditioner_start"] = time_limits["preparation_start"]
                manual_settings["conditioner_end"] = time_limits["lesson_start"]
                manual_settings["algorithm_details"]["temperature_control"] = (
                    f"Для достижения температуры алгоритм включит кондиционер "
                    f"в {time_limits['preparation_start']} и выключит в {time_limits['lesson_start']}."
                )

        # Влажность оставлена алгоритму
        if desired_humidity is None:
            manual_settings["missing_handled_by_algorithm"].append("Влажность")
            manual_settings["humidity"] = "45"
            manual_settings["algorithm_details"]["humidity"] = (
                "Алгоритм установит влажность 45%."
            )

        # Свет включён, но процент не указан
        if light_on and light_level is None:
            manual_settings["missing_handled_by_algorithm"].append("Освещённость")
            manual_settings["light_level"] = "80"
            manual_settings["light_start"] = time_limits["lesson_start"]
            manual_settings["light_end"] = time_limits["lesson_end"]
            manual_settings["algorithm_details"]["light"] = (
                f"Алгоритм включит свет в {time_limits['lesson_start']}, "
                f"выключит в {time_limits['lesson_end']} и установит освещённость 80%."
            )

        # Если окна не выбраны вообще — алгоритм сам решает проветрить до пары
        if not window_state and getattr(room, "windows", 0) > 0:
            manual_settings["missing_handled_by_algorithm"].append("Окна")
            manual_settings["window_state"] = "open"
            manual_settings["window_start"] = time_limits["preparation_start"]
            manual_settings["window_end"] = time_limits["lesson_start"]
            manual_settings["algorithm_details"]["windows"] = (
                f"Алгоритм откроет окна в {time_limits['preparation_start']} "
                f"и закроет в {time_limits['lesson_start']}."
            )

        # Если пользователь выбрал закрыть окна — не открываем их, а фиксируем закрытие к началу пары
        if window_state == "close":
            manual_settings["window_state"] = "close"
            manual_settings["window_start"] = ""
            manual_settings["window_end"] = time_limits["lesson_start"]
            manual_settings["algorithm_details"]["windows"] = (
                f"Окна будут закрыты к началу пары в {time_limits['lesson_start']}."
            )

        # Если пользователь указал температуру, но не выбрал способ достижения
        if desired_temp is not None and not conditioner_on and not window_state:
            manual_settings["missing_handled_by_algorithm"].append("Способ достижения температуры")
            manual_settings["temperature_control_by_algorithm"] = True

            if getattr(room, "conditioners", 0) > 0:
                manual_settings["conditioner_on"] = True
                manual_settings["conditioner_start"] = time_limits["preparation_start"]
                manual_settings["conditioner_end"] = time_limits["lesson_start"]
                manual_settings["algorithm_details"]["temperature_control"] = (
                    f"Алгоритм включит кондиционер в {time_limits['preparation_start']}, "
                    f"установит температуру {desired_temp}°C "
                    f"и выключит кондиционер в {time_limits['lesson_start']}."
                )
            elif getattr(room, "windows", 0) > 0:
                manual_settings["window_state"] = "open"
                manual_settings["window_start"] = time_limits["preparation_start"]
                manual_settings["window_end"] = time_limits["lesson_start"]
                manual_settings["algorithm_details"]["temperature_control"] = (
                    f"Алгоритм откроет окна в {time_limits['preparation_start']} "
                    f"и закроет в {time_limits['lesson_start']} "
                    f"для достижения температуры {desired_temp}°C."
                )

    payload["manual_settings"] = manual_settings

    notification.payload = payload
    notification.action_choice = "manual"
    notification.status = "dismissed"
    notification.show_popup = False
    notification.read_at = timezone.now()
    notification.action_at = timezone.now()
    notification.save(
        update_fields=[
            "payload",
            "action_choice",
            "status",
            "show_popup",
            "read_at",
            "action_at",
        ]
    )

    return True, "Ручные настройки среды сохранены."


@login_required
def notifications_page(request):
    mode = request.GET.get("mode", "active")

    today = timezone.localdate()
    max_setup_date = today + datetime.timedelta(days=7)

    date_from = request.GET.get("date_from") or ""
    date_to = request.GET.get("date_to") or ""
    room = (request.GET.get("room") or "").strip()

    base_qs = TeacherNotification.objects.filter(user=request.user)

    if mode == "hidden":
        items = base_qs.filter(
            status="dismissed",
            lesson_date__gte=today,
            lesson_date__lte=max_setup_date,
        )

    elif mode == "history":
        items = base_qs.all()

        if date_from:
            items = items.filter(lesson_date__gte=date_from)

        if date_to:
            items = items.filter(lesson_date__lte=date_to)

        if room:
            items = items.filter(room_name__icontains=room)

    else:
        items = base_qs.filter(
            lesson_date__gte=today,
            lesson_date__lte=max_setup_date,
        ).exclude(status="dismissed")

    items = items.order_by("lesson_date", "lesson_number", "-created_at")

    hidden_count = base_qs.filter(
        status="dismissed",
        lesson_date__gte=today,
        lesson_date__lte=max_setup_date,
    ).count()

    history_count = base_qs.count()

    return render(
        request,
        "notifications.html",
        {
            "notifications": items,
            "mode": mode,
            "hidden_count": hidden_count,
            "history_count": history_count,
            "date_from": date_from,
            "date_to": date_to,
            "room_filter": room,
            "today": today,
            "max_setup_date": max_setup_date,
        },
    )


@login_required
def manual_setup_form(request, pk):
    item = get_object_or_404(TeacherNotification, pk=pk, user=request.user)
    room = get_room_by_name(item.room_name)
    capabilities = get_room_sensor_capabilities(room)

    context = {
        "item": item,
        "room": room,
        "capabilities": capabilities,
        "manual_settings": (item.payload or {}).get("manual_settings", {}),
        "time_limits": get_manual_time_limits(item),
    }

    if request.method == "POST":
        temp_raw = (request.POST.get("temperature") or "").strip()
        humidity_raw = (request.POST.get("humidity") or "").strip()
        light_on = request.POST.get("light_on") == "on"
        light_level_raw = (request.POST.get("light_level") or "").strip()
        conditioner_on = request.POST.get("conditioner_on") == "on"
        window_state = request.POST.get("window_state")
        conditioner_start = request.POST.get("conditioner_start") or ""
        conditioner_end = request.POST.get("conditioner_end") or ""
        window_start = request.POST.get("window_start") or ""
        window_end = request.POST.get("window_end") or ""
        light_start = request.POST.get("light_start") or ""
        light_end = request.POST.get("light_end") or ""

        time_limits = get_manual_time_limits(item)
        algorithm_for_missing = request.POST.get("algorithm_for_missing") == "1"

        context["manual_settings"] = {
            "temperature": temp_raw,
            "humidity": humidity_raw,
            "light_on": light_on,
            "light_level": light_level_raw,
            "conditioner_on": conditioner_on,
            "window_state": window_state,
            "conditioner_start": conditioner_start,
            "conditioner_end": conditioner_end,
            "window_start": window_start,
            "window_end": window_end,
            "light_start": light_start,
            "light_end": light_end,
        }

        temperature = None
        humidity = None
        light_level = None

        try:
            if temp_raw:
                temperature = Decimal(temp_raw)
        except InvalidOperation:
            messages.error(request, "Температура указана неверно.")
            return render(request, "notification_manual_setup.html", context)

        try:
            if humidity_raw:
                humidity = Decimal(humidity_raw)
        except InvalidOperation:
            messages.error(request, "Влажность указана неверно.")
            return render(request, "notification_manual_setup.html", context)

        allowed_start = time_limits["preparation_start"]
        lesson_start = time_limits["lesson_start"]
        lesson_end = time_limits["lesson_end"]

        if conditioner_on:
            if not conditioner_start or not conditioner_end:
                messages.error(request, "Укажите время работы кондиционера.")
                return render(request, "notification_manual_setup.html", context)

            if not is_time_in_range(conditioner_start, allowed_start, lesson_end) or not is_time_in_range(conditioner_end, allowed_start, lesson_end):
                messages.error(request, "Кондиционер можно включать только за 10 минут до пары и до конца пары.")
                return render(request, "notification_manual_setup.html", context)

            if conditioner_start >= conditioner_end:
                messages.error(request, "Время выключения кондиционера должно быть позже времени включения.")
                return render(request, "notification_manual_setup.html", context)

            if window_state == "open":
                if not window_start or not window_end:
                    messages.error(request, "Укажите время открытия и закрытия окон.")
                    return render(request, "notification_manual_setup.html", context)

                if not is_time_in_range(window_start, allowed_start, lesson_end) or not is_time_in_range(window_end, allowed_start, lesson_end):
                    messages.error(request, "Окна можно открывать не раньше чем за 10 минут до пары и не позже конца пары.")
                    return render(request, "notification_manual_setup.html", context)

                if window_start >= window_end:
                    messages.error(request, "Время закрытия окон должно быть позже времени открытия.")
                    return render(request, "notification_manual_setup.html", context)

            if window_state == "close":
                window_start = ""
                window_end = lesson_start

        if light_on:
            if not light_start or not light_end:
                messages.error(request, "Укажите время работы света.")
                return render(request, "notification_manual_setup.html", context)

            if not is_time_in_range(light_start, lesson_start, lesson_end) or not is_time_in_range(light_end, lesson_start, lesson_end):
                messages.error(request, "Свет можно включать только во время пары.")
                return render(request, "notification_manual_setup.html", context)

            if light_start >= light_end:
                messages.error(request, "Время выключения света должно быть позже времени включения.")
                return render(request, "notification_manual_setup.html", context)
        if light_level_raw:
            try:
                light_level = int(light_level_raw)
            except ValueError:
                messages.error(request, "Освещённость указана неверно.")
                return render(request, "notification_manual_setup.html", context)

            if not (0 <= light_level <= 100):
                messages.error(request, "Освещённость должна быть от 0 до 100%.")
                return render(request, "notification_manual_setup.html", context)

        temp_min = item.temperature_min or Decimal("18.0")
        temp_max = item.temperature_max or Decimal("26.0")

        if temperature is not None and not (temp_min <= temperature <= temp_max):
            messages.error(
                request,
                f"Температура должна быть в диапазоне от {temp_min} до {temp_max} °C.",
            )
            return render(request, "notification_manual_setup.html", context)

        if humidity is not None and not (Decimal("30.0") <= humidity <= Decimal("70.0")):
            messages.error(request, "Влажность должна быть в диапазоне от 30 до 70%.")
            return render(request, "notification_manual_setup.html", context)

        ok, message = apply_manual_environment_settings(
            item,
            {
                "temperature": temperature,
                "humidity": humidity,
                "light_on": light_on,
                "light_level": light_level,
                "conditioner_on": conditioner_on,
                "window_state": window_state,
                "algorithm_for_missing": algorithm_for_missing,
                "conditioner_start": conditioner_start,
                "conditioner_end": conditioner_end,
                "window_start": window_start,
                "window_end": window_end,
                "light_start": light_start,
                "light_end": light_end,
            },
        )

        if ok:
            messages.success(request, message)
        else:
            messages.warning(request, message)

        return redirect("university:notifications")

    return render(request, "notification_manual_setup.html", context)


@login_required
def mark_notification_read(request, pk):
    notification = get_object_or_404(
        TeacherNotification,
        pk=pk,
        user=request.user,
    )

    notification.status = "dismissed"
    notification.show_popup = False
    notification.read_at = timezone.now()
    notification.save(update_fields=["status", "show_popup", "read_at"])

    messages.success(request, "Уведомление скрыто.")
    return redirect("university:notifications")


@login_required
def choose_algorithm_setup(request, pk):
    notification = get_object_or_404(
        TeacherNotification,
        pk=pk,
        user=request.user,
    )

    room = get_room_by_name(notification.room_name)
    capabilities = get_room_sensor_capabilities(room)
    preparation_time = calculate_preparation_time(notification, room)

    payload = notification.payload or {}
    payload.pop("manual_settings", None)
    lesson_start = preparation_time["end"]
    preparation_start = preparation_time["start"]

    payload["algorithm_result"] = {
        "temperature": (
            str(notification.recommended_temperature)
            if capabilities["temperature"]
            else "Нет датчика температуры"
        ),

        "humidity": (
            45
            if capabilities["humidity"]
            else "Нет датчика влажности"
        ),

        "light": (
            80
            if capabilities["light"]
            else ""
        ),
        "light_plan": (
            "Свет будет включён с начала пары и будет работать до конца занятия"
            if capabilities["light"]
            else "Нет управления светом"
        ),

        "conditioner": (
            f"Кондиционер включится в {preparation_start}, установит температуру "
            f"{notification.recommended_temperature}°C и будет работать до конца подготовки кабинета"
            if capabilities["conditioner"]
            else "Нет кондиционера"
        ),

        "windows": (
            f"Окна откроются в {preparation_start} для проветривания и закроются к началу пары в {lesson_start}"
            if capabilities["windows"]
            else "Нет окон"
        ),

        "co2": (
            "CO₂ будет контролироваться по датчику во время подготовки и занятия"
            if capabilities["co2"]
            else "Нет датчика CO₂"
        ),

        "ventilation": (
            f"Проветривание: открыть окна в {preparation_start}, закрыть окна в {lesson_start}"
            if capabilities["windows"]
            else "Проветривание недоступно, потому что в кабинете нет окон"
        ),

        "heating_or_cooling": (
            f"Температура будет достигаться кондиционером: включить в {preparation_start}, "
            f"цель — {notification.recommended_temperature}°C"
            if capabilities["conditioner"]
            else "Температура будет только контролироваться, так как кондиционер отсутствует"
        ),

        "comment": (
            "Алгоритм сформировал конкретный план подготовки кабинета: "
            "проветривание, кондиционер, свет и контроль параметров среды."
        ),

        "room_conditioners": getattr(room, "conditioners", 0) if room else 0,
        "room_windows": getattr(room, "windows", 0) if room else 0,
        "room_computers": getattr(room, "computers", 0) if room else 0,
        "room_chairs": getattr(room, "chairs", 0) if room else 0,

        "preparation_start": preparation_time["start"],
        "preparation_end": preparation_time["end"],
        "preparation_duration": preparation_time["duration"],
        "preparation_note": preparation_time["note"],
    }

    notification.payload = payload
    notification.action_choice = "algorithm"
    notification.status = "dismissed"
    notification.show_popup = False
    notification.read_at = timezone.now()
    notification.action_at = timezone.now()
    notification.save(
        update_fields=[
            "payload",
            "action_choice",
            "status",
            "show_popup",
            "read_at",
            "action_at",
        ]
    )

    messages.success(request, "Кабинет оставлен на алгоритм.")
    return redirect("university:notifications")


@login_required
def restore_notification(request, pk):
    notification = get_object_or_404(
        TeacherNotification,
        pk=pk,
        user=request.user,
    )

    notification.status = "read"
    notification.show_popup = False
    notification.save(update_fields=["status", "show_popup"])

    messages.success(request, "Уведомление возвращено в актуальные.")
    return redirect("university:notifications")