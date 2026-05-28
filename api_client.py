import os
from urllib.parse import quote

from dotenv import load_dotenv
import requests

load_dotenv()


class APIClient:
    def __init__(self):
        self.base_url = "http://89.39.121.218:8085/raspyx/api/v2"
        self.auth_base_url = "http://89.39.121.218:8081/auth/api/v1/login"

        self.token = os.getenv("ACCESS_TOKEN")
        self.username = os.getenv("API_USERNAME")
        self.password = os.getenv("API_PASSWORD")

        self.session = requests.Session()

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Origin": "https://zefixed.ru",
            "Referer": "https://zefixed.ru/"
        }

    def login(self):
        response = self.session.post(
            self.auth_base_url,  
            json={
                "username": self.username,
                "password": self.password,
            },
            headers={
                "accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Origin": "https://zefixed.ru",
                "Referer": "https://zefixed.ru/",
            }
        )

        if response.status_code == 200:
            data = response.json()
            self.token = data.get("result", {}).get("access_token")
            if self.token:
                self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            return True

        print("Ошибка логина:", response.status_code)
        print(response.text)
        return False

    def _get_with_relogin(self, url):
        response = self.session.get(url, headers=self.get_headers())


        if response.status_code == 200:
            return response.json()

        if response.status_code == 401:
            print("Access token истёк или недействителен. Пробую заново логиниться...")

            if self.login():
                response = self.session.get(url, headers=self.get_headers())
                if response.status_code == 200:
                    return response.json()

            print("Ошибка после повторного логина:", response.status_code)
            print(response.text)
            return None

        print("Ошибка:", response.status_code)
        print(response.text)
        return None

    def get_schedule(self, group):
        return self._get_with_relogin(
            f"{self.base_url}/schedule/group_number/{quote(str(group), safe='')}"
        )

    def get_schedule_by_teacher(self, teacher_fio):
        return self._get_with_relogin(
            f"{self.base_url}/schedule/teacher_fio/{quote(teacher_fio, safe='')}"
        )