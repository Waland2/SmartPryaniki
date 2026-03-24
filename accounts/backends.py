from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import User


class FIOLoginBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        candidates = User.objects.filter(profile__login=username).select_related("profile")

        matched_user = None

        for user in candidates:
            if user.check_password(password):
                if matched_user is not None:
                    return None
                matched_user = user

        return matched_user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None