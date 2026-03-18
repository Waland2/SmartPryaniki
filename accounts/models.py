from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ("teacher", "Преподаватель"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    middle_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default="teacher")

    def __str__(self):
        return self.user.username