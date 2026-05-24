from core.auth.bot_access import get_request_user_bot_id, is_bot_request
from warship.models import GameSession


def attach_bot_to_game_if_needed(game_session: GameSession, request) -> None:
    """Привязывает UserBot к игре при первом запросе от бота."""
    if not is_bot_request(request):
        return

    bot_id = get_request_user_bot_id(request)
    if not bot_id:
        return

    user_id = request.user.id
    update_fields = []

    if game_session.player1_id == user_id and not game_session.player1_bot_id:
        game_session.player1_bot_id = bot_id
        update_fields.append('player1_bot')
    elif game_session.player2_id == user_id and not game_session.player2_bot_id:
        game_session.player2_bot_id = bot_id
        update_fields.append('player2_bot')

    if update_fields:
        game_session.save(update_fields=update_fields)
