from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("university", "0003_alter_sensordata_options"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TeacherNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("notification_type", models.CharField(choices=[("environment_setup", "Настройка среды"), ("preparation", "Подготовка кабинета")], default="environment_setup", max_length=32, verbose_name="Тип уведомления")),
                ("title", models.CharField(max_length=255, verbose_name="Заголовок")),
                ("message", models.TextField(verbose_name="Сообщение")),
                ("lesson_date", models.DateField(verbose_name="Дата занятия")),
                ("lesson_number", models.CharField(blank=True, max_length=8, verbose_name="Номер пары")),
                ("room_name", models.CharField(blank=True, max_length=64, verbose_name="Кабинет")),
                ("subject_name", models.CharField(blank=True, max_length=255, verbose_name="Предмет")),
                ("group_name", models.CharField(blank=True, max_length=64, verbose_name="Группа")),
                ("recommended_temperature", models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True, verbose_name="Рекомендуемая температура")),
                ("temperature_min", models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True, verbose_name="Минимальная температура")),
                ("temperature_max", models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True, verbose_name="Максимальная температура")),
                ("action_choice", models.CharField(choices=[("pending", "Не выбрано"), ("manual", "Настрою сам"), ("algorithm", "Оставить алгоритму")], default="pending", max_length=16, verbose_name="Выбор преподавателя")),
                ("payload", models.JSONField(blank=True, default=dict, verbose_name="Дополнительные данные")),
                ("status", models.CharField(choices=[("unread", "Не прочитано"), ("read", "Прочитано"), ("dismissed", "Скрыто")], default="unread", max_length=16, verbose_name="Статус")),
                ("show_popup", models.BooleanField(default=True, verbose_name="Показывать popup")),
                ("valid_from", models.DateTimeField(verbose_name="Показывать с")),
                ("valid_until", models.DateTimeField(verbose_name="Показывать до")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("read_at", models.DateTimeField(blank=True, null=True, verbose_name="Прочитано")),
                ("action_at", models.DateTimeField(blank=True, null=True, verbose_name="Выбор сделан")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="teacher_notifications", to=settings.AUTH_USER_MODEL, verbose_name="Пользователь")),
            ],
            options={
                "verbose_name": "Уведомление преподавателя",
                "verbose_name_plural": "Уведомления преподавателей",
                "ordering": ["-valid_from", "-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="teachernotification",
            index=models.Index(fields=["user", "status"], name="university_t_user_id_8fb2ab_idx"),
        ),
        migrations.AddIndex(
            model_name="teachernotification",
            index=models.Index(fields=["lesson_date", "lesson_number"], name="university_t_lesson__ee08c6_idx"),
        ),
        migrations.AddIndex(
            model_name="teachernotification",
            index=models.Index(fields=["valid_from", "valid_until"], name="university_t_valid_f_6523d7_idx"),
        ),
    ]
