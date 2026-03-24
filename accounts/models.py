from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ("teacher", "Преподаватель"),
        ("moderator", "Младший администратор"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")

    last_name = models.CharField("Фамилия", max_length=150, blank=True)
    first_name = models.CharField("Имя", max_length=150, blank=True)
    middle_name = models.CharField("Отчество", max_length=150, blank=True)

    login = models.CharField("Логин", max_length=255, blank=True, db_index=True)

    role = models.CharField(
        "Роль",
        max_length=50,
        choices=ROLE_CHOICES,
        default="teacher",
    )

    def __str__(self):
        return self.get_full_name() or self.user.username

    def get_full_name(self):
        return " ".join(
            part for part in [self.last_name, self.first_name, self.middle_name] if part
        ).strip()

    def get_short_name(self):
        initials = []
        if self.first_name:
            initials.append(f"{self.first_name[:1]}.")
        if self.middle_name:
            initials.append(f"{self.middle_name[:1]}.")
        initials_str = "".join(initials)

        if self.last_name and initials_str:
            return f"{self.last_name} {initials_str}"
        if self.last_name:
            return self.last_name
        return self.user.username
    
    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"