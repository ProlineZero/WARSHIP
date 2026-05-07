# Протокол API и Centrifugo для игры в морской бой

## Подключение

Система работает на гибридной архитектуре: **REST API** для выполнения действий (запросов) и **Centrifugo** для получения асинхронных событий в реальном времени.

### 1. Подключение к Centrifugo
Для получения событий в реальном времени клиент должен подключиться к серверу Centrifugo. Для этого сначала нужно получить токен соединения через наше API.

**Получение токена:**
```http
GET /api/warship/centrifugo/token/
Authorization: Bearer <jwt_token_django>
```

**Ответ:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR..."
}
```

Полученный токен используется для инициализации клиента Centrifugo.

### 2. Подписки на каналы (Centrifugo)
После успешного подключения к Centrifugo, клиент должен подписаться на соответствующие каналы:

1. **Персональный канал пользователя:** `user_<user_id>` (для событий матчмейкинга).
2. **Канал игры:** `game_<game_id>` (после того как игра найдена, для событий конкретной игры).

---

## Выполнение действий (через HTTP REST API)

Все действия в игре инициируются клиентом через обычные HTTP-запросы.
Каждый запрос требует стандартной авторизации: `Authorization: Bearer <jwt_token_django>`.

### 1. Размещение кораблей
**Запрос:**
```http
POST /api/warship/game/<game_id>/place_ships/
Content-Type: application/json

{
  "ships": [
    {"size": 4, "cells": [[0, 0], [0, 1], [0, 2], [0, 3]]},
    {"size": 3, "cells": [[2, 0], [2, 1], [2, 2]]},
    // ...
  ]
}
```
*Правила валидации кораблей остались прежними: 1х4, 2х3, 3х2, 4х1. Без соприкосновений.*

**Ответ при успехе (HTTP 200):**
```json
{
  "action": "place_ships",
  "status": "success",
  "message": "Корабли успешно размещены"
}
```

При ошибке (например, корабли соприкасаются) сервер вернет HTTP 400 и JSON с описанием ошибки.

### 2. Выполнение выстрела
**Запрос:**
```http
POST /api/warship/game/<game_id>/make_shot/
Content-Type: application/json

{
  "row": 5,
  "col": 3
}
```

**Ответ при успехе (HTTP 200):**
```json
{
  "action": "make_shot",
  "status": "success",
  "data": {
    "success": true,
    "hit": true,
    "ship_destroyed": false,
    "ship_size": 3,
    "game_finished": false,
    "winner": null,
    "move_id": 42
  }
}
```

### 3. Получение статуса игры
**Запрос:**
```http
GET /api/warship/game/<game_id>/status/
```

**Ответ (HTTP 200):**
```json
{
  "action": "game_status",
  "status": "success",
  "data": {
    "game_id": 1,
    "status": "player1_turn",
    "player1": { "id": 1, "username": "player1", "ships_placed": true },
    "player2": { "id": 2, "username": "player2", "ships_placed": true },
    "current_turn": { "id": 1, "username": "player1" },
    "winner": null,
    "board_size": 10,
    "started_at": "2026-01-28T12:00:00Z",
    "finished_at": null,
    "moves": [ ... ]
  }
}
```

### 4. Получение состояния доски
**Запрос:**
```http
GET /api/warship/game/<game_id>/board/
```

**Ответ (HTTP 200):** Возвращает ваши корабли, ваши выстрелы и выстрелы противника по вашему полю.

---

## События в реальном времени (через Centrifugo)

При совершении действий в игре (вами или противником), бэкенд публикует события в канал `game_<game_id>`.

### 1. Обновление статуса игры (`game_status`)
Приходит при размещении кораблей или выстрелах.
```json
{
  "action": "game_status",
  "status": "success",
  "data": { ...объект статуса игры... }
}
```

### 2. Игра началась (`game_started`)
Приходит, когда оба игрока разместили корабли.
```json
{
  "action": "game_started",
  "status": "success",
  "data": {
    "game_id": 1,
    "current_turn": { "id": 1, "username": "player1" },
    "started_at": "2026-01-28T12:00:00Z"
  }
}
```

### 3. Результат выстрела (`shot_result`)
Приходит сразу после того, как любой из игроков выстрелил.
```json
{
  "action": "shot_result",
  "status": "success",
  "data": {
    "hit": true,
    "ship_destroyed": false,
    ...
  }
}
```

### 4. Завершение игры (`game_finished`)
Приходит, когда все корабли одного из игроков уничтожены.
```json
{
  "action": "game_finished",
  "status": "success",
  "data": {
    "game_id": 1,
    "winner": { "id": 1, "username": "player1" },
    "finished_at": "2026-01-28T12:30:00Z"
  }
}
```