import logging
import re
import time

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from warship.centrifugo import publish_to_game, publish_to_user
from warship.models import GameSession

logger = logging.getLogger('ws_app')

GAME_CHANNEL_PATTERN = re.compile(r'^game_(\d+)$')

TERMINAL_STATUSES = (
    GameSession.GameStatus.FINISHED,
    GameSession.GameStatus.CANCELLED,
)


def parse_game_id_from_channel(channel: str) -> int | None:
    match = GAME_CHANNEL_PATTERN.match(channel or '')
    return int(match.group(1)) if match else None


def _presence_cache_key(game_id: int, user_id: int) -> str:
    return f'game_presence:{game_id}:{user_id}'


def presence_ttl_seconds() -> int:
    return int(getattr(settings, 'GAME_PRESENCE_TTL', 90))


def subscription_expire_seconds() -> int:
    return int(getattr(settings, 'GAME_SUBSCRIPTION_EXPIRE_SECONDS', 60))


def cancel_grace_seconds() -> int:
    return int(getattr(settings, 'GAME_CANCEL_GRACE_SECONDS', 60))


def subscription_expire_at() -> int:
    return int(time.time()) + subscription_expire_seconds()


def touch_presence(game_id: int, user_id: int) -> None:
    cache.set(_presence_cache_key(game_id, user_id), 1, timeout=presence_ttl_seconds())


def clear_presence(game_id: int, user_id: int) -> None:
    cache.delete(_presence_cache_key(game_id, user_id))


def is_player_online(game_id: int, user_id: int) -> bool:
    return cache.get(_presence_cache_key(game_id, user_id)) is not None


def get_active_game_session(game_id: int) -> GameSession | None:
    return GameSession.objects.filter(pk=game_id).select_related('player1', 'player2').first()


def is_game_participant(game_session: GameSession, user_id: int) -> bool:
    if game_session.player1_id == user_id:
        return True
    return game_session.player2_id is not None and game_session.player2_id == user_id


def _notify_game_cancelled(game_session: GameSession) -> None:
    finished_at = game_session.finished_at.isoformat() if game_session.finished_at else None
    message = {
        'action': 'game_cancelled',
        'status': 'success',
        'data': {
            'game_id': game_session.id,
            'finished_at': finished_at,
        },
    }
    publish_to_game(game_session.id, message)
    for user_id in (game_session.player1_id, game_session.player2_id):
        if user_id:
            publish_to_user(user_id, message)


def cancel_game_if_abandoned(game_session: GameSession) -> bool:
    """Отменяет игру, если оба участника офлайн и прошла grace-пауза после старта."""
    if game_session.status in TERMINAL_STATUSES:
        return False
    if not game_session.player2_id:
        return False

    grace_elapsed = (
        timezone.now() - game_session.started_at
    ).total_seconds() >= cancel_grace_seconds()
    if not grace_elapsed:
        return False

    player1_online = is_player_online(game_session.id, game_session.player1_id)
    player2_online = is_player_online(game_session.id, game_session.player2_id)
    if player1_online or player2_online:
        return False

    return finalize_game_cancellation(game_session, reason='оба игрока офлайн')


def finalize_game_cancellation(game_session: GameSession, reason: str = '') -> bool:
    if game_session.status in TERMINAL_STATUSES:
        return False
    try:
        game_session.cancel_game()
    except Exception as exc:
        logger.warning('Не удалось отменить игру %s: %s', game_session.id, exc)
        return False

    _notify_game_cancelled(game_session)
    if reason:
        logger.info('Игра %s отменена: %s', game_session.id, reason)
    return True


def try_cancel_game_if_abandoned(game_id: int) -> bool:
    game_session = get_active_game_session(game_id)
    if not game_session:
        return False
    return cancel_game_if_abandoned(game_session)


def touch_presence_for_active_game(game_session: GameSession, user_id: int) -> None:
    if game_session.status in TERMINAL_STATUSES:
        return
    if is_game_participant(game_session, user_id):
        touch_presence(game_session.id, user_id)
