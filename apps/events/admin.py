"""Admin for Events."""

from typing import ClassVar

from django import forms
from django.contrib import admin

from apps.events.models import CHOICE_MESSAGES, Event


class EventAdminForm(forms.ModelForm[Event]):
    """The Event form, with messages that never name the submitted value.

    A model field's ``error_messages`` do not reach its form field, and
    the form's own ``invalid_choice`` message names the value.
    """

    class Meta:
        model = Event
        fields = (
            "name",
            "kind",
            "organizer",
            "club",
            "start_date",
            "end_date",
            "weight",
        )
        error_messages: ClassVar[dict[str, dict[str, str]]] = {"kind": CHOICE_MESSAGES}


@admin.register(Event)
class EventAdmin(admin.ModelAdmin[Event]):
    form = EventAdminForm
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
