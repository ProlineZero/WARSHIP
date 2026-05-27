import json
from unittest.mock import patch

from django.test import RequestFactory, TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models.user import User
from warship.centrifugo_proxy import CentrifugoPublishProxyView, CentrifugoSubscribeProxyView
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


class PeerModeTestCase(TestCase):
    def setUp(self):
        self.centrifugo_patcher = patch('warship.centrifugo.get_centrifugo_client')
        mock_client = self.centrifugo_patcher.start()
        mock_client.return_value.publish.return_value = None

        self.player1 = User.objects.create_user(username='p1', password='pass1')
        self.player2 = User.objects.create_user(username='p2', password='pass2')
        self.client1 = auth_client(self.player1)
        self.client2 = auth_client(self.player2)
        self.factory = RequestFactory()

    def tearDown(self):
        self.centrifugo_patcher.stop()

    def _create_peer_game(self, started: bool = True) -> GameSession:
        game = GameSession.objects.create(
            player1=self.player1,
            player2=self.player2,
            status=GameSession.GameStatus.WAITING_SHIPS,
            is_training=True,
            play_mode=GameSession.PlayMode.PEER,
        )
        ShipPlacement.objects.create(
            game_session=game,
            player=self.player1,
            ships=VALID_SHIPS,
            ships_placed=True,
        )
        ShipPlacement.objects.create(
            game_session=game,
            player=self.player2,
            ships=VALID_SHIPS,
            ships_placed=True,
        )
        if started:
            game.start_game()
            game.purge_placement_data()
            game.refresh_from_db()
        return game

    def test_make_shot_returns_409_in_peer_mode(self):
        game = self._create_peer_game()
        response = self.client1.post(
            f'/api/warship/game/{game.id}/make_shot/',
            {'row': 0, 'col': 0},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['play_mode'], 'peer')
        self.assertEqual(GameMove.objects.filter(game_session=game).count(), 0)

    def test_board_empty_after_peer_start(self):
        game = self._create_peer_game()
        response = self.client1.get(f'/api/warship/game/{game.id}/board/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['my_ships'], [])
        self.assertEqual(response.data['data']['my_shots'], [])

    def test_place_ships_purges_coordinates_on_start(self):
        game = GameSession.objects.create(
            player1=self.player1,
            player2=self.player2,
            status=GameSession.GameStatus.WAITING_SHIPS,
            is_training=True,
            play_mode=GameSession.PlayMode.PEER,
        )
        ShipPlacement.objects.create(
            game_session=game,
            player=self.player2,
            ships=VALID_SHIPS,
            ships_placed=True,
        )
        response = self.client1.post(
            f'/api/warship/game/{game.id}/place_ships/',
            {'ships': VALID_SHIPS},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        game.refresh_from_db()
        self.assertEqual(game.status, GameSession.GameStatus.PLAYER1_TURN)
        placement = ShipPlacement.objects.get(game_session=game, player=self.player1)
        self.assertEqual(placement.ships, [])
        self.assertTrue(placement.ships_placed)

    def test_finish_api_records_winner(self):
        game = self._create_peer_game()
        response = self.client1.post(
            f'/api/warship/game/{game.id}/finish/',
            {'winner_id': self.player1.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        game.refresh_from_db()
        self.assertEqual(game.status, GameSession.GameStatus.FINISHED)
        self.assertEqual(game.winner_id, self.player1.id)
        self.assertEqual(GameMove.objects.filter(game_session=game).count(), 0)

    def test_publish_proxy_finish_channel(self):
        game = self._create_peer_game()
        view = CentrifugoPublishProxyView.as_view()
        request = self.factory.post(
            '/api/warship/centrifugo/proxy/publish/',
            data=json.dumps({
                'channel': f'finish:{game.id}',
                'user': self.player1.id,
                'data': {'action': 'game_finished', 'winner_id': self.player2.id},
            }),
            content_type='application/json',
        )
        response = view(request)
        self.assertEqual(response.status_code, 200)
        game.refresh_from_db()
        self.assertEqual(game.status, GameSession.GameStatus.FINISHED)
        self.assertEqual(game.winner_id, self.player2.id)

    def test_subscribe_user_channel_only_own(self):
        view = CentrifugoSubscribeProxyView.as_view()
        request = self.factory.post(
            '/api/warship/centrifugo/proxy/subscribe/',
            data=json.dumps({'channel': f'user_{self.player2.id}', 'user': self.player1.id}),
            content_type='application/json',
        )
        response = view(request)
        self.assertEqual(response.status_code, 403)

    def test_matchmaking_blocks_unfinished_peer_game(self):
        self._create_peer_game()
        response = self.client1.post(
            '/api/warship/matchmaking/find/',
            {'is_training': True},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['action'], 'active_game_found')

    def test_training_matchmaking_sets_peer_mode(self):
        with patch('warship.views.is_bot_request', return_value=True):
            with patch('warship.views.find_opponent_from_queue', return_value=self.player2):
                with patch('warship.views.cache') as mock_cache:
                    mock_cache.get.return_value = {}
                    response = self.client1.post(
                        '/api/warship/matchmaking/find/',
                        {'is_training': True},
                        format='json',
                    )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['action'], 'game_found')
        game = GameSession.objects.filter(
            player1=self.player1,
            player2=self.player2,
        ).latest('started_at')
        self.assertEqual(game.play_mode, GameSession.PlayMode.PEER)
