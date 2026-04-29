from django.contrib import admin, messages
from django.template.response import TemplateResponse
from django.urls import path

from .models import (
    Room,
    SensorType,
    Sensor,
    SensorData,
    Conditioner,
    RoomLesson,
    ClimateActionLog,
)


class ConditionerInline(admin.TabularInline):
    model = Conditioner
    extra = 1
    fields = ("name", "status", "enabled", "mode", "target_temperature", "power")
    show_change_link = True


class ClimateActionLogInline(admin.TabularInline):
    model = ClimateActionLog
    extra = 0
    can_delete = False

    fields = (
        "created_at",
        "lesson_date",
        "lesson_time",
        "action",
        "reason",
    )

    readonly_fields = (
        "created_at",
        "lesson_date",
        "lesson_time",
        "action",
        "reason",
    )

    ordering = ("-created_at",)
    max_num = 20

    verbose_name = "История настройки"
    verbose_name_plural = "История настройки кабинета"


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "floor",
        "chairs",
        "desks",
        "computers",
        "windows",
        "conditioners",
        "window_open",
        "last_climate_action",
    )

    search_fields = ("name",)
    list_filter = ("floor", "window_open")
    change_list_template = "admin/university/room/change_list.html"

    inlines = [
        ConditionerInline,
        ClimateActionLogInline,
    ]

    def last_climate_action(self, obj):
        log = obj.climate_logs.order_by("-created_at").first()
        if not log:
            return "Нет записей"
        return f"{log.get_action_display()} — {log.created_at:%d.%m.%Y %H:%M}"

    last_climate_action.short_description = "Последняя настройка"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "simulate/",
                self.admin_site.admin_view(self.simulate_view),
                name="university_room_simulate",
            ),
        ]
        return custom_urls + urls

    def simulate_view(self, request):
        rooms = Room.objects.prefetch_related("sensor_set__sensor_type").all()
        selected_room = None
        results = []

        room_id = request.POST.get("room_id") or request.GET.get("room_id")
        if room_id:
            try:
                selected_room = rooms.get(pk=room_id)
            except Room.DoesNotExist:
                self.message_user(request, "Кабинет не найден.", level=messages.ERROR)

        if request.method == "POST" and selected_room:
            results = selected_room.simulate_sensors()
            self.message_user(
                request,
                f"Симуляция для кабинета {selected_room.name} выполнена.",
            )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Симуляция датчиков",
            "rooms": rooms,
            "selected_room": selected_room,
            "results": results,
        }

        return TemplateResponse(
            request,
            "admin/university/room/simulate_sensors.html",
            context,
        )


@admin.register(ClimateActionLog)
class ClimateActionLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "room",
        "lesson_date",
        "lesson_time",
        "action",
        "reason",
    )

    list_filter = (
        "room",
        "action",
        "lesson_date",
        "created_at",
    )

    date_hierarchy = "created_at"

    search_fields = (
        "room__name",
        "action",
        "reason",
    )

    readonly_fields = (
        "created_at",
        "room",
        "lesson_date",
        "lesson_time",
        "action",
        "reason",
    )

    ordering = ("-created_at",)

    list_per_page = 25


@admin.register(SensorType)
class SensorTypeAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Sensor)
class SensorAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "room",
        "sensor_type",
        "status",
        "last_value",
        "last_updated",
    )

    list_filter = ("sensor_type", "status", "room")
    search_fields = ("name", "room__name")
    actions = ["simulate_selected_sensors"]

    @admin.action(description="Симулировать показания выбранных датчиков")
    def simulate_selected_sensors(self, request, queryset):
        simulated = 0

        for sensor in queryset:
            result = sensor.read_from_simulator()
            if result.get("saved"):
                simulated += 1

        self.message_user(request, f"Обновлено датчиков: {simulated}")


@admin.register(SensorData)
class SensorDataAdmin(admin.ModelAdmin):
    list_display = ("sensor", "value", "created_at")
    list_filter = ("sensor", "sensor__room", "sensor__sensor_type", "created_at")
    search_fields = ("sensor__name", "sensor__room__name")
    date_hierarchy = "created_at"


@admin.register(Conditioner)
class ConditionerAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "room",
        "status",
        "enabled",
        "mode",
        "target_temperature",
        "power",
        "last_updated",
    )

    list_filter = ("status", "enabled", "mode", "room")
    search_fields = ("name", "room__name")


@admin.register(RoomLesson)
class RoomLessonAdmin(admin.ModelAdmin):
    list_display = (
        "room",
        "lesson_date",
        "start_time",
        "end_time",
        "pair_number",
        "group_name",
        "subject",
        "is_cancelled",
    )

    list_filter = ("lesson_date", "is_cancelled", "room")
    search_fields = (
        "room__name",
        "group_name",
        "subject",
        "teacher",
        "external_id",
    )

    date_hierarchy = "lesson_date"


admin.site.site_header = "Умные Пряники"
admin.site.site_title = "Администрирование"
admin.site.index_title = "Панель управления"