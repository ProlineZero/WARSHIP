from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models.group import PlayerGroup
from core.models.user import User
from core.models.user_bot import UserBot
from core.tokens.user_bot import UserBotRefreshToken
from warship.models import GameMove, GameSession, ShipPlacement


VALID_SHIPS = [
    {'size': 4, 'cells': [[0, 0], [0, 1], [0, 2], [0, 3]]},
    {'size': 3, 'cells': [[2, 0], [2, 1], [2, 2]]},
    {'size': 3, 'cells': [[4, 0], [4, 1], [4, 2]]},
    {'size': 2, 'cells': [[6, 0], [6, 1]]},
    {'size': 2, 'cells': [[8, 0], [8, 1]]},
    {'size': 2, 'cells': [[1, 5], [1, 6]]},
    {'size': 1, 'cells': [[3, 5]]},
    {'size': 1, 'cells': [[5, 5]]},
    {'size': 1, 'cells': [[7, 5]]},
    {'size': 1, 'cells': [[9, 5]]},
]


def auth_client(user: User) -> APIClient:
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')
    return client


def bot_auth_client(user: User, user_bot: UserBot) -> APIClient:
    client = APIClient()
    token = UserBotRefreshToken.for_user_bot(user, user_bot)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')
    return client


class AdminAPITestCase(TestCase):
    def setUp(self):
        self.centrifugo_patcher = patch('warship.centrifugo.get_centrifugo_client')
        mock_client = self.centrifugo_patcher.start()
        mock_client.return_value.publish.return_value = None

        self.admin = User.objects.create_user(username='admin', password='adminpass', is_staff=True)
        self.student1 = User.objects.create_user(username='student1', password='pass1')
        self.student2 = User.objects.create_user(username='student2', password='pass2')
        self.group = PlayerGroup.objects.create(name='ИТ-21-1')
        self.admin_client = auth_client(self.admin)
        self.student1_client = auth_client(self.student1)

    def tearDown(self):
        self.centrifugo_patcher.stop()

    def test_non_admin_forbidden(self):
        response = self.student1_client.get('/api/admin/groups/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_group_and_add_member_by_credentials(self):
        response = self.admin_client.post('/api/admin/groups/', {'name': 'ИТ-22-2', 'description': 'Test'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        group_id = response.data['id']

        response = self.admin_client.post(
            f'/api/admin/groups/{group_id}/members/',
            {'username': 'new_student', 'password': 'secret123'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['username'], 'new_student')
        self.assertEqual(response.data['group']['id'], group_id)

    def test_add_existing_user_to_group(self):
        response = self.admin_client.post(
            f'/api/admin/groups/{self.group.id}/members/',
            {'user_id': self.student1.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.group_id, self.group.id)

    def test_ban_blocks_login_and_active_api(self):
        self.student1.set_password('pass1')
        self.student1.save()

        response = self.admin_client.post(
            f'/api/admin/users/{self.student1.id}/ban/',
            {'reason': 'Нарушение правил'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_active'])
        self.assertTrue(response.data['is_banned'])

        login_client = APIClient()
        response = login_client.post('/api/auth/login/', {'login': 'student1', 'password': 'pass1'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        banned_client = auth_client(self.student1)
        response = banned_client.get('/api/user/me/')
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_unban_restores_access(self):
        self.student1.is_active = False
        self.student1.ban_reason = 'test'
        self.student1.banned_at = timezone.now()
        self.student1.banned_by = self.admin
        self.student1.save()

        response = self.admin_client.post(f'/api/admin/users/{self.student1.id}/unban/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_active'])

        client = auth_client(self.student1)
        response = client.get('/api/user/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_leaderboard_students_by_group(self):
        self.student1.group = self.group
        self.student1.save()
        self.student2.group = self.group
        self.student2.save()

        game = GameSession.objects.create(
            player1=self.student1,
            player2=self.student2,
            status=GameSession.GameStatus.FINISHED,
            is_training=False,
            winner=self.student1,
            finished_at=timezone.now(),
        )
        self.assertIsNotNone(game.id)

        response = self.admin_client.get(f'/api/admin/leaderboard/students/?group_id={self.group.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 2)
        self.assertEqual(response.data[0]['rank'], 1)
        self.assertEqual(response.data[0]['username'], 'student1')

    def test_leaderboard_bots_per_bot(self):
        bot1 = UserBot.objects.create(name='bot_alpha', user=self.student1)
        bot2 = UserBot.objects.create(name='bot_beta', user=self.student2)

        GameSession.objects.create(
            player1=self.student1,
            player2=self.student2,
            player1_bot=bot1,
            player2_bot=bot2,
            status=GameSession.GameStatus.FINISHED,
            is_training=False,
            winner=self.student1,
            finished_at=timezone.now(),
        )

        response = self.admin_client.get('/api/admin/leaderboard/bots/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ranks = {item['bot_id']: item['rank'] for item in response.data}
        self.assertEqual(ranks[bot1.id], 1)
        self.assertEqual(ranks[bot2.id], 2)

    def test_stats_overview_and_games_by_day(self):
        GameSession.objects.create(
            player1=self.student1,
            player2=self.student2,
            status=GameSession.GameStatus.PLAYER1_TURN,
            is_training=False,
        )
        GameSession.objects.create(
            player1=self.student1,
            player2=self.student2,
            status=GameSession.GameStatus.FINISHED,
            is_training=False,
            finished_at=timezone.now(),
        )

        response = self.admin_client.get('/api/admin/stats/overview/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data['active_games'], 1)
        self.assertGreaterEqual(response.data['finished_today'], 1)

        response = self.admin_client.get('/api/admin/stats/games-by-day/?days=7')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(any(item['total'] >= 1 for item in response.data))

    def test_manual_step_flow(self):
        game = GameSession.objects.create(
            player1=self.student1,
            player2=self.student2,
            status=GameSession.GameStatus.PLAYER1_TURN,
            current_turn=self.student1,
            is_training=True,
            admin_control_mode=GameSession.AdminControlMode.MANUAL_STEP,
        )
        ShipPlacement.objects.create(game_session=game, player=self.student1, ships=VALID_SHIPS, ships_placed=True)
        ShipPlacement.objects.create(game_session=game, player=self.student2, ships=VALID_SHIPS, ships_placed=True)

        response = self.student1_client.post(
            f'/api/warship/game/{game.id}/make_shot/',
            {'row': 9, 'col': 5},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        game.refresh_from_db()
        self.assertIsNotNone(game.pending_move)

        response = self.admin_client.post(f'/api/admin/games/{game.id}/approve-move/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(GameMove.objects.filter(game_session=game, row=9, col=5).exists())

    def test_bot_versus_creates_game(self):
        bot1 = UserBot.objects.create(name='bot1', user=self.student1)
        bot2 = UserBot.objects.create(name='bot2', user=self.student2)

        response = self.admin_client.post(
            '/api/admin/bots/versus/',
            {'bot1_id': bot1.id, 'bot2_id': bot2.id, 'is_training': True},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['data']['player1_bot']['id'], bot1.id)
        self.assertEqual(response.data['data']['player2_bot']['id'], bot2.id)

    def test_admin_board_shows_both_sides(self):
        game = GameSession.objects.create(
            player1=self.student1,
            player2=self.student2,
            status=GameSession.GameStatus.PLAYER1_TURN,
            current_turn=self.student1,
        )
        ShipPlacement.objects.create(game_session=game, player=self.student1, ships=VALID_SHIPS, ships_placed=True)
        ShipPlacement.objects.create(game_session=game, player=self.student2, ships=VALID_SHIPS, ships_placed=True)

        response = self.admin_client.get(f'/api/admin/games/{game.id}/board/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']['player1']['ships']), 10)
        self.assertEqual(len(response.data['data']['player2']['ships']), 10)

    def test_centrifugo_proxy_allows_admin_subscribe(self):
        from warship.centrifugo_proxy import CentrifugoSubscribeProxyView

        game = GameSession.objects.create(
            player1=self.student1,
            player2=self.student2,
            status=GameSession.GameStatus.PLAYER1_TURN,
        )
        view = CentrifugoSubscribeProxyView.as_view()
        request_body = {'channel': f'game_{game.id}', 'user': self.admin.id}
        from django.test import RequestFactory
        import json

        factory = RequestFactory()
        request = factory.post(
            '/api/warship/centrifugo/proxy/subscribe/',
            data=json.dumps(request_body),
            content_type='application/json',
        )
        response = view(request)
        self.assertEqual(response.status_code, 200)
