import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from django.contrib.auth import get_user_model

from warship.game_presence import (
    get_active_game_session,
    is_game_participant,
    parse_game_id_from_channel,
    subscription_expire_at,
    touch_presence,
)

User = get_user_model()

logger = logging.getLogger('ws_app')


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
    return JsonResponse({'error': {'code': 403, 'message': 'permission denied'}})


@method_decorator(csrf_exempt, name='dispatch')
class CentrifugoSubscribeProxyView(View):
    """Subscribe proxy: доступ к game_<id> только участникам, фиксируем presence."""

    def post(self, request):
        if not _proxy_authorized(request):
            return _proxy_forbidden()

        payload = _parse_body(request)
        channel = payload.get('channel', '')
        user_id = payload.get('user')
        if user_id is not None:
            user_id = int(user_id)

        game_id = parse_game_id_from_channel(channel)
        if game_id is None:
            return JsonResponse({'result': {}})

        game_session = get_active_game_session(game_id)
        if not game_session or not user_id:
            return _proxy_forbidden()

        is_admin_observer = User.objects.filter(id=user_id, is_staff=True, is_active=True).exists()
        if is_admin_observer:
            return JsonResponse({'result': {'expire_at': subscription_expire_at()}})

        if not is_game_participant(game_session, user_id):
            return _proxy_forbidden()
        if game_session.status in (
            game_session.GameStatus.FINISHED,
            game_session.GameStatus.CANCELLED,
        ):
            return _proxy_forbidden()

        touch_presence(game_id, user_id)
        return JsonResponse({
            'result': {
                'expire_at': subscription_expire_at(),
            },
        })


@method_decorator(csrf_exempt, name='dispatch')
class CentrifugoSubRefreshProxyView(View):
    """Sub refresh: продление подписки = heartbeat presence (unsubscribe-хука нет)."""

    def post(self, request):
        if not _proxy_authorized(request):
            return _proxy_forbidden()

        payload = _parse_body(request)
        channel = payload.get('channel', '')
        user_id = payload.get('user')
        if user_id is not None:
            user_id = int(user_id)

        game_id = parse_game_id_from_channel(channel)
        if game_id is None:
            return JsonResponse({'result': {}})

        game_session = get_active_game_session(game_id)
        if not game_session or not user_id:
            return JsonResponse({'result': {'expired': True}})

        is_admin_observer = User.objects.filter(id=user_id, is_staff=True, is_active=True).exists()
        if is_admin_observer:
            return JsonResponse({'result': {'expire_at': subscription_expire_at()}})

        if not is_game_participant(game_session, user_id):
            return JsonResponse({'result': {'expired': True}})

        touch_presence(game_id, user_id)
        return JsonResponse({
            'result': {
                'expire_at': subscription_expire_at(),
            },
        })
