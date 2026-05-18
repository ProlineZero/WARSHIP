from core.models.user import User
from warship.models import GameSession
from django.db.models import Q



def get_player_stats(user: User):
    """
    Получает статистику игрока.
    
    Args:
        user: Пользователь
    
    Returns:
        dict с ключами:
        - total_games: общее количество завершенных игр
        - wins: количество побед
        - win_rate: процент побед (0-100)
    """
    # Подсчитываем завершенные игры, где игрок участвовал
    finished_games = GameSession.objects.filter(
        Q(player1=user) | Q(player2=user),
        status=GameSession.GameStatus.FINISHED,
        is_training=False
    )
    
    total_games = finished_games.count()
    
    # Подсчитываем победы
    wins = finished_games.filter(winner=user).count()
    
    # Рассчитываем процент побед
    win_rate = (wins / total_games * 100) if total_games > 0 else 50.0
    
    return {
        'total_games': total_games,
        'wins': wins,
        'win_rate': round(win_rate, 2)
    }

