from warship.centrifugo import publish_to_game
from warship.models import ShipPlacement


def get_game_status_data(game_session):
    player1_placement = ShipPlacement.objects.filter(
        game_session=game_session, player=game_session.player1
    ).first()
    player2_placement = ShipPlacement.objects.filter(
        game_session=game_session, player=game_session.player2
    ).first()

    current_turn_data = None
    if game_session.current_turn:
        current_turn_data = {
            'id': game_session.current_turn.id,
            'username': game_session.current_turn.username,
        }

    return {
        'game_id': game_session.id,
        'status': game_session.status,
        'is_training': game_session.is_training,
        'player1': {
            'id': game_session.player1.id,
            'username': game_session.player1.username,
            'ships_placed': player1_placement.ships_placed if player1_placement else False,
        },
        'player2': {
            'id': game_session.player2.id if game_session.player2 else None,
            'username': game_session.player2.username if game_session.player2 else None,
            'ships_placed': player2_placement.ships_placed if player2_placement else False,
        } if game_session.player2 else None,
        'player1_bot': {
            'id': game_session.player1_bot_id,
            'name': game_session.player1_bot.name if game_session.player1_bot_id else None,
        } if game_session.player1_bot_id else None,
        'player2_bot': {
            'id': game_session.player2_bot_id,
            'name': game_session.player2_bot.name if game_session.player2_bot_id else None,
        } if game_session.player2_bot_id else None,
        'current_turn': current_turn_data,
        'winner': {
            'id': game_session.winner.id,
            'username': game_session.winner.username,
        } if game_session.winner else None,
        'board_size': game_session.board_size,
        'play_mode': game_session.play_mode,
        'admin_control_mode': game_session.admin_control_mode,
        'move_delay_ms': game_session.move_delay_ms,
        'is_paused': game_session.is_paused,
        'pending_move': game_session.pending_move,
        'started_at': game_session.started_at.isoformat() if game_session.started_at else None,
        'finished_at': game_session.finished_at.isoformat() if game_session.finished_at else None,
    }


def broadcast_game_status(game_session):
    status_data = get_game_status_data(game_session)
    publish_to_game(game_session.id, {
        'action': 'game_status',
        'status': 'success',
        'data': status_data,
    })
