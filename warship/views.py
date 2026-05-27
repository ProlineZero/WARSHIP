import logging
from rest_framework.decorators import api_view
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Q
from rest_framework import status
from rest_framework.request import Request
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError

from core.auth.admin_access import IsActiveUser
from core.auth.bot_access import get_request_user_bot_id, is_bot_request
from core.models.user import User
from warship.models import GameSession, ShipPlacement, GameMove
from warship.matchmaking import find_opponent_from_queue
from warship.centrifugo import publish_to_game, publish_to_user, generate_centrifugo_token
from warship.game_status import broadcast_game_status, get_game_status_data
from warship.services.bot_binding import attach_bot_to_game_if_needed
from warship.services.game_control import publish_shot_result, queue_manual_move
from warship.services.peer_finish import finalize_peer_game
from warship.game_presence import (
    clear_presence,
    touch_presence_for_active_game,
    try_cancel_game_if_abandoned,
)

logger = logging.getLogger('ws_app')

class CentrifugoTokenAPIView(APIView):
    """Эндпоинт для получения JWT токена Centrifugo"""
    permission_classes = [IsAuthenticated, IsActiveUser]
    
    def get(self, request):
        token = generate_centrifugo_token(request.user.id)
        return Response({'token': token})


class MatchmakingFindAPIView(APIView):
    """Запрос на поиск игры"""
    permission_classes = [IsAuthenticated, IsActiveUser]
    
    def get_active_game_data(self, user: User):
        try:
            active_game = GameSession.objects.select_related(
                'player1', 'player2', 'current_turn'
            ).filter(
                Q(player1=user) | Q(player2=user)
            ).exclude(
                status__in=[
                    GameSession.GameStatus.FINISHED,
                    GameSession.GameStatus.CANCELLED
                ]
            ).order_by('-started_at').first()
            
            if not active_game:
                return None
            
            opponent = active_game.player2 if active_game.player1_id == user.id else active_game.player1
            return {
                'game_id': active_game.id,
                'status': active_game.status,
                'opponent': {
                    'id': opponent.id if opponent else None,
                    'username': opponent.username if opponent else None,
                } if opponent else None,
                'player1': {
                    'id': active_game.player1.id,
                    'username': active_game.player1.username
                },
                'player2': {
                    'id': active_game.player2.id if active_game.player2 else None,
                    'username': active_game.player2.username if active_game.player2 else None,
                } if active_game.player2 else None,
                'current_turn': {
                    'id': active_game.current_turn.id,
                    'username': active_game.current_turn.username,
                } if active_game.current_turn else None,
                'play_mode': active_game.play_mode,
            }
        except Exception as e:
            logger.error(f"Ошибка при получении активной игры для пользователя {user.id}: {e}")
            return None

    def post(self, request: Request):
        user: User = request.user
        is_training = False
        if is_bot_request(request):
            is_training = request.data.get('is_training', True)

        # Проверяем наличие активных игр
        active_game_data = self.get_active_game_data(user)
        if active_game_data:
            return Response({
                'action': 'active_game_found',
                'status': 'success',
                'data': active_game_data
            })
            
        # Работа с очередью
        queue = cache.get('matchmaking_queue', {})
        
        # Ищем противника
        opponent = find_opponent_from_queue(user, queue)
        
        if opponent:
            # Проверяем не создана ли уже игра
            existing_game = GameSession.objects.filter(
                Q(player1=user, player2=opponent) | Q(player1=opponent, player2=user), is_training=is_training
            ).exclude(
                status__in=[GameSession.GameStatus.FINISHED, GameSession.GameStatus.CANCELLED]
            ).first()
            
            if existing_game:
                game_session = existing_game
            else:
                play_mode = (
                    GameSession.PlayMode.PEER if is_training else GameSession.PlayMode.SERVER
                )
                game_session = GameSession.objects.create(
                    player1=user,
                    player2=opponent,
                    status=GameSession.GameStatus.WAITING_SHIPS,
                    is_training=is_training,
                    play_mode=play_mode,
                )
                if is_bot_request(request):
                    if game_session.player1_id == user.id:
                        game_session.player1_bot_id = get_request_user_bot_id(request)
                    else:
                        game_session.player2_bot_id = get_request_user_bot_id(request)
                    game_session.save(update_fields=['player1_bot', 'player2_bot'])
            
            # Удаляем из очереди
            queue.pop(user.id, None)
            queue.pop(opponent.id, None)
            cache.set('matchmaking_queue', queue, timeout=3600)
            
            # Уведомляем обоих игроков через Centrifugo
            message_data_base = {
                'game_id': game_session.id,
                'player1': {'id': game_session.player1.id, 'username': game_session.player1.username},
                'player2': {'id': game_session.player2.id, 'username': game_session.player2.username}
            }
            
            # Уведомление первому
            publish_to_user(game_session.player1.id, {
                'action': 'game_found',
                'status': 'success',
                'data': {
                    'opponent': {'id': game_session.player2.id, 'username': game_session.player2.username},
                    **message_data_base
                }
            })
            
            # Уведомление второму
            publish_to_user(game_session.player2.id, {
                'action': 'game_found',
                'status': 'success',
                'game_status': game_session.status,
                'data': {
                    'opponent': {'id': game_session.player1.id, 'username': game_session.player1.username},
                    **message_data_base
                }
            })
            
            return Response({
                'action': 'game_found',
                'status': 'success',
                'message': 'Противник найден'
            })
        else:
            # Добавляем в очередь
            queue[user.id] = {
                'user': user,
                'started_at': timezone.now()
            }
            cache.set('matchmaking_queue', queue, timeout=3600)
            
            return Response({
                'action': 'search_started',
                'status': 'success',
                'message': 'Поиск противника начат'
            })


