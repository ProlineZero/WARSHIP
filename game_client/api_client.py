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

    def login(self, login: str, password: str) -> dict:
        payload = self._request('POST', '/auth/login/', json={'login': login, 'password': password})
        self.access_token = payload['access']
        self.refresh_token = payload.get('refresh')
        me = self.get_me()
        self.user_id = me['id']
        self.username = me.get('username') or str(me.get('phone') or me['id'])
        return payload

    def get_me(self) -> dict:
        return self._request('GET', '/user/me/')

    def get_centrifugo_token(self) -> str:
        return self._request('GET', '/warship/centrifugo/token/')['token']

    def matchmaking_find(self) -> dict:
        return self._request('POST', '/warship/matchmaking/find/', json={})

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
