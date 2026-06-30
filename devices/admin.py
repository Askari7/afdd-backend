from django.contrib import admin
from .models import Device

# Register your models here.
@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("id", "uuid", "name", "type", "created_at")
    list_filter = ("type", "created_at")
    search_fields = ("uuid", "name", "type")