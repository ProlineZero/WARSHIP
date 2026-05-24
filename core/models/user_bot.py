import uuid
from django.db import models
from django.conf import settings

from core.common import get_logger


class UserBot(models.Model):
    token = models.CharField(max_length=255, unique=True, default=uuid.uuid4)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_bots")
    created_at = models.DateTimeField(auto_now_add=True)