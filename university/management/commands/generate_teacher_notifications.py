import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from university.models import TeacherNotification
from university.views import get_lessons_for_teacher_on_date


class Command(BaseCommand):
    help = "Автоматически создаёт уведомления преподавателям за 1 день до занятий"

    def handle(self, *args, **options):
        User = get_user_model()

        target_date = timezone.localdate() + datetime.timedelta(days=1)
        created_count = 0

        teachers = User.objects.filter(profile__role="teacher")

        for user in teachers:
            profile = getattr(user, "profile", None)

            if not profile:
                continue

            teacher_name = profile.get_full_name()

            if not teacher_name:
                continue

            lessons = get_lessons_for_teacher_on_date(teacher_name, target_date)

            for lesson in lessons:
                room_name = lesson.get("room")

                if not room_name:
                    continue

                lesson_number = str(lesson.get("lesson_number"))
                subject_name = lesson.get("subject") or "Занятие"
                group_name = lesson.get("group") or "—"

                exists = TeacherNotification.objects.filter(
                    user=user,
                    lesson_date=target_date,
                    lesson_number=lesson_number,
                    room_name=room_name,
                    subject_name=subject_name,
                    group_name=group_name,
                ).exists()

                if exists:
                    continue

                valid_from = timezone.now()

                valid_until = timezone.make_aware(
                    datetime.datetime.combine(
                        target_date,
                        datetime.time(hour=23, minute=59),
                    )
                )

                TeacherNotification.objects.create(
                    user=user,
                    notification_type="environment_setup",
                    title="Подготовка кабинета к завтрашнему занятию",
                    message=(
                        "Завтра у вас занятие. Проверьте параметры среды "
                        "и выберите ручную настройку или алгоритм."
                    ),
                    lesson_date=target_date,
                    lesson_number=lesson_number,
                    room_name=room_name,
                    subject_name=subject_name,
                    group_name=group_name,
                    recommended_temperature=22,
                    temperature_min=18,
                    temperature_max=24,
                    action_choice="pending",
                    status="unread",
                    show_popup=True,
                    valid_from=valid_from,
                    valid_until=valid_until,
                    payload={
                        "created_automatically": True,
                        "created_for_date": str(target_date),
                    },
                )

                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Создано автоматических уведомлений: {created_count}"
            )
        )