class MatchmakingCancelAPIView(APIView):
    """Отмена поиска игры"""
    permission_classes = [IsAuthenticated, IsActiveUser]
    
    def post(self, request):
        queue = cache.get('matchmaking_queue', {})
        if request.user.id in queue:
            del queue[request.user.id]
            cache.set('matchmaking_queue', queue, timeout=3600)
            
        return Response({
            'action': 'search_cancelled',
            'status': 'success',
            'message': 'Поиск игры отменен'
        })


# --- Вспомогательные функции для Game API ---

def _get_participant_game(request, game_id, *, touch_presence=True):
    game_session = GameSession.objects.filter(id=game_id).select_related('player1', 'player2').first()
    if not game_session:
        return None, Response({'error': 'Игра не найдена'}, status=404)
    participant_ids = [game_session.player1_id]
    if game_session.player2_id:
        participant_ids.append(game_session.player2_id)
    if request.user.id not in participant_ids:
        return None, Response({'error': 'Вы не участник этой игры'}, status=403)
    attach_bot_to_game_if_needed(game_session, request)
    if touch_presence:
        touch_presence_for_active_game(game_session, request.user.id)
    return game_session, None


class GameLeaveAPIView(APIView):
    """Явный выход из игры (ускоряет отмену при уходе обоих)."""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request, game_id):
        game_session, error_response = _get_participant_game(request, game_id, touch_presence=False)
        if error_response:
            return error_response

        clear_presence(game_id, request.user.id)
        try_cancel_game_if_abandoned(game_id)

        return Response({
            'action': 'game_left',
            'status': 'success',
            'message': 'Вы вышли из игры',
        })


class GameStatusAPIView(APIView):
    """Получение статуса игры"""
    permission_classes = [IsAuthenticated, IsActiveUser]
    
    def get(self, request, game_id):
        game_session, error_response = _get_participant_game(request, game_id)
        if error_response:
            return error_response
        
        return Response({
            'action': 'game_status',
            'status': 'success',
            'data': get_game_status_data(game_session)
        })


class GameBoardAPIView(APIView):
    """Получение состояния доски"""
    permission_classes = [IsAuthenticated, IsActiveUser]
    
    def get(self, request, game_id):
        game_session, error_response = _get_participant_game(request, game_id)
        if error_response:
            return error_response
            
        my_placement = ShipPlacement.objects.filter(
            game_session=game_session,
            player=request.user
        ).first()
        
        opponent = game_session.player2 if game_session.player1_id == request.user.id else game_session.player1
        
        my_shots = list(GameMove.objects.filter(
            game_session=game_session,
            player=request.user
        ).values('row', 'col', 'hit', 'ship_destroyed', 'ship_size'))
        
        opponent_shots = list(GameMove.objects.filter(
            game_session=game_session,
            player=opponent
        ).values('row', 'col', 'hit', 'ship_destroyed', 'ship_size')) if opponent else []

        if game_session.is_peer_mode() and game_session.status != GameSession.GameStatus.WAITING_SHIPS:
            return Response({
                'action': 'board_state',
                'status': 'success',
                'data': {
                    'my_ships': [],
                    'my_shots': [],
                    'opponent_shots': [],
                    'board_size': game_session.board_size,
                    'play_mode': game_session.play_mode,
                },
            })

        return Response({
            'action': 'board_state',
            'status': 'success',
            'data': {
                'my_ships': my_placement.ships if my_placement else [],
                'my_shots': my_shots,
                'opponent_shots': opponent_shots,
                'board_size': game_session.board_size,
                'play_mode': game_session.play_mode,
            }
        })


