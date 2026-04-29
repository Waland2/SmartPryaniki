from .models import Sensor
from .climate_rules import build_comfort_summary


TEMPERATURE_SENSOR_NAMES = {
    "температура",
    "температурный датчик",
}

HUMIDITY_SENSOR_NAMES = {
    "влажность",
    "влажность воздуха",
    "датчик влажности",
    "относительная влажность",
}

CO2_SENSOR_NAMES = {
    "co2",
    "co₂",
    "углекислый газ",
    "диоксид углерода",
}


def _normalize_sensor_type_name(name):
    return (name or "").strip().lower()


def get_room_sensor_value(room, allowed_names):
    sensors = (
        Sensor.objects
        .select_related("sensor_type")
        .filter(room=room, status="active")
        .order_by("-last_updated")
    )

    for item in sensors:
        sensor_type_name = _normalize_sensor_type_name(item.sensor_type.name)
        if sensor_type_name in allowed_names:
            return item.last_value

    return None


def get_room_climate_snapshot(room):
    temperature = get_room_sensor_value(room, TEMPERATURE_SENSOR_NAMES)
    humidity = get_room_sensor_value(room, HUMIDITY_SENSOR_NAMES)
    co2 = get_room_sensor_value(room, CO2_SENSOR_NAMES)

    summary = build_comfort_summary(
        temperature_value=temperature,
        humidity_value=humidity,
        co2_value=co2,
    )

    return {
        "room": room,
        "temperature": temperature,
        "humidity": humidity,
        "co2": co2,
        "summary": summary,
    }