from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "get_full_name", "login", "role")
    search_fields = ("login", "last_name", "first_name", "middle_name")
    list_filter = ("role",)
    autocomplete_fields = ("user",)

    def get_full_name(self, obj):
        return obj.get_full_name()
    get_full_name.short_description = "ФИО"