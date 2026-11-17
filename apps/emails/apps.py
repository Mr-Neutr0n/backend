from django.apps import AppConfig


class EmailsConfig(AppConfig):
    name = "apps.emails"
    label = "emails"
    verbose_name = "Email outbox"
