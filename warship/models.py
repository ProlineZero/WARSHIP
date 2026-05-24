from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings


class ShipPlacementError(ValidationError):
    """
    Исключение для ошибок размещения кораблей с координатами проблемных клеток.
    
    Attributes:
        message: Сообщение об ошибке
        error_cells: Список координат проблемных клеток [[row, col], ...]
        error_type: Тип ошибки ('out_of_bounds', 'intersection', 'touching', 'invalid_shape', 'wrong_count')
    """
    
    def __init__(self, message, error_cells=None, error_type=None):
        super().__init__(message)
        self.error_cells = error_cells or []
        self.error_type = error_type


class GameSession(models.Model):
    """
    Сессия игры в морской бой.
    Хранит информацию о двух игроках, статусе игры и времени.
    """
    
    class GameStatus(models.TextChoices):
        WAITING_CHALLENGE = 'waiting_challenge', 'Ожидание вызова'
        WAITING_SHIPS = 'waiting_ships', 'Ожидание размещения кораблей'
        PLAYER1_TURN = 'player1_turn', 'Ход первого игрока'
        PLAYER2_TURN = 'player2_turn', 'Ход второго игрока'
        FINISHED = 'finished', 'Игра завершена'
        CANCELLED = 'cancelled', 'Игра отменена'
    
    player1 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='game_sessions_as_player1',
        verbose_name='Первый игрок'
    )
    player2 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='game_sessions_as_player2',
        verbose_name='Второй игрок',
        null=True,
        blank=True
    )
    
    is_training = models.BooleanField(
        default=False,
        verbose_name='Тренировка'
    )

    status = models.CharField(
        max_length=20,
        choices=GameStatus.choices,
        default=GameStatus.WAITING_SHIPS,
        verbose_name='Статус игры'
    )
    
    current_turn = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='current_turn_sessions',
        null=True,
        blank=True,
        verbose_name='Текущий ход'
    )
    
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='won_games',
        null=True,
        blank=True,
        verbose_name='Победитель'
    )
    
    board_size = models.IntegerField(
        default=10,
        verbose_name='Размер поля',
        help_text='Размер игрового поля (по умолчанию 10x10)'
    )
    
    started_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Время начала'
    )
    
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Время окончания'
    )

    player1_bot = models.ForeignKey(
        'core.UserBot',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='games_as_player1_bot',
        verbose_name='Бот первого игрока',
    )
    player2_bot = models.ForeignKey(
        'core.UserBot',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='games_as_player2_bot',
        verbose_name='Бот второго игрока',
    )

    class AdminControlMode(models.TextChoices):
        NORMAL = 'normal', 'Обычный'
        DELAYED = 'delayed', 'С задержкой'
        MANUAL_STEP = 'manual_step', 'Ручной шаг'

    admin_control_mode = models.CharField(
        max_length=20,
        choices=AdminControlMode.choices,
        default=AdminControlMode.NORMAL,
        verbose_name='Режим контроля админом',
    )
    move_delay_ms = models.PositiveIntegerField(default=0, verbose_name='Задержка хода (мс)')
    is_paused = models.BooleanField(default=False, verbose_name='Пауза')
    pending_move = models.JSONField(null=True, blank=True, verbose_name='Ожидающий ход')
    last_move_at = models.DateTimeField(null=True, blank=True, verbose_name='Время последнего хода')
    
    class Meta:
        verbose_name = 'Сессия игры'
        verbose_name_plural = 'Сессии игр'
        ordering = ['-started_at']
    
    def __str__(self):
        return f'Игра #{self.id}: {self.player1.username} vs {self.player2.username if self.player2 else "ожидание"}'
    
    def start_game(self):
        """Начинает игру после размещения кораблей обоими игроками."""
        if self.status != self.GameStatus.WAITING_SHIPS:
            raise ValidationError('Игра уже начата или завершена')
        
        player1_placement = self.ship_placements.filter(player=self.player1).first()
        player2_placement = self.ship_placements.filter(player=self.player2).first()
        
        if not player1_placement or not player1_placement.ships_placed:
            raise ValidationError('Первый игрок еще не разместил корабли')
        
        if not player2_placement or not player2_placement.ships_placed:
            raise ValidationError('Второй игрок еще не разместил корабли')
        
        self.status = self.GameStatus.PLAYER1_TURN
        self.current_turn = self.player1
        self.save()
    
    def finish_game(self, winner):
        """Завершает игру и устанавливает победителя."""

        from warship.utils import get_bot_stats, get_player_stats

        if self.status == self.GameStatus.FINISHED:
            raise ValidationError('Игра уже завершена')

        if winner not in [self.player1, self.player2]:
            raise ValidationError('Победитель должен быть одним из игроков')

        self.status = self.GameStatus.FINISHED
        self.winner = winner
        self.current_turn = None
        self.pending_move = None
        self.finished_at = timezone.now()

        if not self.is_training:
            self.player1.metadata['stats'] = get_player_stats(self.player1)
            self.player1.save(update_fields=['metadata'])
            if self.player2_id:
                self.player2.metadata['stats'] = get_player_stats(self.player2)
                self.player2.save(update_fields=['metadata'])

            from core.models.user_bot import UserBot

            if self.player1_bot_id:
                bot = UserBot.objects.get(pk=self.player1_bot_id)
                bot.metadata['stats'] = get_bot_stats(bot)
                bot.save(update_fields=['metadata'])
            if self.player2_bot_id:
                bot = UserBot.objects.get(pk=self.player2_bot_id)
                bot.metadata['stats'] = get_bot_stats(bot)
                bot.save(update_fields=['metadata'])

        self.save()
    
    def cancel_game(self):
        """Отменяет игру (когда оба игрока отключились)."""
        if self.status == self.GameStatus.FINISHED:
            raise ValidationError('Игра уже завершена')
        
        if self.status == self.GameStatus.CANCELLED:
            return  # Уже отменена
        
        self.status = self.GameStatus.CANCELLED
        self.current_turn = None
        self.finished_at = timezone.now()
        self.save()
    
    def switch_turn(self):
        """Переключает ход между игроками."""
        if self.current_turn == self.player1:
            self.current_turn = self.player2
            self.status = self.GameStatus.PLAYER2_TURN
        else:
            self.current_turn = self.player1
            self.status = self.GameStatus.PLAYER1_TURN
        self.save()
    
    def get_opponent(self, player):
        """Возвращает противника для указанного игрока."""
        if player == self.player1:
            return self.player2
        elif player == self.player2:
            return self.player1
        else:
            raise ValidationError('Игрок не участвует в этой игре')


