"""Локальная логика peer-игры (ходы без бэкенда)."""

import copy
import random
from typing import Any


def finish_channel_name(game_id: int) -> str:
    return f'finish:{game_id}'


def apply_shot_to_fleet(ships: list[dict], row: int, col: int) -> dict:
    """Проверяет попадание по флоту (логика ShipPlacement.check_hit)."""
    ships_updated = []
    hit_result = {
        'hit': False,
        'ship_destroyed': False,
        'ship_size': None,
    }

    for ship in ships:
        ship_copy = copy.deepcopy(ship)
        cells = ship_copy.get('cells', [])

        if [row, col] in cells:
            hit_cells = ship_copy.get('hit_cells', [])
            if [row, col] not in hit_cells:
                hit_cells.append([row, col])
                ship_copy['hit_cells'] = hit_cells

            ship_destroyed = len(hit_cells) == len(cells)
            if ship_destroyed:
                ship_copy['destroyed'] = True

            hit_result = {
                'hit': True,
                'ship_destroyed': ship_destroyed,
                'ship_size': ship_copy.get('size'),
            }

        ships_updated.append(ship_copy)

    return {'ships': ships_updated, 'result': hit_result}


def all_ships_destroyed(ships: list[dict]) -> bool:
    if not ships:
        return False
    return all(ship.get('destroyed', False) for ship in ships)


class PeerBattleState:
    """Состояние peer-партии на одном клиенте."""

    def __init__(
        self,
        game_id: int,
        user_id: int,
        player1_id: int,
        player2_id: int,
        fleet: list[dict],
        board_size: int = 10,
    ):
        self.game_id = game_id
        self.user_id = user_id
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.board_size = board_size
        self.my_fleet = copy.deepcopy(fleet)
        self.my_shots: set[tuple[int, int]] = set()
        self.incoming_shots: set[tuple[int, int]] = set()
        self.current_turn_id = player1_id

    def opponent_id(self) -> int:
        return self.player2_id if self.user_id == self.player1_id else self.player1_id

    def is_my_turn(self) -> bool:
        return self.current_turn_id == self.user_id

    def pick_shot(self) -> tuple[int, int] | None:
        available = [
            (row, col)
            for row in range(self.board_size)
            for col in range(self.board_size)
            if (row, col) not in self.my_shots
        ]
        if not available:
            return None
        return random.choice(available)

    def build_shot_message(self, row: int, col: int) -> dict:
        return {
            'action': 'shot',
            'player_id': self.user_id,
            'row': row,
            'col': col,
        }

    def handle_incoming_shot(self, message: dict) -> dict | None:
        """Обрабатывает выстрел противника по нашему полю, возвращает shot_result."""
        shooter_id = message.get('player_id')
        row = message.get('row')
        col = message.get('col')
        if shooter_id is None or row is None or col is None:
            return None
        if shooter_id != self.opponent_id():
            return None

        key = (int(row), int(col))
        if key in self.incoming_shots:
            return None
        self.incoming_shots.add(key)

        applied = apply_shot_to_fleet(self.my_fleet, key[0], key[1])
        self.my_fleet = applied['ships']
        hit_result = applied['result']

        game_finished = all_ships_destroyed(self.my_fleet)
        if game_finished:
            next_turn_id = shooter_id
        elif hit_result['hit']:
            next_turn_id = shooter_id
        else:
            next_turn_id = self.user_id

        self.current_turn_id = next_turn_id

        payload: dict[str, Any] = {
            'action': 'shot_result',
            'shooter_id': shooter_id,
            'row': key[0],
            'col': key[1],
            'hit': hit_result['hit'],
            'ship_destroyed': hit_result['ship_destroyed'],
            'ship_size': hit_result.get('ship_size'),
            'next_turn_id': next_turn_id,
        }
        if game_finished:
            payload['game_finished'] = True
            payload['winner_id'] = shooter_id
        return payload

    def apply_shot_result(self, message: dict) -> bool:
        """Применяет ответ на наш выстрел. Возвращает True если игра завершена."""
        if message.get('shooter_id') != self.user_id:
            return False

        row = message.get('row')
        col = message.get('col')
        if row is None or col is None:
            return False

        self.my_shots.add((int(row), int(col)))
        next_turn_id = message.get('next_turn_id')
        if next_turn_id is not None:
            self.current_turn_id = int(next_turn_id)

        return bool(message.get('game_finished'))

    def build_finish_message(self, winner_id: int) -> dict:
        return {
            'action': 'game_finished',
            'winner_id': winner_id,
        }
