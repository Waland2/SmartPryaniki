from datetime import datetime

from django.utils import timezone

from .models import Room, RoomLesson


def get_first_upcoming_lesson_for_room(room):
    now = timezone.localtime()

    return (
        RoomLesson.objects.filter(
            room=room,
            lesson_date=now.date(),
            is_cancelled=False,
            start_time__gt=now.time(),
        )
        .order_by("start_time")
        .first()
    )


def is_time_to_prepare(lesson):
    now = timezone.localtime()

    lesson_datetime = datetime.combine(
        lesson.lesson_date,
        lesson.start_time,
    )

    lesson_datetime = timezone.make_aware(
        lesson_datetime,
        timezone.get_current_timezone(),
    )

    delta = lesson_datetime - now
    minutes_left = delta.total_seconds() / 60

    return 0 <= minutes_left <= 15


def get_rooms_to_prepare():
    result = []

    for room in Room.objects.all():
        lesson = get_first_upcoming_lesson_for_room(room)

        if not lesson:
            continue

        if is_time_to_prepare(lesson):
            result.append((room, lesson))

    return result