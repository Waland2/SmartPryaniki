SANPIN_LIMITS = {
    "temperature": {
        "min": 18.0,
        "max": 24.0,
    },
    "humidity": {
        "min": 40.0,
        "max": 60.0,
    },
    "co2": {
        "warning": 800.0,
        "critical": 1000.0,
    },
}

BAD_WEATHER_TYPES = {"rain", "snow", "thunderstorm", "drizzle", "hail"}
MAX_SAFE_WIND_SPEED = 10.0
MIN_OUTDOOR_TEMP_FOR_VENTILATION = 16.0


def evaluate_temperature(value):
    if value is None:
        return {"status": "no_data", "reason": "Нет данных по температуре"}

    if value < SANPIN_LIMITS["temperature"]["min"]:
        return {"status": "low", "reason": "Температура ниже нормы"}

    if value > SANPIN_LIMITS["temperature"]["max"]:
        return {"status": "high", "reason": "Температура выше нормы"}

    return {"status": "ok", "reason": "Температура в норме"}


def evaluate_humidity(value):
    if value is None:
        return {"status": "no_data", "reason": "Нет данных по влажности"}

    if value < SANPIN_LIMITS["humidity"]["min"]:
        return {"status": "low", "reason": "Влажность ниже нормы"}

    if value > SANPIN_LIMITS["humidity"]["max"]:
        return {"status": "high", "reason": "Влажность выше нормы"}

    return {"status": "ok", "reason": "Влажность в норме"}


def evaluate_co2(value):
    if value is None:
        return {"status": "no_data", "reason": "Нет данных по CO2"}

    if value >= SANPIN_LIMITS["co2"]["critical"]:
        return {"status": "critical", "reason": "Высокий CO2, выраженная духота"}

    if value >= SANPIN_LIMITS["co2"]["warning"]:
        return {"status": "warning", "reason": "CO2 повышен, желательно проветривание"}

    return {"status": "ok", "reason": "CO2 в рабочем диапазоне"}


def build_comfort_summary(temperature_value, humidity_value, co2_value):
    temperature = evaluate_temperature(temperature_value)
    humidity = evaluate_humidity(humidity_value)
    co2 = evaluate_co2(co2_value)

    needs_ventilation = co2["status"] in {"warning", "critical"}
    too_hot = temperature["status"] == "high"
    too_cold = temperature["status"] == "low"
    too_dry = humidity["status"] == "low"
    too_humid = humidity["status"] == "high"

    status = "comfortable"
    if too_cold:
        status = "cold"
    elif too_hot or needs_ventilation or too_dry or too_humid:
        status = "attention"

    return {
        "status": status,
        "temperature": temperature,
        "humidity": humidity,
        "co2": co2,
        "needs_ventilation": needs_ventilation,
        "too_hot": too_hot,
        "too_cold": too_cold,
        "too_dry": too_dry,
        "too_humid": too_humid,
    }


def is_bad_weather_for_ventilation(outdoor_weather):
    if not outdoor_weather:
        return True

    outdoor_temp = outdoor_weather.get("temperature")
    weather_main = (outdoor_weather.get("weather_main") or "").lower()
    wind_speed = outdoor_weather.get("wind_speed") or 0

    if outdoor_temp is None:
        return True

    if outdoor_temp < MIN_OUTDOOR_TEMP_FOR_VENTILATION:
        return True

    if weather_main in BAD_WEATHER_TYPES:
        return True

    if wind_speed >= MAX_SAFE_WIND_SPEED:
        return True

    return False