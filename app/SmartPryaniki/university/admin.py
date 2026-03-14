from django.contrib import admin
from .models import Room, SensorType, Sensor, SensorData


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
    )

    search_fields = ("name",)

    list_filter = ("floor",)


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

    list_filter = (
        "sensor_type",
        "status",
        "room",
    )

    search_fields = ("name",)


@admin.register(SensorData)
class SensorDataAdmin(admin.ModelAdmin):
    list_display = (
        "sensor",
        "value",
        "created_at",
    )

    list_filter = ("sensor",)

    search_fields = ("sensor__name",)


# Заголовок админки
admin.site.site_header = "Умные Пряники"
admin.site.site_title = "Администрирование"
admin.site.index_title = "Панель управления"