class ShipPlacement(models.Model):
    """
    Размещение кораблей игрока на поле.
    Хранит позиции всех кораблей в формате JSON.
    """
    
    game_session = models.ForeignKey(
        GameSession,
        on_delete=models.CASCADE,
        related_name='ship_placements',
        verbose_name='Сессия игры'
    )
    
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ship_placements',
        verbose_name='Игрок'
    )
    
    ships = models.JSONField(
        default=list,
        verbose_name='Корабли',
        help_text='Список кораблей в формате [{"size": 4, "cells": [[0,0], [0,1], ...], "destroyed": false}, ...]'
    )
    
    ships_placed = models.BooleanField(
        default=False,
        verbose_name='Корабли размещены'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Время создания'
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Время обновления'
    )
    
    class Meta:
        verbose_name = 'Размещение кораблей'
        verbose_name_plural = 'Размещения кораблей'
        unique_together = ['game_session', 'player']
    
    def __str__(self):
        return f'Размещение кораблей игрока {self.player.username} в игре #{self.game_session.id}'
    
    def validate_ship_placement(self, ships_data: list):
        """
        Валидирует размещение кораблей.
        
        Правила классического морского боя:
        - 1 корабль на 4 клетки
        - 2 корабля на 3 клетки
        - 3 корабля на 2 клетки
        - 4 корабля на 1 клетку
        
        Корабли не должны:
        - Выходить за границы поля
        - Пересекаться
        - Соприкасаться (включая диагонали)
        """
        board_size = self.game_session.board_size
        
        # Стандартная конфигурация кораблей
        required_ships = {4: 1, 3: 2, 2: 3, 1: 4}
        
        # Проверяем количество кораблей каждого размера
        ship_counts = {}
        for ship in ships_data:
            size = ship.get('size')
            if size not in ship_counts:
                ship_counts[size] = 0
            ship_counts[size] += 1
        
        for size, count in required_ships.items():
            if ship_counts.get(size, 0) != count:
                raise ValidationError(
                    f'Неверное количество кораблей размера {size}. '
                    f'Требуется: {count}, получено: {ship_counts.get(size, 0)}'
                )
        
        # Проверяем каждый корабль
        all_cells = set()
        for ship in ships_data:
            cells = ship.get('cells', [])
            size = ship.get('size')
            
            if not cells:
                raise ValidationError('Корабль должен содержать координаты клеток')
            
            if len(cells) != size:
                raise ValidationError(
                    f'Корабль размера {size} должен занимать {size} клеток, '
                    f'получено {len(cells)}'
                )
            
            # Проверяем границы поля
            out_of_bounds_cells = []
            for row, col in cells:
                if not (0 <= row < board_size and 0 <= col < board_size):
                    out_of_bounds_cells.append([row, col])
            
            if out_of_bounds_cells:
                raise ShipPlacementError(
                    f'Клетки выходят за границы поля размером {board_size}x{board_size}',
                    error_cells=out_of_bounds_cells,
                    error_type='out_of_bounds'
                )
            
            # Проверяем, что клетки корабля идут подряд (горизонтально или вертикально)
            cells_sorted = sorted(cells)
            is_horizontal = all(
                cells_sorted[i][0] == cells_sorted[0][0] 
                and cells_sorted[i][1] == cells_sorted[i-1][1] + 1
                for i in range(1, len(cells_sorted))
            )
            is_vertical = all(
                cells_sorted[i][1] == cells_sorted[0][1]
                and cells_sorted[i][0] == cells_sorted[i-1][0] + 1
                for i in range(1, len(cells_sorted))
            )
            
            if not (is_horizontal or is_vertical):
                raise ShipPlacementError(
                    f'Корабль должен быть размещен горизонтально или вертикально',
                    error_cells=cells,
                    error_type='invalid_shape'
                )
            
            # Проверяем пересечения
            ship_cells = set(tuple(cell) for cell in cells)
            intersection = all_cells & ship_cells
            if intersection:
                # Преобразуем обратно в список списков
                intersection_cells = [[row, col] for row, col in intersection]
                raise ShipPlacementError(
                    f'Корабли пересекаются',
                    error_cells=intersection_cells,
                    error_type='intersection'
                )
            all_cells.update(ship_cells)
        
        # Проверяем соприкосновение кораблей (включая диагонали)
        touching_cells = []
        for i, ship1 in enumerate(ships_data):
            cells1 = set(tuple(cell) for cell in ship1.get('cells', []))
            for ship2 in ships_data[i+1:]:
                cells2 = set(tuple(cell) for cell in ship2.get('cells', []))
                
                # Проверяем соседние клетки (включая диагонали)
                for row1, col1 in cells1:
                    for row2, col2 in cells2:
                        # Проверяем расстояние между клетками (не должны быть соседними)
                        if abs(row1 - row2) <= 1 and abs(col1 - col2) <= 1:
                            # Добавляем обе проблемные клетки
                            if [row1, col1] not in touching_cells:
                                touching_cells.append([row1, col1])
                            if [row2, col2] not in touching_cells:
                                touching_cells.append([row2, col2])
        
        if touching_cells:
            raise ShipPlacementError(
                f'Корабли не должны соприкасаться',
                error_cells=touching_cells,
                error_type='touching'
            )
    
    def set_ships(self, ships_data: list):
        """
        Устанавливает размещение кораблей с валидацией.
        
        Args:
            ships_data: Список словарей вида [
                {"size": 4, "cells": [[0,0], [0,1], [0,2], [0,3]]},
                ...
            ]
        """
        self.validate_ship_placement(ships_data)
        
        # Добавляем поле destroyed для каждого корабля
        ships_with_status = []
        for ship in ships_data:
            ship_copy = ship.copy()
            ship_copy['destroyed'] = False
            ships_with_status.append(ship_copy)
        
        self.ships = ships_with_status
        self.ships_placed = True
        self.save()
    
    def check_hit(self, row: int, col: int) -> dict:
        """
        Проверяет попадание в корабль по координатам.
        
        Returns:
            dict с ключами:
            - hit: bool - попал ли
            - ship_destroyed: bool - уничтожен ли корабль
            - ship_size: int - размер корабля (если попал)
        """
        ships_updated = []
        hit_result = {
            'hit': False,
            'ship_destroyed': False,
            'ship_size': None
        }
        
        for ship in self.ships:
            ship_copy = ship.copy()
            cells = ship_copy.get('cells', [])
            
            if [row, col] in cells:
                # Помечаем клетку как подбитую
                hit_cells = ship_copy.get('hit_cells', [])
                if [row, col] not in hit_cells:
                    hit_cells.append([row, col])
                    ship_copy['hit_cells'] = hit_cells
                
                # Проверяем, уничтожен ли корабль
                ship_destroyed = len(hit_cells) == len(cells)
                if ship_destroyed:
                    ship_copy['destroyed'] = True
                
                hit_result = {
                    'hit': True,
                    'ship_destroyed': ship_destroyed,
                    'ship_size': ship_copy.get('size')
                }
            
            ships_updated.append(ship_copy)
        
        # Сохраняем обновленные данные только если было попадание
        if hit_result['hit']:
            self.ships = ships_updated
            self.save(update_fields=['ships'])
        
        return hit_result
    
    def all_ships_destroyed(self) -> bool:
        """Проверяет, уничтожены ли все корабли."""
        return all(ship.get('destroyed', False) for ship in self.ships)


