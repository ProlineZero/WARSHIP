import time
import os
from pprint import pprint
import traceback
from django.conf import settings
from django.core.management.base import BaseCommand

from core.models.user import User
from warship.models import GameSession




class Command(BaseCommand):
    # ЗАПУСК
    # daphne -b 0.0.0.0 -p 8000 config.asgi:application
    def handle(self, *args, **options):
        import requests
        import json

        url = 'https://restapi.plusofon.ru/api/v1/sms'
        payload = {
            "text": "mollitia",
            "number_id": 2,
            "to": 241.77791,
            "dlr_level": 18,
            "reject_long": True,
            "count_pdu": True
        }
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Client': '10553',
            'Authorization': 'Bearer {settings.PLUSOFON_TOKEN}'
        }
        # response = requests.request('POST', url, headers=headers, json=payload)
        # response.json()
        # print(PLUSOFON_TOKEN)
        # print(response.json())
        print(
            # GameSession.objects.exclude(status=GameSession.GameStatus.CANCELLED).count()
            (
                GameSession.objects.exclude(
                status=GameSession.GameStatus.CANCELLED
            )
            )
            # .count()
            .update(
                status=GameSession.GameStatus.CANCELLED
            )
        )

        pass