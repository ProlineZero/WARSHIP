from django.db.models import Q
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.auth.admin_access import IsActiveUser, IsAdminUser
from core.models.user_bot import UserBot
from warship.centrifugo import generate_centrifugo_token, publish_to_user
from warship.game_status import get_game_status_data
from warship.models import GameMove, GameSession, ShipPlacement
from warship.services.game_control import approve_pending_move, publish_shot_result
from warship.utils import get_bot_stats


ACTIVE_STATUSES = [
    GameSession.GameStatus.WAITING_CHALLENGE,
    GameSession.GameStatus.WAITING_SHIPS,
    GameSession.GameStatus.PLAYER1_TURN,
    GameSession.GameStatus.PLAYER2_TURN,
]


def _bot_is_active(bot_id: int) -> bool:
    return GameSession.objects.filter(
        Q(player1_bot_id=bot_id) | Q(player2_bot_id=bot_id),
        status__in=ACTIVE_STATUSES,
    ).exists()


def _bot_last_game_at(bot_id: int):
    game = GameSession.objects.filter(
        Q(player1_bot_id=bot_id) | Q(player2_bot_id=bot_id),
    ).order_by('-started_at').first()
    return game.started_at.isoformat() if game else None


class AdminCentrifugoTokenAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def get(self, request):
        return Response({'token': generate_centrifugo_token(request.user.id)})


class AdminBotListAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def get(self, request):
        queryset = UserBot.objects.select_related('user', 'user__group')
        group_id = request.query_params.get('group_id')
        active_only = request.query_params.get('active_only', '').lower() in ('1', 'true', 'yes')

        if group_id:
            queryset = queryset.filter(user__group_id=group_id)

        bots = []
        for bot in queryset:
            is_active = _bot_is_active(bot.id)
            if active_only and not is_active:
                continue
            bots.append({
                'id': bot.id,
                'name': bot.name,
                'description': bot.description,
                'owner': {
                    'id': bot.user_id,
                    'username': bot.user.username,
                    'group_id': bot.user.group_id,
                    'group_name': bot.user.group.name if bot.user.group_id else None,
                },
                'stats': bot.metadata.get('stats') or get_bot_stats(bot),
                'is_in_active_game': is_active,
                'last_game_at': _bot_last_game_at(bot.id),
                'created_at': bot.created_at.isoformat(),
            })

        return Response(bots)


class AdminBotChallengeAPIView(APIView):
    """Админ играет против бота."""
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def post(self, request, bot_id):
        bot = UserBot.objects.select_related('user').filter(id=bot_id).first()
        if not bot:
            raise NotFound(detail='Бот не найден.')

        game_session = GameSession.objects.create(
            player1=request.user,
            player2=bot.user,
            player2_bot=bot,
            status=GameSession.GameStatus.WAITING_SHIPS,
            is_training=True,
            play_mode=GameSession.PlayMode.PEER,
        )

        publish_to_user(request.user.id, {
            'action': 'game_found',
            'status': 'success',
            'data': {
                'game_id': game_session.id,
                'opponent': {'id': bot.user.id, 'username': bot.user.username},
                'player1': {'id': request.user.id, 'username': request.user.username},
                'player2': {'id': bot.user.id, 'username': bot.user.username},
            },
        })
        publish_to_user(bot.user.id, {
            'action': 'game_found',
            'status': 'success',
            'data': {
                'game_id': game_session.id,
                'opponent': {'id': request.user.id, 'username': request.user.username},
                'player1': {'id': request.user.id, 'username': request.user.username},
                'player2': {'id': bot.user.id, 'username': bot.user.username},
            },
        })

        return Response({
            'action': 'game_created',
            'status': 'success',
            'data': get_game_status_data(game_session),
        }, status=status.HTTP_201_CREATED)


