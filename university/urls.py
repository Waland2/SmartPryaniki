from django.urls import path
from . import views
from . import notification_views

app_name = "university"

urlpatterns = [
    path("", views.index_redirect, name="index"),
    path("dashboard/", views.dashboard_home, name="dashboard_home"),
    path("dashboard/room/<int:room_id>/", views.room_detail, name="room_detail"),
    path("dashboard/room/<int:room_id>/simulate/", views.room_simulate, name="room_simulate"),
    path("dashboard/room/<int:room_id>/history/", views.room_history, name="room_history"),
    path("schedule/", views.schedule_view, name="schedule"),
    path("current-day/", views.current_day_view, name="current_day"),
    path("rooms/", views.rooms_view, name="rooms"),

    path("notifications/", notification_views.notifications_page, name="notifications"),
    path("notifications/<int:pk>/read/", notification_views.mark_notification_read, name="notification_read"),
    path("notifications/<int:pk>/manual/", notification_views.choose_manual_setup, name="notification_manual"),
    path("notifications/<int:pk>/algorithm/", notification_views.choose_algorithm_setup, name="notification_algorithm"),
    path("notifications/<int:pk>/manual-form/", notification_views.manual_setup_form, name="notification_manual_form"),
]
