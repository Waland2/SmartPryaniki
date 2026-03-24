from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.utils.crypto import get_random_string

from .services import create_user_with_role


def redirect_user_by_role(user):
    if user.is_superuser:
        return "/dashboard/"

    profile = getattr(user, "profile", None)

    if profile and profile.role == "moderator":
        return "/dashboard/"

    return "/schedule/"


def login_view(request):
    error = ""

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()

        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)
            return redirect(redirect_user_by_role(user))
        else:
            error = "Неверный логин или пароль"

    return render(request, "accounts/login.html", {"error": error})


def logout_view(request):
    logout(request)
    return redirect("/accounts/login/")


def create_user_view(request):
    if not request.user.is_authenticated:
        return redirect("/accounts/login/")

    if not request.user.is_superuser:
        return redirect("/schedule/")

    error = ""
    success = ""
    created_username = ""
    created_password = ""

    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        middle_name = request.POST.get("middle_name", "").strip()
        password = request.POST.get("password", "").strip()
        role = request.POST.get("role", "teacher").strip()

        generate_password = request.POST.get("generate_password") == "on"

        if generate_password:
            password = get_random_string(12)

        if not first_name or not last_name:
            error = "Заполните имя и фамилию"
        elif not password:
            error = "Введите пароль или включите генерацию случайного пароля"
        else:
            user = create_user_with_role(
                first_name=first_name,
                last_name=last_name,
                middle_name=middle_name,
                password=password,
                role=role,
            )
            success = "Пользователь успешно создан"
            created_username = user.profile.login
            created_password = password

    return render(
        request,
        "accounts/create_user.html",
        {
            "error": error,
            "success": success,
            "created_username": created_username,
            "created_password": created_password,
            "title": "Создать пользователя",
        },
    )