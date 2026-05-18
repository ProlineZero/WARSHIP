"""
Утилиты для подбора противников и расчета статистики игроков.
"""
from django.db.models import Q, Count, Case, When, IntegerField
from django.db.models.functions import Coalesce
from warship.models import GameSession
from django.conf import settings
import logging
from warship.utils import get_player_stats
logger = logging.getLogger('ws_app')


def find_opponent_from_queue(user, waiting_queue_dict, max_skill_diff=20, max_games_diff=50):
    """
    Находит подходящего противника для игрока из очереди ожидающих.
    
    Args:
        user: Пользователь, ищущий противника
        waiting_queue_dict: Словарь ожидающих игроков {user_id: {...}}
        max_skill_diff: Максимальная разница в проценте побед (по умолчанию 20%)
        max_games_diff: Максимальная разница в количестве игр (по умолчанию 50)
    
    Returns:
        User объект противника или None
    """
    user_stats = get_player_stats(user)
    user_win_rate = user_stats['win_rate']
    user_total_games = user_stats['total_games']
    
    best_match = None
    best_score = float('inf')
    
    # Ищем среди игроков в очереди
    for opponent_id, opponent_data in waiting_queue_dict.items():
        if opponent_id == user.id:
            continue
        
        opponent = opponent_data.get('user')
        if not opponent:
            continue
        
        opponent_stats = get_player_stats(opponent)
        opponent_win_rate = opponent_stats['win_rate']
        opponent_total_games = opponent_stats['total_games']
        
        # Рассчитываем разницу в навыках
        skill_diff = abs(user_win_rate - opponent_win_rate)
        games_diff = abs(user_total_games - opponent_total_games)
        
        # Проверяем, подходит ли противник
        if skill_diff <= max_skill_diff and games_diff <= max_games_diff:
            # Рассчитываем "оценку совпадения" (меньше = лучше)
            # Учитываем и разницу в навыках, и разницу в количестве игр
            score = skill_diff * 2 + games_diff * 0.1
            
            if score < best_score:
                best_score = score
                best_match = opponent
    
    # Если не нашли идеального противника, расширяем критерии
    if not best_match:
        logger.info(f"Не найден идеальный противник для {user.id} в очереди, расширяем критерии")
        max_skill_diff *= 2
        max_games_diff *= 2
        
        for opponent_id, opponent_data in waiting_queue_dict.items():
            if opponent_id == user.id:
                continue
            
            opponent = opponent_data.get('user')
            if not opponent:
                continue
            
            opponent_stats = get_player_stats(opponent)
            opponent_win_rate = opponent_stats['win_rate']
            opponent_total_games = opponent_stats['total_games']
            
            skill_diff = abs(user_win_rate - opponent_win_rate)
            games_diff = abs(user_total_games - opponent_total_games)
            
            if skill_diff <= max_skill_diff and games_diff <= max_games_diff:
                score = skill_diff * 2 + games_diff * 0.1
                
                if score < best_score:
                    best_score = score
                    best_match = opponent
    
    return best_match
