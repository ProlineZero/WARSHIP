import os
import json
import logging
import hmac
import hashlib
import time
from cent import Client
from django.conf import settings

logger = logging.getLogger('ws_app')

def get_centrifugo_client():
    api_url = getattr(settings, 'CENTRIFUGO_API_URL', 'http://localhost:8001/api')
    api_key = getattr(settings, 'CENTRIFUGO_API_KEY', '')
    return Client(api_url, api_key, timeout=2.0)

def publish_to_game(game_id, message):
    client = get_centrifugo_client()
    channel = f"game_{game_id}"
    logger.info(f"[CENTRIFUGO] Публикация в канал {channel}: {message}")
    try:
        client.publish(channel, message)
    except Exception as e:
        logger.error(f"[CENTRIFUGO] Ошибка публикации в {channel}: {e}", exc_info=True)

def publish_to_user(user_id, message):
    client = get_centrifugo_client()
    channel = f"user_{user_id}"
    logger.info(f"[CENTRIFUGO] Публикация пользователю {channel}: {message}")
    try:
        client.publish(channel, message)
    except Exception as e:
        logger.error(f"[CENTRIFUGO] Ошибка публикации пользователю {user_id}: {e}", exc_info=True)

def generate_centrifugo_token(user_id):
    """Генерация JWT токена для подключения к Centrifugo"""
    import jwt
    secret = getattr(settings, 'CENTRIFUGO_HMAC_SECRET_KEY', getattr(settings, 'SECRET_KEY'))
    payload = {
        "sub": str(user_id),
        "exp": int(time.time()) + 24 * 3600
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token
