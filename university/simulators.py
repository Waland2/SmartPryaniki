import random
from dataclasses import dataclass


@dataclass
class BaseSensorSimulator:
    sensor: object

    def generate_value(self):
        return 0.0

    def normalized(self, value, digits=1):
        return round(value, digits)


class CO2SensorSimulator(BaseSensorSimulator):
    def generate_value(self):
        room = self.sensor.room
        base = 420
        people = room.chairs * random.uniform(0.2, 0.9)
        people_factor = people * random.uniform(8.0, 18.0)
        computers_factor = room.computers * random.uniform(3.0, 8.0)
        ventilation_bonus = room.windows * random.uniform(8.0, 18.0)
        conditioners_bonus = room.conditioners * random.uniform(15.0, 30.0)
        noise = random.uniform(-35.0, 40.0)
        value = base + people_factor + computers_factor - ventilation_bonus - conditioners_bonus + noise
        return max(350.0, self.normalized(value))


class TemperatureSensorSimulator(BaseSensorSimulator):
    def generate_value(self):
        room = self.sensor.room
        base = random.uniform(21.0, 24.0)
        computers_heat = room.computers * random.uniform(0.03, 0.10)
        conditioners_cool = room.conditioners * random.uniform(0.4, 1.2)
        sun_heat = room.windows * random.uniform(0.05, 0.20)
        noise = random.uniform(-0.7, 0.7)
        value = base + computers_heat + sun_heat - conditioners_cool + noise
        return max(16.0, min(31.0, self.normalized(value)))


class LightSensorSimulator(BaseSensorSimulator):
    def generate_value(self):
        room = self.sensor.room
        daylight = room.windows * random.uniform(70.0, 140.0)
        lamps = room.desks * random.uniform(1.0, 3.0)
        computers_glow = room.computers * random.uniform(2.0, 6.0)
        base = random.uniform(180.0, 260.0)
        noise = random.uniform(-40.0, 50.0)
        value = base + daylight + lamps + computers_glow + noise
        return max(50.0, self.normalized(value))


class WaterLeakSensorSimulator(BaseSensorSimulator):
    def generate_value(self):
        leak_probability = 0.03 + self.sensor.room.conditioners * 0.01
        return 1.0 if random.random() < min(leak_probability, 0.15) else 0.0


class LightSwitchSensorSimulator(BaseSensorSimulator):
    def generate_value(self):
        room = self.sensor.room
        probability = 0.45 + min(room.chairs / 100, 0.35)
        return 1.0 if random.random() < probability else 0.0


SIMULATOR_MAP = {
    'co2': CO2SensorSimulator,
    'co₂': CO2SensorSimulator,
    'углекислый газ': CO2SensorSimulator,
    'температура': TemperatureSensorSimulator,
    'температурный датчик': TemperatureSensorSimulator,
    'освещенность': LightSensorSimulator,
    'освещённость': LightSensorSimulator,
    'датчик освещенности': LightSensorSimulator,
    'датчик освещённости': LightSensorSimulator,
    'утечка воды': WaterLeakSensorSimulator,
    'датчик утечки воды': WaterLeakSensorSimulator,
    'включение света': LightSwitchSensorSimulator,
    'свет': LightSwitchSensorSimulator,
}


def get_simulator(sensor):
    sensor_type_name = sensor.sensor_type.name.strip().lower()
    simulator_class = SIMULATOR_MAP.get(sensor_type_name, BaseSensorSimulator)
    return simulator_class(sensor)