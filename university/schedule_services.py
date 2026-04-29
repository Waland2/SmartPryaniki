from django.utils import timezone
from .models import RoomLesson
from .models import Room
from datetime import timedelta


def get_first_upcoming_lesson_for_room(room):
    now = timezone.localtime()

    lesson = (
        RoomLesson.objects.filter(
            room=room,
            lesson_date=now.date(),
            is_cancelled=False,
            start_time__gt=now.time(),
        )
        .order_by("start_time")
        .first()
    )

    return lesson

def is_time_to_prepare(lesson):
    now = timezone.localtime()

    lesson_dt = timezone.make_aware(
        timezone.datetime.combine(
            lesson.lesson_date,
            lesson.start_time
        )
    )

    delta = lesson_dt - now
    minutes = delta.total_seconds() / 60

    return 0 <= minutes <= 15

def get_rooms_to_prepare():
    result = []

    for room in Room.objects.all():
        lesson = get_first_upcoming_lesson_for_room(room)

        if not lesson:
            continue

        if is_time_to_prepare(lesson):
            result.append((room, lesson))

    return result