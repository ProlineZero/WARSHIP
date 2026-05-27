"""Завершение peer-игры: запись победителя без хранения ходов."""

import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from warship.centrifugo import publish_to_game
from warship.models import GameSession

User = get_user_model()
logger = logging.getLogger('ws_app')

IN_PROGRESS_STATUSES = (
    GameSession.GameStatus.PLAYER1_TURN,
    GameSession.GameStatus.PLAYER2_TURN,
)


def finalize_peer_game(game_session: GameSession, winner_id: int, reporter_user_id: int) -> dict:
    """
    Завершает peer-игру и публикует game_finished в game_{id}.
    Идемпотентно, если игра уже finished.
    """
    if not game_session.is_peer_mode():
        raise ValidationError('Игра не в режиме peer')

    if not game_session.player2_id:
        raise ValidationError('В игре нет второго игрока')

    if reporter_user_id not in (game_session.player1_id, game_session.player2_id):
        raise ValidationError('Только участник может завершить игру')

    if winner_id not in (game_session.player1_id, game_session.player2_id):
        raise ValidationError('Победитель должен быть участником игры')

    if game_session.status == GameSession.GameStatus.FINISHED:
        game_session = GameSession.objects.select_related('winner').get(pk=game_session.pk)
        return _build_finished_payload(game_session)

    if game_session.status not in IN_PROGRESS_STATUSES:
        raise ValidationError('Игра не в активной фазе')

    winner = User.objects.get(pk=winner_id)
    game_session.finish_game(winner)
    game_session.purge_placement_data()
    game_session = GameSession.objects.select_related('winner').get(pk=game_session.pk)

    payload = _build_finished_payload(game_session)
    publish_to_game(game_session.id, {
        'action': 'game_finished',
        'status': 'success',
        'data': payload,
    })
    logger.info('Peer-игра %s завершена, победитель %s', game_session.id, winner_id)
    return payload


def _build_finished_payload(game_session: GameSession) -> dict:
    winner_data = None
    if game_session.winner_id:
        winner_data = {
            'id': game_session.winner_id,
            'username': game_session.winner.username,
        }
    return {
        'game_id': game_session.id,
        'winner': winner_data,
        'finished_at': game_session.finished_at.isoformat() if game_session.finished_at else None,
    }
