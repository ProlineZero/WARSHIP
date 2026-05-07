# Matchmaking - Поиск противника (REST + Centrifugo)

## Описание

Система автоматического подбора противников для игры в морской бой. 
Работает на базе HTTP API для отправки запросов и Centrifugo для получения асинхронных уведомлений.

## Как начать поиск игры

Для получения событий поиска клиент **обязательно** должен быть подключен к Centrifugo и подписан на свой персональный канал `user_<user_id>`.

### 1. Запрос на поиск игры
Запрашивает поиск противника. Если у пользователя уже есть активная (незавершенная) игра, бэкенд сразу вернет её. Иначе - добавит пользователя в очередь (кэш).

**Запрос:**
```http
POST /api/warship/matchmaking/find/
Authorization: Bearer <jwt_token_django>
```

**Ответ при наличии активной игры (HTTP 200):**
```json
{
  "action": "active_game_found",
  "status": "success",
  "data": {
    "game_id": 24,
    "status": "player1_turn",
    "opponent": { "id": 2, "username": "player2" },
    "player1": { "id": 1, "username": "player1" },
    "player2": { "id": 2, "username": "player2" },
    "current_turn": { "id": 1, "username": "player1" }
  }
}
```

**Ответ, когда игрок добавлен в очередь (поиск начат) (HTTP 200):**
```json
{
  "action": "search_started",
  "status": "success",
  "message": "Поиск противника начат"
}
```
*В этот момент запрос завершается. Дальнейшее ожидание происходит асинхронно через прослушивание Centrifugo.*

**Ответ, если противник сразу найден (в очереди уже кто-то был) (HTTP 200):**
```json
{
  "action": "game_found",
  "status": "success",
  "message": "Противник найден"
}
```

### 2. Событие: Игра найдена (через Centrifugo)

Если вы получили `search_started`, вы просто ждете. Как только другой игрок выполнит `/api/warship/matchmaking/find/` и алгоритм подберет вас друг другу, вам обоим прилетит событие в канал `user_<user_id>`:

```json
{
  "action": "game_found",
  "status": "success",
  "data": {
    "game_id": 42,
    "opponent": { "id": 2, "username": "player2" },
    "player1": { "id": 1, "username": "player1" },
    "player2": { "id": 2, "username": "player2" }
  }
}
```
Увидев это событие, фронтенд переходит на экран игры и подписывается на канал `game_<game_id>`.

### 3. Отмена поиска
Отменяет поиск игры и удаляет игрока из очереди (из кэша).

**Запрос:**
```http
POST /api/warship/matchmaking/cancel/
Authorization: Bearer <jwt_token_django>
```

**Ответ (HTTP 200):**
```json
{
  "action": "search_cancelled",
  "status": "success",
  "message": "Поиск игры отменен"
}
```

## Алгоритм подбора противника
Подбор происходит по следующим критериям:
1. Процент побед (win rate)
2. Количество сыгранных игр

Все ожидающие игроки находятся в Redis (через `django.core.cache`). Когда новый игрок вызывает `/find/`, бэкенд ищет ему подходящую пару в кэше. Если находит — создает игру и публикует событие в Centrifugo обоим игрокам. Если нет — помещает нового игрока в кэш ждать.