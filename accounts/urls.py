from django.urls import path
from .views import login_view, logout_view, create_user_view

urlpatterns = [
    path("login/", login_view),
    path("logout/", logout_view),
    path("create/", create_user_view),
]