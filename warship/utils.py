from core.models.user import User
from core.models.user_bot import UserBot
from warship.models import GameSession
from django.db.models import Q


def get_player_stats(user: User):
    """Статистика игрока по рейтинговым (не тренировочным) играм."""
    finished_games = GameSession.objects.filter(
        Q(player1=user) | Q(player2=user),
        status=GameSession.GameStatus.FINISHED,
        is_training=False,
    )

    total_games = finished_games.count()
    wins = finished_games.filter(winner=user).count()
    win_rate = (wins / total_games * 100) if total_games > 0 else 50.0

    return {
        'total_games': total_games,
        'wins': wins,
        'win_rate': round(win_rate, 2),
    }


def get_bot_stats(user_bot: UserBot):
    """Статистика конкретного бота по рейтинговым играм."""
    finished_games = GameSession.objects.filter(
        Q(player1_bot=user_bot) | Q(player2_bot=user_bot),
        status=GameSession.GameStatus.FINISHED,
        is_training=False,
    )

    total_games = finished_games.count()
    wins = 0
    for game in finished_games.select_related('winner', 'player1', 'player2', 'player1_bot', 'player2_bot'):
        if game.player1_bot_id == user_bot.id and game.winner_id == game.player1_id:
            wins += 1
        elif game.player2_bot_id == user_bot.id and game.winner_id == game.player2_id:
            wins += 1

    win_rate = (wins / total_games * 100) if total_games > 0 else 50.0

    return {
        'total_games': total_games,
        'wins': wins,
        'win_rate': round(win_rate, 2),
    }


def build_leaderboard(entries, stats_key='stats'):
    """
    Сортировка и ранжирование записей лидерборда.
    entries: list of dicts with stats inside stats_key
    """
    sorted_entries = sorted(
        entries,
        key=lambda item: (
            -item[stats_key]['wins'],
            -item[stats_key]['win_rate'],
            -item[stats_key]['total_games'],
        ),
    )
    for rank, entry in enumerate(sorted_entries, start=1):
        entry['rank'] = rank
    return sorted_entries
