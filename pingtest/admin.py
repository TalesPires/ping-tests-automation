from django.contrib import admin
from .models import NetworkTestResult
from django.contrib import admin
from pingtest.models import NetworkTestResult
from django_q.models import Task, Schedule

@admin.register(NetworkTestResult)
class NetworkTestResultAdmin(admin.ModelAdmin):
    list_display = ('telnet_host', 'ping_destination', 'success')
    list_filter = ('success', 'telnet_host')
    search_fields = ('statistics', 'error_message')