class GameMove(models.Model):
    """
    Ход игры - выстрел игрока по координатам противника.
    """
    
    game_session = models.ForeignKey(
        GameSession,
        on_delete=models.CASCADE,
        related_name='moves',
        verbose_name='Сессия игры'
    )
    
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='game_moves',
        verbose_name='Игрок'
    )
    
    row = models.IntegerField(
        verbose_name='Строка'
    )
    
    col = models.IntegerField(
        verbose_name='Столбец'
    )
    
    hit = models.BooleanField(
        verbose_name='Попадание'
    )
    
    ship_destroyed = models.BooleanField(
        default=False,
        verbose_name='Корабль уничтожен'
    )
    
    ship_size = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Размер корабля'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Время хода'
    )
    
    class Meta:
        verbose_name = 'Ход игры'
        verbose_name_plural = 'Ходы игр'
        ordering = ['created_at']
        unique_together = ['game_session', 'player', 'row', 'col']
    
    def __str__(self):
        result = 'Попал' if self.hit else 'Мимо'
        return f'Ход игрока {self.player.username}: ({self.row}, {self.col}) - {result}'
    
    def clean(self):
        """Валидация хода перед сохранением."""
        # Проверяем границы поля
        board_size = self.game_session.board_size
        if not (0 <= self.row < board_size and 0 <= self.col < board_size):
            raise ValidationError(
                f'Координаты ({self.row}, {self.col}) выходят за границы поля '
                f'размером {board_size}x{board_size}'
            )
        
        # Проверяем, что игрок не стреляет по своим координатам
        # (это проверяется на уровне бизнес-логики, но можно добавить и здесь)
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# Вспомогательные функции для работы с игрой

