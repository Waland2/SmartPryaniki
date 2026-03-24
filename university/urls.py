from django.urls import path
from . import views

app_name = "university"

urlpatterns = [
    path("", views.index_redirect, name="index"),
    path("dashboard/", views.dashboard_home, name="dashboard_home"),
    path("dashboard/room/<int:room_id>/", views.room_detail, name="room_detail"),
    path("dashboard/room/<int:room_id>/simulate/", views.room_simulate, name="room_simulate"),
    path("dashboard/room/<int:room_id>/history/", views.room_history, name="room_history"),
    path("schedule/", views.schedule_view, name="schedule"),
]