from django.contrib.auth.models import User

from .utils import build_username


def create_teacher(first_name, last_name, middle_name, password, role="teacher"):
    base_username = build_username(
        last_name=last_name,
        first_name=first_name,
        middle_name=middle_name,
    )

    username = base_username
    counter = 1

    while User.objects.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1

    user = User.objects.create_user(
        username=username,
        password=password,
        first_name=first_name,
        last_name=last_name,
        is_staff=True,
    )

    user.profile.middle_name = middle_name
    user.profile.role = role
    user.profile.save()

    return user