class AdminBotVersusAPIView(APIView):
    """Запускает игру bot vs bot."""
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def post(self, request):
        bot1_id = request.data.get('bot1_id')
        bot2_id = request.data.get('bot2_id')
        is_training = request.data.get('is_training', True)

        if not bot1_id or not bot2_id:
            return Response({'error': 'Укажите bot1_id и bot2_id.'}, status=400)
        if bot1_id == bot2_id:
            return Response({'error': 'Боты должны быть разными.'}, status=400)

        bot1 = UserBot.objects.select_related('user').filter(id=bot1_id).first()
        bot2 = UserBot.objects.select_related('user').filter(id=bot2_id).first()
        if not bot1 or not bot2:
            raise NotFound(detail='Один из ботов не найден.')

        play_mode = GameSession.PlayMode.PEER if is_training else GameSession.PlayMode.SERVER
        game_session = GameSession.objects.create(
            player1=bot1.user,
            player2=bot2.user,
            player1_bot=bot1,
            player2_bot=bot2,
            status=GameSession.GameStatus.WAITING_SHIPS,
            is_training=is_training,
            play_mode=play_mode,
        )

        for bot in (bot1, bot2):
            publish_to_user(bot.user.id, {
                'action': 'game_found',
                'status': 'success',
                'data': {
                    'game_id': game_session.id,
                    'game_status': game_session.status,
                    'player1': {'id': bot1.user.id, 'username': bot1.user.username},
                    'player2': {'id': bot2.user.id, 'username': bot2.user.username},
                },
            })

        return Response({
            'action': 'game_created',
            'status': 'success',
            'data': get_game_status_data(game_session),
        }, status=status.HTTP_201_CREATED)


class AdminActiveGamesAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def get(self, request):
        queryset = GameSession.objects.filter(
            status__in=ACTIVE_STATUSES,
        ).select_related(
            'player1', 'player2', 'player1_bot', 'player2_bot', 'current_turn',
        )

        group_id = request.query_params.get('group_id')
        if group_id:
            queryset = queryset.filter(
                Q(player1__group_id=group_id) | Q(player2__group_id=group_id)
            )

        has_bot = request.query_params.get('has_bot')
        if has_bot is not None and has_bot.lower() in ('1', 'true', 'yes'):
            queryset = queryset.filter(Q(player1_bot__isnull=False) | Q(player2_bot__isnull=False))

        return Response({
            'action': 'active_games',
            'status': 'success',
            'data': [get_game_status_data(game) for game in queryset],
        })


class AdminGameDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def get(self, request, game_id):
        game = GameSession.objects.select_related(
            'player1', 'player2', 'player1_bot', 'player2_bot', 'current_turn', 'winner',
        ).filter(id=game_id).first()
        if not game:
            raise NotFound(detail='Игра не найдена.')
        return Response({
            'action': 'game_detail',
            'status': 'success',
            'data': get_game_status_data(game),
        })


class AdminGameBoardAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def get(self, request, game_id):
        game = GameSession.objects.select_related('player1', 'player2').filter(id=game_id).first()
        if not game:
            raise NotFound(detail='Игра не найдена.')

        def board_for(player):
            placement = ShipPlacement.objects.filter(game_session=game, player=player).first()
            shots = list(GameMove.objects.filter(game_session=game, player=player).values(
                'row', 'col', 'hit', 'ship_destroyed', 'ship_size'
            ))
            return {
                'player_id': player.id,
                'username': player.username,
                'ships': placement.ships if placement else [],
                'shots': shots,
            }

        return Response({
            'action': 'admin_board_state',
            'status': 'success',
            'data': {
                'game_id': game.id,
                'board_size': game.board_size,
                'player1': board_for(game.player1),
                'player2': board_for(game.player2) if game.player2 else None,
            },
        })


class AdminGameControlAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def post(self, request, game_id):
        game = GameSession.objects.filter(id=game_id).first()
        if not game:
            raise NotFound(detail='Игра не найдена.')

        update_fields = []
        if 'admin_control_mode' in request.data:
            game.admin_control_mode = request.data['admin_control_mode']
            update_fields.append('admin_control_mode')
        if 'move_delay_ms' in request.data:
            game.move_delay_ms = int(request.data['move_delay_ms'])
            update_fields.append('move_delay_ms')
        if 'is_paused' in request.data:
            game.is_paused = bool(request.data['is_paused'])
            update_fields.append('is_paused')
        if 'play_mode' in request.data:
            game.play_mode = request.data['play_mode']
            update_fields.append('play_mode')

        if update_fields:
            game.save(update_fields=update_fields)

        from warship.game_status import broadcast_game_status
        broadcast_game_status(game)

        return Response({
            'action': 'game_control_updated',
            'status': 'success',
            'data': get_game_status_data(game),
        })


class AdminGameApproveMoveAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def post(self, request, game_id):
        game = GameSession.objects.filter(id=game_id).first()
        if not game:
            raise NotFound(detail='Игра не найдена.')

        result, error = approve_pending_move(game)
        if error:
            return Response({'error': error}, status=400)

        result_to_send = publish_shot_result(game, result)
        return Response({
            'action': 'approve_move',
            'status': 'success',
            'data': result_to_send,
        })
