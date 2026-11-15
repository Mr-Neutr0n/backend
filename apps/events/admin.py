"""Admin for Events."""

from django.contrib import admin

from apps.events.models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin[Event]):
    list_display = (
        "public_code",
        "name",
        "kind",
        "organizer",
        "club",
        "start_date",
        "end_date",
        "weight",
    )
    readonly_fields = ("public_code",)
    search_fields = ("public_code", "name")
    list_filter = ("kind",)
    autocomplete_fields = ("organizer", "club")
