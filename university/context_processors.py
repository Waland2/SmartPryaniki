from django.utils import timezone
from .models import TeacherNotification


def unread_notification_popup(request):
    if not request.user.is_authenticated:
        return {"popup_notifications": []}

    if request.session.get("notifications_popup_shown") is True:
        return {"popup_notifications": []}

    now = timezone.now()

    notifications = TeacherNotification.objects.filter(
        user=request.user,
        status="unread",
        show_popup=True,
        valid_from__lte=now,
        valid_until__gte=now,
    ).order_by("-created_at")

    request.session["notifications_popup_shown"] = True
    request.session.modified = True

    return {"popup_notifications": notifications}