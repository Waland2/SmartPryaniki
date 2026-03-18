import os
from dotenv import load_dotenv
import requests

load_dotenv()


class APIClient:
    def __init__(self):
        self.base_url = "https://zefixed.ru/raspyx/api"
        self.token = os.getenv("ACCESS_TOKEN")

        self.session = requests.Session()

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Origin": "https://zefixed.ru",
            "Referer": "https://zefixed.ru/"
        }

    def get_schedule(self, group):
        response = self.session.get(
            f"{self.base_url}/v2/schedule/group_number/{group}",
            headers=self.get_headers()
        )

        if response.status_code == 200:
            return response.json()
        else:
            print("Ошибка:", response.status_code)
            print(response.text)
            return None

    def get_schedule_by_teacher(self, teacher_fio):
        response = self.session.get(
            f"{self.base_url}/v2/schedule/teacher_fio/{teacher_fio}",
            headers=self.get_headers()
        )

        if response.status_code == 200:
            return response.json()
        else:
            print("Ошибка:", response.status_code)
            print(response.text)
            return None