class GamePlaceShipsAPIView(APIView):
    """Размещение кораблей"""
    permission_classes = [IsAuthenticated, IsActiveUser]
    
    def post(self, request, game_id):
        ships_data = request.data.get('ships', [])
        if not ships_data:
            return Response({'error': 'Не указаны корабли для размещения'}, status=400)
            
        game_session, error_response = _get_participant_game(request, game_id)
        if error_response:
            return error_response
            
        if game_session.status != GameSession.GameStatus.WAITING_SHIPS:
            return Response({'error': 'Игра уже начата, нельзя размещать корабли'}, status=400)
            
        placement, _ = ShipPlacement.objects.get_or_create(
            game_session=game_session,
            player=request.user,
            defaults={'ships': [], 'ships_placed': False}
        )
        
        try:
            placement.set_ships(ships_data)
        except Exception as e:
            return Response({'error': str(e)}, status=400)
            
        # Проверяем старт игры
        player1_placement = ShipPlacement.objects.filter(game_session=game_session, player=game_session.player1).first()
        player2_placement = ShipPlacement.objects.filter(game_session=game_session, player=game_session.player2).first()
        
        if player1_placement and player1_placement.ships_placed and player2_placement and player2_placement.ships_placed:
            try:
                game_session.start_game()
                game_session.refresh_from_db()
                
                # Уведомляем о старте
                current_turn_data = None
                if game_session.current_turn:
                    current_turn_data = {'id': game_session.current_turn.id, 'username': game_session.current_turn.username}
                    
                publish_to_game(game_session.id, {
                    'action': 'game_started',
                    'status': 'success',
                    'data': {
                        'game_id': game_session.id,
                        'current_turn': current_turn_data,
                        'started_at': game_session.started_at.isoformat() if game_session.started_at else None,
                        'play_mode': game_session.play_mode,
                    }
                })
                if game_session.is_peer_mode():
                    game_session.purge_placement_data()
            except ValidationError:
                pass
                
        broadcast_game_status(game_session)
        
        return Response({
            'action': 'place_ships',
            'status': 'success',
            'message': 'Корабли успешно размещены'
        })


class GameMakeShotAPIView(APIView):
    """Выполнение выстрела"""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request, game_id):
        row = request.data.get('row')
        col = request.data.get('col')

        if row is None or col is None:
            return Response({'error': 'Не указаны координаты выстрела (row, col)'}, status=400)

        game_session, error_response = _get_participant_game(request, game_id)
        if error_response:
            return error_response

        if game_session.is_peer_mode():
            return Response(
                {
                    'error': 'В режиме peer ходы выполняются через Centrifugo',
                    'play_mode': game_session.play_mode,
                },
                status=409,
            )

        if game_session.status == GameSession.GameStatus.WAITING_SHIPS:
            return Response({'error': 'Игра еще не начата'}, status=400)

        if game_session.status == GameSession.GameStatus.FINISHED:
            return Response({'error': 'Игра уже завершена'}, status=400)

        if game_session.current_turn_id != request.user.id:
            return Response({'error': 'Сейчас не ваш ход'}, status=400)

        if game_session.is_paused:
            return Response({'error': 'Игра на паузе'}, status=423)

        from warship.models import make_shot

        if game_session.admin_control_mode == GameSession.AdminControlMode.MANUAL_STEP:
            from warship.models import validate_shot

            shot_validation = validate_shot(game_session, request.user, row, col)
            if not shot_validation['valid']:
                return Response({'error': shot_validation['error']}, status=400)

            queued = queue_manual_move(
                game_session,
                request.user,
                row,
                col,
                bot_id=get_request_user_bot_id(request),
            )
            return Response({
                'action': 'make_shot',
                'status': 'pending',
                'data': queued,
            }, status=202)

        try:
            result = make_shot(game_session, request.user, row, col)
        except Exception as e:
            return Response({'error': str(e)}, status=400)

        if not result['success']:
            if result.get('retry_after_ms'):
                return Response({'error': result.get('error'), 'retry_after_ms': result['retry_after_ms']}, status=429)
            return Response({'error': result.get('error', 'Ошибка выстрела')}, status=400)

        result_to_send = publish_shot_result(game_session, result)

        return Response({
            'action': 'make_shot',
            'status': 'success',
            'data': result_to_send,
        })


