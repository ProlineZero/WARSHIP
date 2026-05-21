import random
from typing import List, Dict, Tuple

REQUIRED_SHIPS = [(4, 1), (3, 2), (2, 3), (1, 4)]


def _neighbors_touch(cells: set, row: int, col: int) -> bool:
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            if (row + dr, col + dc) in cells:
                return True
    return False


def _can_place(cells: set, size: int, row: int, col: int, horizontal: bool, board_size: int) -> List[Tuple[int, int]] | None:
    coords = []
    for i in range(size):
        r = row if horizontal else row + i
        c = col + i if horizontal else col
        if not (0 <= r < board_size and 0 <= c < board_size):
            return None
        if _neighbors_touch(cells, r, c):
            return None
        coords.append((r, c))
    return coords


def generate_random_fleet(board_size: int = 10, max_attempts: int = 500) -> List[Dict]:
    for _ in range(max_attempts):
        occupied: set = set()
        ships: List[Dict] = []
        ok = True
        for size, count in REQUIRED_SHIPS:
            for _ in range(count):
                placed = False
                for _ in range(200):
                    horizontal = random.choice([True, False])
                    row = random.randint(0, board_size - 1)
                    col = random.randint(0, board_size - 1)
                    coords = _can_place(occupied, size, row, col, horizontal, board_size)
                    if coords:
                        for r, c in coords:
                            occupied.add((r, c))
                        ships.append({
                            'size': size,
                            'cells': [[r, c] for r, c in coords],
                        })
                        placed = True
                        break
                if not placed:
                    ok = False
                    break
            if not ok:
                break
        if ok and len(ships) == sum(c for _, c in REQUIRED_SHIPS):
            return ships
    raise RuntimeError('Не удалось сгенерировать флот')
