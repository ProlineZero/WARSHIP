from django.contrib.auth import get_user_model

from warship.centrifugo import publish_to_game
from warship.models import GameSession, make_shot

User = get_user_model()


def queue_manual_move(game_session: GameSession, player, row: int, col: int, bot_id: int | None = None) -> dict:
    """Ставит ход в очередь для подтверждения администратором."""
    game_session.pending_move = {
        'player_id': player.id,
        'row': row,
        'col': col,
        'bot_id': bot_id,
    }
    game_session.save(update_fields=['pending_move'])

    publish_to_game(game_session.id, {
        'action': 'admin_move_pending',
        'status': 'success',
        'data': {
            'game_id': game_session.id,
            'pending_move': game_session.pending_move,
        },
    })

    return {
        'success': False,
        'error': 'Ход ожидает подтверждения администратора',
        'awaiting_approval': True,
        'pending_move': game_session.pending_move,
    }


def approve_pending_move(game_session: GameSession) -> tuple[dict | None, str | None]:
    """Выполняет ожидающий ход после подтверждения администратором."""
    if not game_session.pending_move:
        return None, 'Нет ожидающего хода'

    pending = game_session.pending_move
    player = User.objects.filter(id=pending['player_id']).first()
    if not player:
        return None, 'Игрок не найден'

    row = pending['row']
    col = pending['col']

    result = make_shot(game_session, player, row, col, skip_control_gates=True)
    if not result['success']:
        return None, result.get('error', 'Ошибка выстрела')

    return result, None


def publish_shot_result(game_session: GameSession, result: dict) -> dict:
    """Публикует результат выстрела в Centrifugo и возвращает payload для HTTP."""
    from warship.game_status import broadcast_game_status

    winner = result.get('winner')
    result_to_send = dict(result)
    if winner:
        result_to_send['winner'] = {'id': winner.id, 'username': winner.username}

    publish_to_game(game_session.id, {
        'action': 'shot_result',
        'status': 'success',
        'data': result_to_send,
    })

    broadcast_game_status(game_session)

    if result.get('game_finished'):
        publish_to_game(game_session.id, {
            'action': 'game_finished',
            'status': 'success',
            'data': {
                'game_id': game_session.id,
                'winner': result_to_send.get('winner'),
                'finished_at': game_session.finished_at.isoformat() if game_session.finished_at else None,
            },
        })

    return result_to_send
