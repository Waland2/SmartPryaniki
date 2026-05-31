from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_alter_userprofile_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="building",
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[(1, "1 корпус"), (2, "2 корпус")],
                help_text="Область ответственности администратора по направлению.",
                null=True,
                verbose_name="Корпус",
            ),
        ),
    ]
