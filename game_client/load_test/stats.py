import threading
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class MetricPoint:
    timestamp: float
    rps: float
    active_games: int
    http_requests: int
    http_errors: int
    cpu_percent: float
    memory_mb: float
    players_prepared: int
    players_in_game: int
    players_done: int


@dataclass
class StatsCollector:
    started_at: float = field(default_factory=time.monotonic)
    http_requests: int = 0
    http_errors: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    games_started: int = 0
    games_finished: int = 0
    games_cancelled: int = 0
    active_games: int = 0
    ws_connections: int = 0
    ws_disconnects: int = 0
    player_errors: int = 0
    players_prepared: int = 0
    players_in_game: int = 0
    players_done: int = 0
    total_players: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _history: deque = field(default_factory=lambda: deque(maxlen=600), repr=False)
    _last_http_requests: int = 0
    _last_sample_at: float = field(default_factory=time.monotonic, repr=False)

    def record_request(self, latency_ms: float, error: bool = False) -> None:
        with self._lock:
            self.http_requests += 1
            self.latencies_ms.append(latency_ms)
            if error:
                self.http_errors += 1

    def record_game_started(self) -> None:
        with self._lock:
            self.games_started += 1
            self.active_games += 1

    def record_game_finished(self) -> None:
        with self._lock:
            self.games_finished += 1
            self.active_games = max(0, self.active_games - 1)

    def record_game_cancelled(self) -> None:
        with self._lock:
            self.games_cancelled += 1
            self.active_games = max(0, self.active_games - 1)

    def record_ws_connect(self) -> None:
        with self._lock:
            self.ws_connections += 1

    def record_ws_disconnect(self) -> None:
        with self._lock:
            self.ws_disconnects += 1

    def record_player_error(self) -> None:
        with self._lock:
            self.player_errors += 1

    def record_player_prepared(self) -> None:
        with self._lock:
            self.players_prepared += 1

    def record_player_in_game(self) -> None:
        with self._lock:
            self.players_in_game += 1

    def record_player_done(self) -> None:
        with self._lock:
            self.players_in_game = max(0, self.players_in_game - 1)
            self.players_done += 1

    def set_total_players(self, count: int) -> None:
        with self._lock:
            self.total_players = count

    @staticmethod
    def _percentile(values: list[float], pct: float) -> float:
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int(len(sorted_values) * pct / 100)
        index = min(index, len(sorted_values) - 1)
        return sorted_values[index]

    def sample(self, cpu_percent: float = 0.0, memory_mb: float = 0.0) -> MetricPoint:
        now = time.monotonic()
        with self._lock:
            interval = max(now - self._last_sample_at, 0.001)
            delta_requests = self.http_requests - self._last_http_requests
            instant_rps = delta_requests / interval
            point = MetricPoint(
                timestamp=now - self.started_at,
                rps=instant_rps,
                active_games=self.active_games,
                http_requests=self.http_requests,
                http_errors=self.http_errors,
                cpu_percent=cpu_percent,
                memory_mb=memory_mb,
                players_prepared=self.players_prepared,
                players_in_game=self.players_in_game,
                players_done=self.players_done,
            )
            self._history.append(point)
            self._last_http_requests = self.http_requests
            self._last_sample_at = now
            return point

    def get_history(self) -> list[MetricPoint]:
        with self._lock:
            return list(self._history)

    def get_live_metrics(self, cpu_percent: float = 0.0, memory_mb: float = 0.0) -> dict:
        with self._lock:
            elapsed = max(time.monotonic() - self.started_at, 0.001)
            rps = self.http_requests / elapsed
            error_rate = (self.http_errors / self.http_requests * 100) if self.http_requests else 0.0
            latencies = list(self.latencies_ms)
            return {
                'elapsed': elapsed,
                'total_players': self.total_players,
                'players_prepared': self.players_prepared,
                'players_in_game': self.players_in_game,
                'players_done': self.players_done,
                'active_games': self.active_games,
                'games_started': self.games_started,
                'games_finished': self.games_finished,
                'games_cancelled': self.games_cancelled,
                'http_requests': self.http_requests,
                'http_errors': self.http_errors,
                'rps': rps,
                'error_rate': error_rate,
                'latency_p50': self._percentile(latencies, 50),
                'latency_p95': self._percentile(latencies, 95),
                'latency_p99': self._percentile(latencies, 99),
                'ws_connections': self.ws_connections,
                'ws_disconnects': self.ws_disconnects,
                'player_errors': self.player_errors,
                'cpu_percent': cpu_percent,
                'memory_mb': memory_mb,
            }

    def snapshot(self, players: int) -> str:
        metrics = self.get_live_metrics()
        return (
            f'Players: {players} | Active games: {metrics["active_games"]} | '
            f'Started: {metrics["games_started"]} | Finished: {metrics["games_finished"]} | '
            f'Cancelled: {metrics["games_cancelled"]}\n'
            f'HTTP: {metrics["http_requests"]} req, {metrics["rps"]:.0f} req/s, '
            f'errors: {metrics["http_errors"]} ({metrics["error_rate"]:.2f}%)\n'
            f'Latency p50/p95/p99: {metrics["latency_p50"]:.0f}/'
            f'{metrics["latency_p95"]:.0f}/{metrics["latency_p99"]:.0f} ms\n'
            f'WS: {metrics["ws_connections"]} conn, {metrics["ws_disconnects"]} disc | '
            f'Player errors: {metrics["player_errors"]}'
        )
