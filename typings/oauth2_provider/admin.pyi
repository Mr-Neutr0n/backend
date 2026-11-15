# Only the Application admin, which apps.partners.admin subclasses.
from typing import Any

from django.contrib import admin

class ApplicationAdmin(admin.ModelAdmin[Any]): ...
