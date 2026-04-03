from .notification_services import get_actual_unread_notifications


def unread_notification_popup(request):
    if not request.user.is_authenticated:
        return {"notification_popup_items": []}

    return {
        "notification_popup_items": get_actual_unread_notifications(request.user, limit=3)
    }
