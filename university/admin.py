from django.contrib import admin, messages
from django.template.response import TemplateResponse
from django.urls import path

from .models import Room, SensorType, Sensor, SensorData


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'floor', 'chairs', 'desks', 'computers', 'windows', 'conditioners')
    search_fields = ('name',)
    list_filter = ('floor',)
    change_list_template = 'admin/university/room/change_list.html'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('simulate/', self.admin_site.admin_view(self.simulate_view), name='university_room_simulate'),
        ]
        return custom_urls + urls

    def simulate_view(self, request):
        rooms = Room.objects.prefetch_related('sensor_set__sensor_type').all()
        selected_room = None
        results = []

        room_id = request.POST.get('room_id') or request.GET.get('room_id')
        if room_id:
            try:
                selected_room = rooms.get(pk=room_id)
            except Room.DoesNotExist:
                self.message_user(request, 'Кабинет не найден.', level=messages.ERROR)

        if request.method == 'POST' and selected_room:
            results = selected_room.simulate_sensors()
            self.message_user(request, f'Симуляция для кабинета {selected_room.name} выполнена.')

        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': 'Симуляция датчиков',
            'rooms': rooms,
            'selected_room': selected_room,
            'results': results,
        }
        return TemplateResponse(request, 'admin/university/room/simulate_sensors.html', context)


@admin.register(SensorType)
class SensorTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Sensor)
class SensorAdmin(admin.ModelAdmin):
    list_display = ('name', 'room', 'sensor_type', 'status', 'last_value', 'last_updated')
    list_filter = ('sensor_type', 'status', 'room')
    search_fields = ('name',)
    actions = ['simulate_selected_sensors']

    @admin.action(description='Симулировать показания выбранных датчиков')
    def simulate_selected_sensors(self, request, queryset):
        simulated = 0
        for sensor in queryset:
            result = sensor.read_from_simulator()
            if result.get('saved'):
                simulated += 1
        self.message_user(request, f'Обновлено датчиков: {simulated}')


@admin.register(SensorData)
class SensorDataAdmin(admin.ModelAdmin):
    list_display = ('sensor', 'value', 'created_at')
    list_filter = ('sensor',)
    search_fields = ('sensor__name',)

# Заголовок админки
admin.site.site_header = "Умные Пряники"
admin.site.site_title = "Администрирование"
admin.site.index_title = "Панель управления"