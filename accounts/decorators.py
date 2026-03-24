from functools import wraps

from django.shortcuts import redirect


def moderator_or_admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("/accounts/login/")

        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        profile = getattr(request.user, "profile", None)
        if profile and profile.role == "moderator":
            return view_func(request, *args, **kwargs)

        return redirect("/schedule/")

    return _wrapped_view