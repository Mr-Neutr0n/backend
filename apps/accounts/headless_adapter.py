"""OPEN's django-allauth headless adapter."""

from allauth.headless.adapter import DefaultHeadlessAdapter


class HeadlessAdapter(DefaultHeadlessAdapter):
    """allauth's headless adapter, without row ids in user payloads."""
