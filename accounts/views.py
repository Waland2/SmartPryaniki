from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect

from .services import create_teacher


def login_view(request):
    error = ""

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()

        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)
            return redirect("/dashboard/")
        else:
            error = "Неверный логин или пароль"

    return render(request, "accounts/login.html", {"error": error})


def logout_view(request):
    logout(request)
    return redirect("/accounts/login/")


def create_user_view(request):
    if not request.user.is_superuser:
        return redirect("/accounts/login/")

    error = ""
    success = ""
    created_username = ""

    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        middle_name = request.POST.get("middle_name", "").strip()
        password = request.POST.get("password", "").strip()
        role = request.POST.get("role", "teacher").strip()

        if not first_name or not last_name or not password:
            error = "Заполните имя, фамилию и пароль"
        else:
            user = create_teacher(
                first_name=first_name,
                last_name=last_name,
                middle_name=middle_name,
                password=password,
                role=role,
            )
            success = "Пользователь успешно создан"
            created_username = user.username

    return render(
        request,
        "accounts/create_user.html",
        {
            "error": error,
            "success": success,
            "created_username": created_username,
        },
    )