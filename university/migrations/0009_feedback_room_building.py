from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("university", "0008_alter_climateactionlog_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="room",
            name="building",
            field=models.PositiveSmallIntegerField(
                choices=[(1, "1 корпус"), (2, "2 корпус")],
                default=1,
                verbose_name="Корпус",
            ),
        ),
        migrations.CreateModel(
            name="Feedback",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150, verbose_name="Имя")),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="Электронная почта")),
                ("message", models.TextField(verbose_name="Сообщение")),
                ("is_read", models.BooleanField(default=False, verbose_name="Прочитано")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
            ],
            options={
                "verbose_name": "Обращение",
                "verbose_name_plural": "Обращения",
                "ordering": ("-created_at",),
            },
        ),
    ]
