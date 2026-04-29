import os
import requests
from dotenv import load_dotenv

load_dotenv()


class WeatherService:
    def __init__(self):
        self.api_key = os.getenv("OPENWEATHER_API_KEY")
        self.city = "Moscow"

    def get_current_weather(self):
        if not self.api_key:
            return {
                "temperature": 20,
                "weather_main": "clear",
                "wind_speed": 2,
            }

        url = "https://api.openweathermap.org/data/2.5/weather"

        params = {
            "q": self.city,
            "appid": self.api_key,
            "units": "metric",
            "lang": "ru",
        }

        try:
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()

            return {
                "temperature": data["main"]["temp"],
                "weather_main": data["weather"][0]["main"].lower(),
                "wind_speed": data["wind"]["speed"],
            }

        except requests.RequestException:
            return {
                "temperature": 20,
                "weather_main": "clear",
                "wind_speed": 2,
            }