def validate_shot(game_session: GameSession, player, row: int, col: int) -> dict:
    """
    Валидирует выстрел игрока.
    
    Args:
        game_session: Сессия игры
        player: Игрок, делающий выстрел
        row: Строка выстрела
        col: Столбец выстрела
    
    Returns:
        dict с результатами валидации:
        - valid: bool - валиден ли выстрел
        - error: str - сообщение об ошибке (если есть)
        - already_shot: bool - был ли уже выстрел по этим координатам
    """
    board_size = game_session.board_size
    
    # Проверка границ поля
    if not (0 <= row < board_size and 0 <= col < board_size):
        return {
            'valid': False,
            'error': f'Координаты ({row}, {col}) выходят за границы поля',
            'already_shot': False
        }
    
    # Проверка на повторный выстрел
    existing_move = GameMove.objects.filter(
        game_session=game_session,
        player=player,
        row=row,
        col=col
    ).exists()
    
    if existing_move:
        return {
            'valid': False,
            'error': 'Вы уже стреляли по этим координатам',
            'already_shot': True
        }
    
    return {
        'valid': True,
        'error': None,
        'already_shot': False
    }


def make_shot(game_session: GameSession, player, row: int, col: int, *, skip_control_gates: bool = False) -> dict:
    """
    Выполняет выстрел игрока.
    """
    validation = validate_shot(game_session, player, row, col)
    if not validation['valid']:
        return {
            'success': False,
            'error': validation['error'],
            'hit': False,
            'ship_destroyed': False,
            'ship_size': None,
            'game_finished': False,
            'winner': None,
            'awaiting_approval': False,
        }

    if game_session.current_turn != player:
        return {
            'success': False,
            'error': 'Сейчас не ваш ход',
            'hit': False,
            'ship_destroyed': False,
            'ship_size': None,
            'game_finished': False,
            'winner': None,
            'awaiting_approval': False,
        }

    if not skip_control_gates:
        if game_session.is_paused:
            return {
                'success': False,
                'error': 'Игра на паузе',
                'hit': False,
                'ship_destroyed': False,
                'ship_size': None,
                'game_finished': False,
                'winner': None,
                'awaiting_approval': False,
                'paused': True,
            }

        if game_session.admin_control_mode == GameSession.AdminControlMode.MANUAL_STEP:
            return {
                'success': False,
                'error': 'Ход ожидает подтверждения администратора',
                'hit': False,
                'ship_destroyed': False,
                'ship_size': None,
                'game_finished': False,
                'winner': None,
                'awaiting_approval': True,
            }

        if game_session.admin_control_mode == GameSession.AdminControlMode.DELAYED and game_session.move_delay_ms:
            if game_session.last_move_at:
                elapsed_ms = (timezone.now() - game_session.last_move_at).total_seconds() * 1000
                if elapsed_ms < game_session.move_delay_ms:
                    return {
                        'success': False,
                        'error': 'Слишком рано для следующего хода',
                        'hit': False,
                        'ship_destroyed': False,
                        'ship_size': None,
                        'game_finished': False,
                        'winner': None,
                        'awaiting_approval': False,
                        'retry_after_ms': int(game_session.move_delay_ms - elapsed_ms),
                    }

    opponent = game_session.get_opponent(player)
    opponent_placement = ShipPlacement.objects.filter(
        game_session=game_session,
        player=opponent
    ).first()

    if not opponent_placement:
        return {
            'success': False,
            'error': 'Противник еще не разместил корабли',
            'hit': False,
            'ship_destroyed': False,
            'ship_size': None,
            'game_finished': False,
            'winner': None,
            'awaiting_approval': False,
        }

    hit_result = opponent_placement.check_hit(row, col)

    GameMove.objects.create(
        game_session=game_session,
        player=player,
        row=row,
        col=col,
        hit=hit_result['hit'],
        ship_destroyed=hit_result['ship_destroyed'],
        ship_size=hit_result.get('ship_size'),
    )

    game_finished = False
    winner = None

    if opponent_placement.all_ships_destroyed():
        game_session.finish_game(player)
        game_finished = True
        winner = player
    elif not hit_result['hit']:
        game_session.switch_turn()

    game_session.last_move_at = timezone.now()
    game_session.pending_move = None
    game_session.save(update_fields=['last_move_at', 'pending_move'])

    return {
        'success': True,
        'error': None,
        'hit': hit_result['hit'],
        'ship_destroyed': hit_result['ship_destroyed'],
        'ship_size': hit_result.get('ship_size'),
        'game_finished': game_finished,
        'winner': winner,
        'awaiting_approval': False,
        'row': row,
        'col': col,
    }
