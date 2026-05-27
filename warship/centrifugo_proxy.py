import json
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from warship.game_presence import (
    get_active_game_session,
    is_game_participant,
    parse_finish_game_id,
    parse_game_id_from_channel,
    parse_user_id_from_channel,
    subscription_expire_at,
    touch_presence,
)
from warship.models import GameSession
from warship.services.peer_finish import finalize_peer_game

User = get_user_model()

logger = logging.getLogger('ws_app')

TERMINAL_STATUSES = (
    GameSession.GameStatus.FINISHED,
    GameSession.GameStatus.CANCELLED,
)


def _proxy_authorized(request) -> bool:
    expected = getattr(settings, 'CENTRIFUGO_PROXY_SECRET', '')
    if not expected:
        return True
    return request.headers.get('X-Centrifugo-Proxy-Key') == expected


def _parse_body(request) -> dict:
    if not request.body:
        return {}
    return json.loads(request.body.decode('utf-8'))


def _proxy_forbidden():
    return JsonResponse({'error': {'code': 403, 'message': 'permission denied'}}, status=403)


def _subscribe_allowed(channel: str, user_id: int) -> JsonResponse | None:
    """Проверка подписки: user_{id}, game_{id}, finish:{id}. None = запрет."""
    if not user_id:
        return _proxy_forbidden()

    channel_owner_id = parse_user_id_from_channel(channel)
    if channel_owner_id is not None:
        if channel_owner_id != user_id:
            return _proxy_forbidden()
        return JsonResponse({'result': {'expire_at': subscription_expire_at()}})

    finish_game_id = parse_finish_game_id(channel)
    if finish_game_id is not None:
        game_session = get_active_game_session(finish_game_id)
        if not game_session or not game_session.is_peer_mode():
            return _proxy_forbidden()
        if game_session.status in TERMINAL_STATUSES:
            return _proxy_forbidden()
        if not is_game_participant(game_session, user_id):
            return _proxy_forbidden()
        touch_presence(finish_game_id, user_id)
        return JsonResponse({'result': {'expire_at': subscription_expire_at()}})

    game_id = parse_game_id_from_channel(channel)
    if game_id is not None:
        game_session = get_active_game_session(game_id)
        if not game_session:
            return _proxy_forbidden()

        is_admin_observer = User.objects.filter(id=user_id, is_staff=True, is_active=True).exists()
        if is_admin_observer:
            return JsonResponse({'result': {'expire_at': subscription_expire_at()}})

        if not is_game_participant(game_session, user_id):
            return _proxy_forbidden()
        if game_session.status in TERMINAL_STATUSES:
            return _proxy_forbidden()

        touch_presence(game_id, user_id)
        return JsonResponse({'result': {'expire_at': subscription_expire_at()}})

    return _proxy_forbidden()


def _sub_refresh_result(channel: str, user_id: int) -> dict:
    if not user_id:
        return {'expired': True}

    channel_owner_id = parse_user_id_from_channel(channel)
    if channel_owner_id is not None:
        if channel_owner_id != user_id:
            return {'expired': True}
        return {'expire_at': subscription_expire_at()}

    finish_game_id = parse_finish_game_id(channel)
    if finish_game_id is not None:
        game_session = get_active_game_session(finish_game_id)
        if not game_session or not game_session.is_peer_mode():
            return {'expired': True}
        if not is_game_participant(game_session, user_id):
            return {'expired': True}
        touch_presence(finish_game_id, user_id)
        return {'expire_at': subscription_expire_at()}

    game_id = parse_game_id_from_channel(channel)
    if game_id is not None:
        game_session = get_active_game_session(game_id)
        if not game_session:
            return {'expired': True}

        is_admin_observer = User.objects.filter(id=user_id, is_staff=True, is_active=True).exists()
        if is_admin_observer:
            return {'expire_at': subscription_expire_at()}

        if not is_game_participant(game_session, user_id):
            return {'expired': True}

        touch_presence(game_id, user_id)
        return {'expire_at': subscription_expire_at()}

    return {'expired': True}


@method_decorator(csrf_exempt, name='dispatch')
class CentrifugoSubscribeProxyView(View):
    """Subscribe proxy: user_{id}, game_{id}, finish:{id}."""

    def post(self, request):
        if not _proxy_authorized(request):
            return _proxy_forbidden()

        payload = _parse_body(request)
        channel = payload.get('channel', '')
        user_id = payload.get('user')
        if user_id is not None:
            user_id = int(user_id)

        return _subscribe_allowed(channel, user_id)


@method_decorator(csrf_exempt, name='dispatch')
class CentrifugoSubRefreshProxyView(View):
    """Sub refresh: продление подписки = heartbeat presence."""

    def post(self, request):
        if not _proxy_authorized(request):
            return _proxy_forbidden()

        payload = _parse_body(request)
        channel = payload.get('channel', '')
        user_id = payload.get('user')
        if user_id is not None:
            user_id = int(user_id)

        return JsonResponse({'result': _sub_refresh_result(channel, user_id)})


@method_decorator(csrf_exempt, name='dispatch')
class CentrifugoPublishProxyView(View):
    """Publish proxy только для finish:{id} — запись результата peer-игры."""

    def post(self, request):
        if not _proxy_authorized(request):
            return _proxy_forbidden()

        payload = _parse_body(request)
        channel = payload.get('channel', '')
        user_id = payload.get('user')
        if user_id is not None:
            user_id = int(user_id)

        game_id = parse_finish_game_id(channel)
        if game_id is None:
            return _proxy_forbidden()

        game_session = get_active_game_session(game_id)
        if not game_session or not user_id:
            return _proxy_forbidden()

        if not is_game_participant(game_session, user_id):
            return _proxy_forbidden()

        pub_data = payload.get('data') or {}
        if isinstance(pub_data, str):
            try:
                pub_data = json.loads(pub_data)
            except json.JSONDecodeError:
                return _proxy_forbidden()

        if pub_data.get('action') != 'game_finished':
            return _proxy_forbidden()

        winner_id = pub_data.get('winner_id')
        if winner_id is None:
            return _proxy_forbidden()
        winner_id = int(winner_id)

        try:
            finalize_peer_game(game_session, winner_id, user_id)
        except ValidationError as exc:
            logger.warning('Отклонена публикация finish:%s: %s', game_id, exc)
            return _proxy_forbidden()

        return JsonResponse({'result': {}})
