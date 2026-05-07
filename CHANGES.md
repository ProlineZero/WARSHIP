# Изменения в проекте WARSHIP

## Дата: 2026-01-30


---

### 2. Добавлена автоматическая отмена игры при отключении всех игроков

**Файл: `warship/consumers.py`**

#### Изменения:
- Добавлен глобальный словарь `game_connections` для отслеживания подключений к играм
- При подключении пользователь добавляется в множество подключенных пользователей игры
- При отключении пользователь удаляется из множества
- Если никого не осталось подключенным - игра автоматически отменяется
- Добавлен метод `cancel_game_if_no_connections()` для отмены игры через БД

#### Код:
```python
# Глобальный словарь для отслеживания подключений к играм
game_connections = {}

# В методе connect:
if self.game_session_id not in game_connections:
    game_connections[self.game_session_id] = set()
game_connections[self.game_session_id].add(self.user.id)

# В методе disconnect:
if game_id in game_connections:
    game_connections[game_id].discard(user_id)
    remaining_connections = len(game_connections[game_id])
    
    if remaining_connections == 0:
        await self.cancel_game_if_no_connections(game_id)
        del game_connections[game_id]
```

**Файл: `warship/models.py`**

#### Изменения:
- Добавлен метод `cancel_game()` в модель `GameSession` для отмены игры
- Устанавливает статус `CANCELLED` и время завершения

#### Код:
```python
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
```

---

### 3. Добавлена проверка активных игр в matchmaking

**Файл: `warship/matchmaking_consumer.py`**

#### Изменения:
- В методе `handle_find_game()` добавлена проверка наличия активных игр у пользователя перед поиском новой
- Добавлен метод `get_active_game_data()` для получения данных последней активной игры
- Если найдена активная игра, возвращается событие `active_game_found` вместо начала нового поиска

#### Код:
```python
async def handle_find_game(self, data):
    # Проверяем наличие активных игр у пользователя
    active_game_data = await self.get_active_game_data()
    
    if active_game_data:
        await self.send_json({
            'action': 'active_game_found',
            'status': 'success',
            'data': active_game_data
        })
        return
    
    # ... продолжение поиска новой игры

@database_sync_to_async
def get_active_game_data(self):
    """Получает данные последней активной игры пользователя."""
    active_game = GameSession.objects.select_related(
        'player1', 'player2', 'current_turn'
    ).filter(
        Q(player1=self.user) | Q(player2=self.user)
    ).exclude(
        status__in=[
            GameSession.GameStatus.FINISHED,
            GameSession.GameStatus.CANCELLED
        ]
    ).order_by('-started_at').first()
    
    if not active_game:
        return None
    
    # Формируем данные игры в синхронном контексте
    # ...
```

#### Исправление:
- Исправлена ошибка "You cannot call this from an async context"
- Использован `select_related` для предзагрузки связанных объектов
- Все обращения к полям модели выполняются внутри синхронного метода

---

### 4. Добавлены автоматические уведомления о смене статуса игры

**Файл: `warship/consumers.py`**

#### Изменения:
- Добавлен метод `broadcast_game_started()` - отправляет уведомление о начале игры
- Добавлен метод `broadcast_game_finished()` - отправляет уведомление о завершении игры
- Добавлены обработчики `game_started_message()` и `game_finished_message()`
- Метод `check_and_start_game()` теперь возвращает `True`, если игра была успешно начата

#### Новые события:
1. **`game_started`** - отправляется когда оба игрока разместили корабли
   ```json
   {
     "action": "game_started",
     "status": "success",
     "data": {
       "game_id": 123,
       "current_turn": {
         "id": 1,
         "username": "player1"
       },
       "started_at": "2026-01-29T10:00:00Z"
     }
   }
   ```

2. **`game_finished`** - отправляется когда игра завершена
   ```json
   {
     "action": "game_finished",
     "status": "success",
     "data": {
       "game_id": 123,
       "winner": {
         "id": 2,
         "username": "player2"
       },
       "finished_at": "2026-01-29T10:30:00Z"
     }
   }
   ```

#### Исправление:
- Исправлена проблема с определением победителя: `result.get('winner_id')` → `result.get('winner')` (объект User)

---

### 5. Обновлена документация

**Файл: `warship/PROTOCOL.md`**

#### Добавлено:
- Описание нового action `game_started`
- Описание нового action `game_finished`
- Информация о том, как клиенты определяют чей ход (через поле `current_turn`)
- Обновлен раздел о matchmaking с описанием `active_game_found`
- Добавлена информация об автоматической отмене игры

**Файл: `warship/MATCHMAKING.md`**

#### Добавлено:
- Описание нового action `active_game_found`
- Обновлен пример кода с обработкой `active_game_found`
- Добавлена информация о проверке активных игр перед поиском новой
- Добавлена информация об автоматической отмене игры

---

### 6. Добавлена документация в docstring класса GameConsumer

**Файл: `warship/consumers.py`**

#### Добавлено:
- Описание автоматических уведомлений о смене статуса
- Подробное описание того, как клиенты должны определять чей ход
- Примеры использования поля `current_turn`

---

## Итоговые изменения по файлам:

### `warship/consumers.py`
- Добавлено подробное логирование во все методы
- Добавлен глобальный словарь `game_connections` для отслеживания подключений
- Добавлены методы `broadcast_game_started()` и `broadcast_game_finished()`
- Добавлены обработчики `game_started_message()` и `game_finished_message()`
- Добавлен метод `cancel_game_if_no_connections()`
- Исправлена проблема с определением победителя в `handle_make_shot()`
- Обновлен метод `check_and_start_game()` для возврата булева значения
- Обновлен метод `get_game_status_data()` с улучшенным логированием

### `warship/models.py`
- Добавлен метод `cancel_game()` в модель `GameSession`

### `warship/matchmaking_consumer.py`
- Добавлена проверка активных игр в `handle_find_game()`
- Добавлен метод `get_active_game_data()` с использованием `select_related`
- Добавлен импорт `Q` из `django.db.models`
- Исправлена ошибка с async контекстом

### `warship/PROTOCOL.md`
- Добавлено описание action `game_started`
- Добавлено описание action `game_finished`
- Добавлено описание action `active_game_found` в разделе matchmaking
- Добавлена информация о том, как определять чей ход
- Обновлены примечания

### `warship/MATCHMAKING.md`
- Добавлено описание action `active_game_found`
- Обновлен пример кода
- Обновлены примечания

---

## Новые WebSocket события для клиентов:

1. **`active_game_found`** (matchmaking) - когда найдена активная игра пользователя
2. **`game_started`** (game) - когда игра началась (оба игрока разместили корабли)
3. **`game_finished`** (game) - когда игра завершена (один из игроков победил)

---

## Важные замечания:

1. **Отслеживание подключений**: Используется глобальный словарь в памяти. В продакшене рекомендуется использовать Redis через channel layers для распределенных систем.

2. **Определение текущего хода**: Клиенты должны проверять поле `current_turn` в ответах `game_status` и `game_started`. Если `current_turn.id` совпадает с ID пользователя - это его ход.

3. **Автоматическая отмена**: Если оба игрока отключились от игрового WebSocket, игра автоматически отменяется (статус меняется на `cancelled`).

4. **Проверка активных игр**: При запросе `find_game` система сначала проверяет наличие активных игр. Если найдена активная игра, возвращается `active_game_found` вместо начала нового поиска.
