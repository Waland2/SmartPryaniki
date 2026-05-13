from .climate_rules import is_bad_weather_for_ventilation
from .climate_services import get_room_climate_snapshot
from .models import ClimateActionLog


def choose_climate_action(snapshot, outdoor_weather):
    temperature = snapshot.get("temperature")
    summary = snapshot.get("summary") or {}

    too_hot = summary.get("too_hot", False)
    too_cold = summary.get("too_cold", False)
    needs_ventilation = summary.get("needs_ventilation", False)

    outdoor_temp = None
    if outdoor_weather:
        outdoor_temp = outdoor_weather.get("temperature")

    ventilation_allowed = not is_bad_weather_for_ventilation(outdoor_weather)

    if too_hot:
        if (
            ventilation_allowed
            and outdoor_temp is not None
            and temperature is not None
            and outdoor_temp < temperature
        ):
            return {
                "action": "ventilation",
                "reason": "В аудитории жарко, снаружи прохладнее, проветривание разрешено",
            }

        return {
            "action": "conditioner_cool",
            "reason": "В аудитории жарко, проветривание не подходит, включаем охлаждение",
        }

    if too_cold:
        if (
            ventilation_allowed
            and outdoor_temp is not None
            and temperature is not None
            and outdoor_temp > temperature
        ):
            return {
                "action": "ventilation",
                "reason": "В аудитории холодно, но снаружи теплее и можно проветривать",
            }

        return {
            "action": "conditioner_heat",
            "reason": "В аудитории холодно, включаем обогрев",
        }

    if needs_ventilation:
        if ventilation_allowed:
            return {
                "action": "ventilation",
                "reason": "Повышен CO2, проветривание разрешено",
            }

        return {
            "action": "none",
            "reason": "Повышен CO2, но проветривание запрещено погодными условиями",
        }

    return {
        "action": "none",
        "reason": "Показатели микроклимата в норме, окно закрыто, кондиционер выключен",
    }


def apply_climate_action(room, decision):
    action = decision["action"]
    active_conditioners = room.conditioner_set.filter(status="active")

    if action == "ventilation":
        room.window_open = True
        room.save(update_fields=["window_open"])
        active_conditioners.update(
            enabled=False,
            mode="off",
            target_temperature=None,
        )
        return

    if action == "conditioner_cool":
        room.window_open = False
        room.save(update_fields=["window_open"])
        active_conditioners.update(
            enabled=True,
            mode="cool",
            target_temperature=22,
        )
        return

    if action == "conditioner_heat":
        room.window_open = False
        room.save(update_fields=["window_open"])
        active_conditioners.update(
            enabled=True,
            mode="heat",
            target_temperature=22,
        )
        return

    room.window_open = False
    room.save(update_fields=["window_open"])
    active_conditioners.update(
        enabled=False,
        mode="off",
        target_temperature=None,
    )


def prepare_room_for_lesson(room, lesson, outdoor_weather=None):
    room.simulate_sensors()
    snapshot = get_room_climate_snapshot(room)

    decision = choose_climate_action(snapshot, outdoor_weather)
    apply_climate_action(room, decision)

    temperature = snapshot.get("temperature")
    humidity = snapshot.get("humidity")
    co2 = snapshot.get("co2")

    outdoor_temp = None
    weather_main = None
    wind_speed = None

    if outdoor_weather:
        outdoor_temp = outdoor_weather.get("temperature")
        weather_main = outdoor_weather.get("weather_main")
        wind_speed = outdoor_weather.get("wind_speed")

    full_reason = (
        f"Температура в кабинете: {temperature} °C; "
        f"Влажность: {humidity} %; "
        f"CO2: {co2} ppm; "
        f"Температура на улице: {outdoor_temp} °C; "
        f"Погода: {weather_main}; "
        f"Ветер: {wind_speed} м/с. "
        f"Решение системы: {decision['reason']}"
    )

    ClimateActionLog.objects.create(
        room=room,
        lesson_date=lesson.lesson_date,
        lesson_time=lesson.start_time,
        action=decision["action"],
        reason=full_reason,
    )

    return {
        "status": "ok",
        "snapshot": snapshot,
        "decision": decision,
        "reason": full_reason,
    }