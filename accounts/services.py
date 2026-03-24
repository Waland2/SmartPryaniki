import uuid

from django.contrib.auth.models import User

from .utils import build_username


def create_user_with_role(first_name, last_name, middle_name, password, role="teacher"):
    fio_login = build_username(
        last_name=last_name,
        first_name=first_name,
        middle_name=middle_name,
    )

    technical_username = uuid.uuid4().hex

    is_staff = role == "moderator"

    user = User.objects.create_user(
        username=technical_username,
        password=password,
        first_name=first_name,
        last_name=last_name,
        is_staff=is_staff,
    )

    user.profile.first_name = first_name
    user.profile.last_name = last_name
    user.profile.middle_name = middle_name
    user.profile.login = fio_login
    user.profile.role = role
    user.profile.save()

    return user