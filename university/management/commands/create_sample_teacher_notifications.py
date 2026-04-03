from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import UserProfile
from university.models import TeacherNotification


class Command(BaseCommand):
    help = "Создаёт примерные уведомления для конкретного преподавателя"

    def add_arguments(self, parser):
        parser.add_argument(
            "--teacher",
            type=str,
            default="Логачёв Максим Сергеевич",
            help='ФИО преподавателя, например: Логачёв Максим Сергеевич',
        )
        parser.add_argument(
            "--days-ahead",
            type=int,
            default=1,
            help="На сколько дней вперёд поставить дату занятия",
        )

    def handle(self, *args, **options):
        teacher_name = (options["teacher"] or "").strip()
        days_ahead = options["days_ahead"]

        profile = None
        for item in UserProfile.objects.select_related("user").filter(role="teacher"):
            if (item.get_full_name() or "").strip() == teacher_name:
                profile = item
                break

        if profile is None:
            raise CommandError(f'Преподаватель "{teacher_name}" не найден в локальной БД.')

        user = profile.user
        now = timezone.now()
        lesson_date = date.today() + timedelta(days=days_ahead)

        created_items = [
            TeacherNotification.objects.create(
                user=user,
                notification_type="environment_setup",
                title="Подготовка кабинета Пр1313",
                message="Завтра занятие в кабинете Пр1313. Настройте параметры среды.",
                lesson_date=lesson_date,
                lesson_number="2",
                room_name="Пр1313",
                subject_name="Программирование",
                group_name="231-329",
                recommended_temperature=22,
                temperature_min=20,
                temperature_max=24,
                action_choice="pending",
                payload={
                    "time": "10:40-12:10",
                    "manual_settings": {},
                    "source": "sample_command",
                },
                status="unread",
                show_popup=True,
                valid_from=now - timedelta(minutes=10),
                valid_until=now + timedelta(days=1),
            ),
            TeacherNotification.objects.create(
                user=user,
                notification_type="environment_setup",
                title="Подготовка кабинета Пр1315",
                message="Завтра занятие в кабинете Пр1315. Настройте параметры среды.",
                lesson_date=lesson_date,
                lesson_number="3",
                room_name="Пр1315",
                subject_name="Базы данных",
                group_name="231-329",
                recommended_temperature=21,
                temperature_min=19,
                temperature_max=24,
                action_choice="pending",
                payload={
                    "time": "12:20-13:50",
                    "manual_settings": {},
                    "source": "sample_command",
                },
                status="unread",
                show_popup=True,
                valid_from=now - timedelta(minutes=10),
                valid_until=now + timedelta(days=1),
            ),
        ]

        self.stdout.write(
            self.style.SUCCESS(
                f'Создано примерных уведомлений: {len(created_items)} для преподавателя "{teacher_name}".'
            )
        )
