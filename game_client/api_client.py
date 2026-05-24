from typing import Any

import requests

from config import API_BASE_URL


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class WarshipApiClient:
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url.rstrip('/')
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.user_id: int | None = None
        self.username: str | None = None
        self.is_bot: bool = False
        self.user_bot: dict | None = None

    def _headers(self) -> dict:
        headers = {'Content-Type': 'application/json'}
        if self.access_token:
            headers['Authorization'] = f'Bearer {self.access_token}'
        return headers

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f'{self.base_url}{path}'
        response = requests.request(method, url, headers=self._headers(), timeout=15, **kwargs)
        try:
            data = response.json() if response.content else {}
        except ValueError:
            data = {'raw': response.text}
        if not response.ok:
            error = data.get('error') or data.get('detail') or data
            if isinstance(error, dict):
                error = '; '.join(
                    f'{k}: {v}' if not isinstance(v, list) else f'{k}: {", ".join(str(x) for x in v)}'
                    for k, v in error.items()
                )
            raise ApiError(str(error), response.status_code, data)
        return data

    def _apply_auth(self, payload: dict) -> None:
        self.is_bot = False
        self.user_bot = None
        self.access_token = payload['access']
        self.refresh_token = payload.get('refresh')
        me = self.get_me()
        self.user_id = me['id']
        self.username = me.get('username') or str(me.get('phone') or me['id'])

    def _apply_bot_auth(self, payload: dict) -> None:
        self.is_bot = True
        self.user_bot = payload.get('user_bot')
        self.access_token = payload['access']
        self.refresh_token = payload.get('refresh')
        me = self.get_me()
        self.user_id = me['id']
        self.username = self.user_bot['name'] if self.user_bot else str(me['id'])

    def login(self, login: str, password: str) -> dict:
        payload = self._request('POST', '/auth/login/', json={'login': login, 'password': password})
        self._apply_auth(payload)
        return payload

    def register_request_otp(self, phone: str) -> dict:
        return self._request('POST', '/auth/register/request-otp/', json={'phone': phone})

    def register_confirm_otp(self, phone: str, code: str, password: str) -> dict:
        payload = self._request(
            'POST',
            '/auth/register/confirm-otp/',
            json={'phone': phone, 'code': code, 'password': password},
        )
        self._apply_auth(payload)
        return payload

    def get_me(self) -> dict:
        return self._request('GET', '/user/me/')

    def bot_login(self, token: str) -> dict:
        payload = self._request('POST', '/auth/bot/login/', json={'token': token})
        self._apply_bot_auth(payload)
        return payload

    def list_bots(self) -> list:
        return self._request('GET', '/user/me/bots/')

    def create_bot(self, name: str, description: str = '') -> dict:
        body = {'name': name}
        if description:
            body['description'] = description
        return self._request('POST', '/user/me/bots/', json=body)

    def delete_bot(self, bot_id: int) -> None:
        self._request('DELETE', f'/user/me/bots/{bot_id}/')

    def get_centrifugo_token(self) -> str:
        return self._request('GET', '/warship/centrifugo/token/')['token']

    def matchmaking_find(self, is_training: bool | None = None) -> dict:
        body: dict = {}
        if is_training is not None:
            body['is_training'] = is_training
        return self._request('POST', '/warship/matchmaking/find/', json=body)

    def matchmaking_cancel(self) -> dict:
        return self._request('POST', '/warship/matchmaking/cancel/', json={})

    def challenge(self, opponent_id: int) -> dict:
        return self._request('POST', '/warship/challenge/', json={'opponent_id': opponent_id})

    def accept_challenge(self, game_id: int) -> dict:
        return self._request('POST', f'/warship/game/{game_id}/accept_challenge/', json={})

    def game_status(self, game_id: int) -> dict:
        return self._request('GET', f'/warship/game/{game_id}/status/')

    def game_board(self, game_id: int) -> dict:
        return self._request('GET', f'/warship/game/{game_id}/board/')['data']

    def place_ships(self, game_id: int, ships: list) -> dict:
        return self._request('POST', f'/warship/game/{game_id}/place_ships/', json={'ships': ships})

    def make_shot(self, game_id: int, row: int, col: int) -> dict:
        return self._request('POST', f'/warship/game/{game_id}/make_shot/', json={'row': row, 'col': col})

    def leave_game(self, game_id: int) -> dict:
        return self._request('POST', f'/warship/game/{game_id}/leave/', json={})
