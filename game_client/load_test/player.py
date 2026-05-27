import asyncio
import logging
import random
import time
from typing import Any

import httpx

from config import BOARD_SIZE
from load_test.async_realtime import AsyncRealtimeClient
from load_test.stats import StatsCollector
from peer_battle import PeerBattleState
from ships import generate_random_fleet

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}


def _format_api_error(data: dict, status_code: int) -> str:
    err = data.get('error') or data.get('detail')
    if err:
        if isinstance(err, dict):
            return '; '.join(
                f'{key}: {value}' if not isinstance(value, list) else f'{key}: {", ".join(str(item) for item in value)}'
                for key, value in err.items()
            )
        return str(err)

    raw = data.get('raw', '')
    if raw and ('<!DOCTYPE' in raw or '<html' in raw.lower()):
        title_match = __import__('re').search(r'<pre class="exception_value">([^<]+)', raw)
        if title_match:
            return f'HTTP {status_code}: {title_match.group(1).strip()}'
        title_match = __import__('re').search(r'<title>\s*([^<]+?)\s*</title>', raw, __import__('re').IGNORECASE)
        if title_match:
            return f'HTTP {status_code}: {title_match.group(1).strip()}'
        return f'HTTP {status_code}: server error'

    if raw:
        return raw[:240]
    return f'HTTP {status_code}: request failed'


def _short_error(exc: Exception) -> str:
    message = str(exc)
    return message if len(message) <= 240 else f'{message[:240]}...'


class AsyncApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class AsyncPlayer:
    def __init__(
        self,
        account: dict,
        api_url: str,
        ws_url: str,
        stats: StatsCollector,
        use_ws: bool = True,
        turn_delay: float = 0.0,
        poll_interval: float = 0.01,
    ):
        self.account = account
        self.api_url = api_url.rstrip('/')
        self.ws_url = ws_url
        self.stats = stats
        self.use_ws = use_ws
        self.turn_delay = turn_delay
        self.poll_interval = poll_interval
        self.access_token: str | None = None
        self.user_id: int | None = None
        self.game_id: int | None = None
        self._client: httpx.AsyncClient | None = None
        self._realtime: AsyncRealtimeClient | None = None
        self._ready = asyncio.Event()
        self._barrier: asyncio.Event | None = None
        self._peer_fleet: list[dict] | None = None
        self._peer_battle: PeerBattleState | None = None

    def set_barrier(self, barrier: asyncio.Event) -> None:
        self._barrier = barrier

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        if not self._client:
            raise RuntimeError('HTTP client not initialized')
        url = f'{self.api_url}{path}'
        headers = kwargs.pop('headers', {})
        headers.setdefault('Content-Type', 'application/json')
        if self.access_token:
            headers['Authorization'] = f'Bearer {self.access_token}'
        started = time.monotonic()
        try:
            response = await self._client.request(method, url, headers=headers, timeout=15.0, **kwargs)
            latency_ms = (time.monotonic() - started) * 1000
            try:
                data = response.json() if response.content else {}
            except ValueError:
                data = {'raw': response.text}
            if not response.is_success:
                err = _format_api_error(data, response.status_code)
                self.stats.record_request(latency_ms, error=True)
                raise AsyncApiError(err, response.status_code)
            self.stats.record_request(latency_ms, error=False)
            return data
        except AsyncApiError:
            raise
        except Exception:
            self.stats.record_request((time.monotonic() - started) * 1000, error=True)
            raise

    async def _get_centrifugo_token(self) -> str:
        return (await self._request('GET', '/warship/centrifugo/token/'))['token']

    async def login(self) -> None:
        payload = await self._request(
            'POST',
            '/auth/bot/login/',
            json={'token': self.account['bot_token']},
        )
        self.access_token = payload['access']
        me = await self._request('GET', '/user/me/')
        self.user_id = me['id']

    async def connect_realtime(self) -> None:
        if not self.use_ws or not self.user_id:
            return
        self._realtime = AsyncRealtimeClient(self.ws_url, self._get_centrifugo_token)
        await self._realtime.connect(self.user_id)
        self.stats.record_ws_connect()

    async def disconnect_realtime(self) -> None:
        if self._realtime:
            await self._realtime.disconnect()
            self.stats.record_ws_disconnect()
            self._realtime = None

    async def prepare(self, retries: int = 5) -> None:
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
        self._client = httpx.AsyncClient(limits=limits)
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                await self.login()
                await self.connect_realtime()
                self._ready.set()
                return
            except AsyncApiError as exc:
                last_error = exc
                if exc.status_code not in _RETRYABLE_STATUS_CODES or attempt + 1 == retries:
                    raise
            except Exception as exc:
                last_error = exc
                if attempt + 1 == retries:
                    raise
            await asyncio.sleep(min(0.5 * (attempt + 1), 3.0))
        if last_error:
            raise last_error

    async def _resolve_game_id(self, first_result: dict) -> int | None:
        action = first_result.get('action')
        if action == 'active_game_found':
            return first_result.get('data', {}).get('game_id')
        if action == 'game_found':
            if self._realtime:
                event = await self._realtime.wait_user_event('game_found', timeout=10.0)
                if event:
                    return event.get('data', {}).get('game_id')
            retry = await self._request('POST', '/warship/matchmaking/find/', json={'is_training': True})
            if retry.get('action') == 'active_game_found':
                return retry.get('data', {}).get('game_id')
        if action == 'search_started':
            if self._realtime:
                event = await self._realtime.wait_user_event('game_found', timeout=30.0)
                if event:
                    return event.get('data', {}).get('game_id')
            for _ in range(30):
                await asyncio.sleep(1.0)
                retry = await self._request('POST', '/warship/matchmaking/find/', json={'is_training': True})
                if retry.get('action') == 'active_game_found':
                    return retry.get('data', {}).get('game_id')
                if retry.get('action') == 'game_found':
                    follow_up = await self._request('POST', '/warship/matchmaking/find/', json={'is_training': True})
                    if follow_up.get('action') == 'active_game_found':
                        return follow_up.get('data', {}).get('game_id')
        return None

    async def matchmaking(self) -> int | None:
        if self._barrier:
            await self._barrier.wait()
        if self._realtime:
            await self._realtime.drain_user_queue()
        result = await self._request('POST', '/warship/matchmaking/find/', json={'is_training': True})
        game_id = await self._resolve_game_id(result)
        if game_id:
            self.game_id = game_id
            self.stats.record_game_started()
            if self._realtime:
                await self._realtime.subscribe_game(game_id)
        return game_id

    async def place_ships_if_needed(self) -> None:
        if not self.game_id:
            return
        status_resp = await self._request('GET', f'/warship/game/{self.game_id}/status/')
        data = status_resp.get('data', {})
        if data.get('status') != 'waiting_ships':
            return
        p1 = data.get('player1', {})
        p2 = data.get('player2') or {}
        my_info = p1 if p1.get('id') == self.user_id else p2
        if my_info.get('ships_placed'):
            return
        fleet = generate_random_fleet(BOARD_SIZE)
        self._peer_fleet = fleet
        await self._request(
            'POST',
            f'/warship/game/{self.game_id}/place_ships/',
            json={'ships': fleet},
        )

    @staticmethod
    def _pick_random_shot(my_shots: set[tuple[int, int]]) -> tuple[int, int] | None:
        available = [(r, c) for r in range(BOARD_SIZE) for c in range(BOARD_SIZE) if (r, c) not in my_shots]
        if not available:
            return None
        return random.choice(available)

    def _apply_game_event(self, event: dict, state: dict) -> str | None:
        action = event.get('action')
        if action == 'game_finished':
            self.stats.record_game_finished()
            return 'finished'

        data = event.get('data') or {}
        if action in ('game_status', 'game_started', 'shot_result'):
            if data.get('status'):
                state['status'] = data['status']
            if data.get('current_turn'):
                state['current_turn_id'] = data['current_turn'].get('id')
            if action == 'game_started' and data.get('current_turn'):
                state['status'] = 'player1_turn'
        return None

    async def _fetch_game_state(self) -> dict:
        status_resp = await self._request('GET', f'/warship/game/{self.game_id}/status/')
        data = status_resp.get('data', {})
        turn = data.get('current_turn')
        return {
            'status': data.get('status'),
            'current_turn_id': turn.get('id') if turn else None,
        }

    async def _load_my_shots(self, my_shots: set[tuple[int, int]]) -> None:
        if my_shots:
            return
        board = (await self._request('GET', f'/warship/game/{self.game_id}/board/'))['data']
        my_shots.update((shot['row'], shot['col']) for shot in board.get('my_shots', []))

    async def _fire_shot(self, my_shots: set[tuple[int, int]], state: dict) -> str:
        if state.get('status') not in ('player1_turn', 'player2_turn'):
            return 'wait'
        if state.get('current_turn_id') != self.user_id:
            return 'wait'

        await self._load_my_shots(my_shots)
        shot = self._pick_random_shot(my_shots)
        if not shot:
            return 'wait'

        row, col = shot
        response = await self._request(
            'POST',
            f'/warship/game/{self.game_id}/make_shot/',
            json={'row': row, 'col': col},
        )
        result = response.get('data', {})
        my_shots.add((row, col))

        if result.get('game_finished'):
            self.stats.record_game_finished()
            return 'finished'
        if result.get('hit'):
            return 'hit_again'
        return 'wait'

    async def _ensure_peer_battle(self, state: dict) -> PeerBattleState | None:
        if self._peer_battle or not self.game_id or not self.user_id:
            return self._peer_battle
        if not self._peer_fleet:
            return None

        status_resp = await self._request('GET', f'/warship/game/{self.game_id}/status/')
        data = status_resp.get('data', {})
        player1 = data.get('player1') or {}
        player2 = data.get('player2') or {}
        player1_id = player1.get('id')
        player2_id = player2.get('id')
        if not player1_id or not player2_id:
            return None

        current_turn = data.get('current_turn') or {}
        self._peer_battle = PeerBattleState(
            game_id=self.game_id,
            user_id=self.user_id,
            player1_id=player1_id,
            player2_id=player2_id,
            fleet=self._peer_fleet,
        )
        if current_turn.get('id'):
            self._peer_battle.current_turn_id = current_turn['id']
        return self._peer_battle

    async def _publish_peer_finish(self, winner_id: int) -> None:
        if not self._realtime or not self.game_id:
            return
        await self._realtime.publish_finish(
            self.game_id,
            {'action': 'game_finished', 'winner_id': winner_id},
        )

    async def _handle_peer_event(self, event: dict, battle: PeerBattleState) -> str | None:
        action = event.get('action')

        if action == 'game_started':
            current_turn = (event.get('data') or {}).get('current_turn') or {}
            if current_turn.get('id'):
                battle.current_turn_id = current_turn['id']
            return None

        if action == 'shot':
            if event.get('player_id') == self.user_id:
                return None
            shot_result = battle.handle_incoming_shot(event)
            if shot_result and self._realtime:
                await self._realtime.publish_game(shot_result)
                if shot_result.get('game_finished'):
                    await self._publish_peer_finish(int(shot_result['winner_id']))
                    self.stats.record_game_finished()
                    return 'finished'
            return None

        if action == 'shot_result':
            if event.get('shooter_id') != self.user_id:
                return None
            game_over = battle.apply_shot_result(event)
            if game_over:
                await self._publish_peer_finish(self.user_id)
                self.stats.record_game_finished()
                return 'finished'
            return None

        if action == 'game_finished':
            self.stats.record_game_finished()
            return 'finished'

        return None

    async def _play_peer_until_finished(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        state = await self._fetch_game_state()
        watch_actions = {'game_started', 'shot', 'shot_result', 'game_finished'}

        if self._realtime and self.game_id:
            await self._realtime.subscribe_finish(self.game_id)

        while time.monotonic() < deadline:
            if state.get('status') == 'waiting_ships':
                await self.place_ships_if_needed()
                state = await self._fetch_game_state()
                continue

            if state.get('status') == 'cancelled':
                self.stats.record_game_cancelled()
                return

            if state.get('status') == 'finished':
                self.stats.record_game_finished()
                return

            battle = await self._ensure_peer_battle(state)

            if self._realtime:
                pending, matched = await self._realtime.wait_game_event_or_drain(
                    watch_actions,
                    self.poll_interval,
                )
                for event in pending:
                    if battle:
                        result = await self._handle_peer_event(event, battle)
                        if result == 'finished':
                            return
                if matched and battle:
                    result = await self._handle_peer_event(matched, battle)
                    if result == 'finished':
                        return

            if battle and battle.is_my_turn() and self._realtime:
                shot = battle.pick_shot()
                if shot:
                    await self._realtime.publish_game(battle.build_shot_message(shot[0], shot[1]))
                if self.turn_delay > 0:
                    await asyncio.sleep(self.turn_delay)
                continue

            if self.poll_interval > 0:
                await asyncio.sleep(self.poll_interval)
            state = await self._fetch_game_state()

    async def play_until_finished(self, timeout: float) -> None:
        if not self.game_id:
            return

        state = await self._fetch_game_state()
        status_resp = await self._request('GET', f'/warship/game/{self.game_id}/status/')
        play_mode = status_resp.get('data', {}).get('play_mode', 'server')

        if play_mode == 'peer' and self.use_ws:
            await self._play_peer_until_finished(timeout)
            return

        deadline = time.monotonic() + timeout
        my_shots: set[tuple[int, int]] = set()
        watch_actions = {'game_status', 'game_started', 'shot_result', 'game_finished'}

        while time.monotonic() < deadline:
            if state.get('status') == 'waiting_ships':
                await self.place_ships_if_needed()
                state = await self._fetch_game_state()
                continue

            if state.get('status') == 'cancelled':
                self.stats.record_game_cancelled()
                return

            if state.get('status') == 'finished':
                self.stats.record_game_finished()
                return

            outcome = await self._fire_shot(my_shots, state)
            while outcome == 'hit_again':
                if self.turn_delay > 0:
                    await asyncio.sleep(self.turn_delay)
                outcome = await self._fire_shot(my_shots, state)
            if outcome == 'finished':
                return

            if self._realtime:
                pending, matched = await self._realtime.wait_game_event_or_drain(watch_actions, self.poll_interval)
                for event in pending:
                    result = self._apply_game_event(event, state)
                    if result == 'finished':
                        return
                if matched:
                    result = self._apply_game_event(matched, state)
                    if result == 'finished':
                        return
                    if state.get('current_turn_id') == self.user_id:
                        continue
                continue

            state = await self._fetch_game_state()
            if self.poll_interval > 0:
                await asyncio.sleep(self.poll_interval)

    async def cleanup(self) -> None:
        if self.game_id:
            try:
                await self._request('POST', f'/warship/game/{self.game_id}/leave/', json={})
            except AsyncApiError:
                pass
        await self.disconnect_realtime()
        if self._client:
            await self._client.aclose()
            self._client = None
