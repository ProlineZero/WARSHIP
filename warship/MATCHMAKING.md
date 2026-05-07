# Matchmaking - Поиск противника

## Описание

Система автоматического подбора противников для игры в морской бой. Подбор происходит на основе статистики игроков:
- Процент побед (win rate)
- Количество сыгранных игр

## WebSocket подключение

**Через query параметр (для обратной совместимости):**
```
ws://host/ws/matchmaking/?token=<jwt_token>
```

**Через заголовок Authorization (предпочтительно):**
```
ws://host/ws/matchmaking/
```
с заголовком: `Authorization: Bearer <jwt_token>`

**Примечание:** Middleware сначала проверяет заголовок `Authorization`, затем query параметр `token`. Использование заголовка более безопасно, так как токен не попадает в URL и логи.

## Действия

### 1. Поиск игры (`find_game`)

Запрашивает поиск противника и добавление в очередь. 

**Важно:** Если у пользователя уже есть активная игра (не завершенная и не отмененная), система автоматически вернет информацию о ней вместо начала нового поиска.

**Запрос:**
```json
{
  "action": "find_game",
  "data": {}
}
```

**Ответ при наличии активной игры:**
```json
{
  "action": "active_game_found",
  "status": "success",
  "data": {
    "game_id": 24,
    "status": "player1_turn",
    "opponent": {
      "id": 2,
      "username": "player2"
    },
    "player1": {
      "id": 1,
      "username": "player1"
    },
    "player2": {
      "id": 2,
      "username": "player2"
    },
    "current_turn": {
      "id": 1,
      "username": "player1"
    }
  }
}
```

**Ответ при начале поиска:**
```json
{
  "action": "search_started",
  "status": "success",
  "message": "Поиск противника начат"
}
```

**Ответ при найденном противнике:**
```json
{
  "action": "game_found",
  "status": "success",
  "data": {
    "game_id": 1,
    "opponent": {
      "id": 2,
      "username": "player2"
    },
    "player1": {
      "id": 1,
      "username": "player1"
    },
    "player2": {
      "id": 2,
      "username": "player2"
    }
  }
}
```

После получения `active_game_found` или `game_found`, игрок должен подключиться к игровому WebSocket:
```
ws://host/ws/game/<game_id>/?token=<token>
```

**Примечание:** Если получен `active_game_found`, это означает, что у пользователя уже есть незавершенная игра, и он должен продолжить её, а не начинать новую.

### 2. Отмена поиска (`cancel_search`)

Отменяет поиск игры и удаляет игрока из очереди.

**Запрос:**
```json
{
  "action": "cancel_search",
  "data": {}
}
```

**Ответ:**
```json
{
  "action": "search_cancelled",
  "status": "success",
  "message": "Поиск игры отменен"
}
```

## Алгоритм подбора противника

Подбор происходит по следующим критериям:

1. **Процент побед (win rate)**
   - Максимальная разница: 20%
   - Если идеальный противник не найден, критерий расширяется до 40%

2. **Количество игр**
   - Максимальная разница: 50 игр
   - Если идеальный противник не найден, критерий расширяется до 100 игр

3. **Оценка совпадения**
   - Рассчитывается как: `skill_diff * 2 + games_diff * 0.1`
   - Выбирается противник с наименьшей оценкой

## Пример использования

```javascript
// Подключение к matchmaking
const matchmaking = new WebSocket('ws://localhost:8000/ws/matchmaking/?token=your_token');

matchmaking.onopen = () => {
  // Запрашиваем поиск игры
  matchmaking.send(JSON.stringify({
    action: 'find_game',
    data: {}
  }));
};

matchmaking.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  switch (message.action) {
    case 'active_game_found':
      const activeGameId = message.data.game_id;
      console.log('Найдена активная игра! ID:', activeGameId);
      console.log('Противник:', message.data.opponent.username);
      console.log('Текущий ход:', message.data.current_turn.username);
      
      // Подключаемся к существующей игре
      const activeGameWs = new WebSocket(
        `ws://localhost:8000/ws/game/${activeGameId}/?token=your_token`
      );
      
      // Настраиваем обработчики игрового WebSocket
      setupGameWebSocket(activeGameWs);
      break;
      
    case 'search_started':
      console.log('Поиск начат...');
      break;
      
    case 'game_found':
      const gameId = message.data.game_id;
      console.log('Игра найдена! ID:', gameId);
      console.log('Противник:', message.data.opponent.username);
      
      // Подключаемся к игровому WebSocket
      const gameWs = new WebSocket(
        `ws://localhost:8000/ws/game/${gameId}/?token=your_token`
      );
      
      // Настраиваем обработчики игрового WebSocket
      setupGameWebSocket(gameWs);
      break;
      
    case 'search_cancelled':
      console.log('Поиск отменен');
      break;
      
    case 'error':
      console.error('Ошибка:', message.message);
      break;
  }
};

// Отмена поиска
function cancelSearch() {
  matchmaking.send(JSON.stringify({
    action: 'cancel_search',
    data: {}
  }));
}
```

## Примечания

1. **Проверка активных игр**: При запросе `find_game` система сначала проверяет наличие активных игр у пользователя. Если найдена активная игра, возвращается `active_game_found` вместо начала нового поиска
2. **Очередь ожидания**: Игроки добавляются в очередь и проверяются каждые 3 секунды
3. **Автоматическое создание сессии**: После подбора противника автоматически создается сессия игры
4. **Уведомления**: Оба игрока получают уведомление о найденной игре через WebSocket
5. **Отключение**: При отключении от WebSocket игрок автоматически удаляется из очереди
6. **Автоматическая отмена игры**: Если оба игрока отключились от игрового WebSocket, игра автоматически отменяется