class GameFinishAPIView(APIView):
    """Завершение peer-игры (fallback к publish на finish:{id})."""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request, game_id):
        winner_id = request.data.get('winner_id')
        if winner_id is None:
            return Response({'error': 'Не указан winner_id'}, status=400)

        game_session, error_response = _get_participant_game(request, game_id)
        if error_response:
            return error_response

        if not game_session.is_peer_mode():
            return Response({'error': 'Завершение через API доступно только в режиме peer'}, status=400)

        try:
            payload = finalize_peer_game(game_session, int(winner_id), request.user.id)
        except ValidationError as exc:
            return Response({'error': str(exc)}, status=400)

        return Response({
            'action': 'game_finished',
            'status': 'success',
            'data': payload,
        })


# Апи для того чтобы бросить вызов другому игроку
class GameChallengeAPIView(APIView):
    """Бросить вызов другому игроку"""
    permission_classes = [IsAuthenticated, IsActiveUser]
    
    def post(self, request):
        opponent_id = request.data.get('opponent_id')
        if not opponent_id:
            return Response({'error': 'Не указан ID противника'}, status=400)

        opponent: User = User.objects.filter(id=opponent_id).first()
        if not opponent:
            return Response({'error': 'Игрок не найден'}, status=404)
        
        user = request.user
        if user.id == opponent_id:
            return Response({'error': 'Вы не можете бросить вызов себе'}, status=400)

        game_session = GameSession.objects.create(
            player1=user,
            player2=opponent,
            status=GameSession.GameStatus.WAITING_CHALLENGE,
            is_training=True,
        )
        if is_bot_request(request):
            game_session.player1_bot_id = get_request_user_bot_id(request)
            game_session.save(update_fields=['player1_bot'])

        challenge_data = {
            "action": "challenge_created",
            "game_id": game_session.id,
            "game_status": game_session.status,
            "opponent": {
                'id': user.id,
                'username': user.username,
                'stats': user.metadata.get('stats', {}),
            },
        }
        publish_to_user(opponent.id, challenge_data)
        
        # Уведомляем обоих игроков через Centrifugo
        message_data_base = {
            'game_id': game_session.id,
            'status': 'success',
            'game_status': game_session.status,
            'player1': {'id': game_session.player1.id, 'username': game_session.player1.username},
            'player2': {'id': game_session.player2.id, 'username': game_session.player2.username}
        }
        
        # Уведомление первому
        publish_to_user(user.id, {
            'action': 'game_found',
            'status': 'success',
            'data': {
                'opponent': {'id': game_session.player2.id, 'username': game_session.player2.username},
                **message_data_base
            }
        })
        return Response(message_data_base)

@api_view(['POST'])
def accept_challenge(request, game_id):
    game_session: GameSession | None = GameSession.objects.filter(id=game_id).first()
    if not game_session:
        return Response({'error': 'Игра не найдена'}, status=404)
    if game_session.status != GameSession.GameStatus.WAITING_CHALLENGE:
        return Response({'error': 'Игра не находится в состоянии ожидания вызова'}, status=400)
    if game_session.player1_id != request.user.id and game_session.player2_id != request.user.id:
        return Response({'error': 'Вы не участник этой игры'}, status=403)
    game_session.status = GameSession.GameStatus.WAITING_SHIPS
    game_session.save()
    user = request.user
    opponent = game_session.get_opponent(user)
    
    message_data_base = {
        'game_id': game_session.id,
        'status': 'success',
        'game_status': game_session.status,
        'player1': {'id': game_session.player1.id, 'username': game_session.player1.username},
        'player2': {'id': game_session.player2.id, 'username': game_session.player2.username}
    }
    for player in (user, opponent):
        publish_to_user(player.id, {
            'action': 'game_found',
            'status': 'success',
            'data': {
                'opponent': {
                    'id': opponent.id if player == user else user.id,
                    'username': opponent.username if player == user else user.username,
                },
                **message_data_base
            }
        })
    return Response({'message': 'Вызов принят'})