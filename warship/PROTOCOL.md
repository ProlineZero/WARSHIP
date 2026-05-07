# Протокол WebSocket для игры в морской бой

## Подключение

### 1. Matchmaking (поиск противника)
```
ws://host/ws/matchmaking/?token=<jwt_token>
```
или через заголовок:
```
ws://host/ws/matchmaking/
```
с заголовком: `Authorization: Bearer <jwt_token>`

**Параметры:**
- `token` - JWT токен доступа (query параметр, для обратной совместимости)
- `Authorization` - заголовок с токеном в формате `Bearer <token>` (предпочтительно)

**Примеры:**
```
# Через query параметр
ws://localhost:8000/ws/matchmaking/?token=eyJ0eXAiOiJKV1QiLCJhbGc...

# Через заголовок (предпочтительно)
ws://localhost:8000/ws/matchmaking/
# с заголовком: Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...
```

### 2. Игровая сессия
```
ws://host/ws/game/<game_id>/?token=<jwt_token>
```
или через заголовок:
```
ws://host/ws/game/<game_id>/
```
с заголовком: `Authorization: Bearer <jwt_token>`

**Параметры:**
- `game_id` - ID сессии игры (число)
- `token` - JWT токен доступа (query параметр, для обратной совместимости)
- `Authorization` - заголовок с токеном в формате `Bearer <token>` (предпочтительно)

**Примеры:**
```
# Через query параметр
ws://localhost:8000/ws/game/1/?token=eyJ0eXAiOiJKV1QiLCJhbGc...

# Через заголовок (предпочтительно)
ws://localhost:8000/ws/game/1/
# с заголовком: Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...
```

**Примечание:** Токен можно передавать как через заголовок `Authorization: Bearer <token>` (предпочтительно, более безопасно), так и через query параметр `?token=<token>` (для обратной совместимости). Middleware сначала проверяет заголовок, затем query параметр.

## Формат сообщений

Все сообщения передаются в формате JSON:

```json
{
  "action": "<название действия>",
  "data": { ... }
}
```

## Входящие сообщения (от клиента к серверу)

### 1. Размещение кораблей (`place_ships`)

Размещает корабли игрока на поле.

**Формат:**
```json
{
  "action": "place_ships",
  "data": {
    "ships": [
      {
        "size": 4,
        "cells": [[0, 0], [0, 1], [0, 2], [0, 3]]
      },
      {
        "size": 3,
        "cells": [[2, 0], [2, 1], [2, 2]]
      },
      {
        "size": 3,
        "cells": [[4, 0], [4, 1], [4, 2]]
      },
      {
        "size": 2,
        "cells": [[6, 0], [6, 1]]
      },
      {
        "size": 2,
        "cells": [[8, 0], [8, 1]]
      },
      {
        "size": 2,
        "cells": [[0, 5], [0, 6]]
      },
      {
        "size": 1,
        "cells": [[2, 5]]
      },
      {
        "size": 1,
        "cells": [[4, 5]]
      },
      {
        "size": 1,
        "cells": [[6, 5]]
      },
      {
        "size": 1,
        "cells": [[8, 5]]
      }
    ]
  }
}
```

**Правила размещения:**
- 1 корабль на 4 клетки
- 2 корабля на 3 клетки
- 3 корабля на 2 клетки
- 4 корабля на 1 клетку
- Корабли не должны пересекаться
- Корабли не должны соприкасаться (включая диагонали)
- Корабли должны быть размещены горизонтально или вертикально

**Ответ при успехе:**
```json
{
  "action": "place_ships",
  "status": "success",
  "message": "Корабли успешно размещены"
}
```

**Ответ при ошибке (с координатами проблемных клеток):**
```json
{
  "action": "error",
  "status": "error",
  "message": "Корабли не должны соприкасаться",
  "data": {
    "error_cells": [[0, 0], [1, 0]],
    "error_type": "touching"
  }
}
```

**Типы ошибок размещения кораблей:**
- `out_of_bounds` - клетки выходят за границы поля
- `intersection` - корабли пересекаются
- `touching` - корабли соприкасаются
- `invalid_shape` - корабль размещен не горизонтально/вертикально

**Примеры ошибок с координатами:**

**Ошибка: клетки выходят за границы**
```json
{
  "action": "error",
  "status": "error",
  "message": "Клетки выходят за границы поля размером 10x10",
  "data": {
    "error_cells": [[10, 5], [11, 6]],
    "error_type": "out_of_bounds"
  }
}
```

**Ошибка: корабли пересекаются**
```json
{
  "action": "error",
  "status": "error",
  "message": "Корабли пересекаются",
  "data": {
    "error_cells": [[5, 5], [5, 6]],
    "error_type": "intersection"
  }
}
```

**Ошибка: корабли соприкасаются**
```json
{
  "action": "error",
  "status": "error",
  "message": "Корабли не должны соприкасаться",
  "data": {
    "error_cells": [[0, 0], [1, 0], [0, 1]],
    "error_type": "touching"
  }
}
```

**Ошибка: неверная форма корабля**
```json
{
  "action": "error",
  "status": "error",
  "message": "Корабль должен быть размещен горизонтально или вертикально",
  "data": {
    "error_cells": [[0, 0], [0, 1], [1, 2]],
    "error_type": "invalid_shape"
  }
}
```

---

### 2. Выполнение выстрела (`make_shot`)

Выполняет выстрел по координатам противника.

**Формат:**
```json
{
  "action": "make_shot",
  "data": {
    "row": 5,
    "col": 3
  }
}
```

**Параметры:**
- `row` - номер строки (0-9 для поля 10x10)
- `col` - номер столбца (0-9 для поля 10x10)

**Ответ при успехе:**
```json
{
  "action": "shot_result",
  "status": "success",
  "data": {
    "success": true,
    "hit": true,
    "ship_destroyed": false,
    "ship_size": 3,
    "game_finished": false,
    "winner": null,
    "move_id": 42,
    "row": 5,
    "col": 3
  }
}
```

**Ответ при промахе:**
```json
{
  "action": "shot_result",
  "status": "success",
  "data": {
    "success": true,
    "hit": false,
    "ship_destroyed": false,
    "ship_size": null,
    "game_finished": false,
    "winner": null,
    "move_id": 43,
    "row": 5,
    "col": 4
  }
}
```

**Ответ при уничтожении корабля:**
```json
{
  "action": "shot_result",
  "status": "success",
  "data": {
    "success": true,
    "hit": true,
    "ship_destroyed": true,
    "ship_size": 2,
    "game_finished": false,
    "winner": null,
    "move_id": 44,
    "row": 6,
    "col": 0
  }
}
```

**Ответ при завершении игры:**
```json
{
  "action": "shot_result",
  "status": "success",
  "data": {
    "success": true,
    "hit": true,
    "ship_destroyed": true,
    "ship_size": 1,
    "game_finished": true,
    "winner": {
      "id": 1,
      "username": "player1"
    },
    "move_id": 45,
    "row": 8,
    "col": 5
  }
}
```

**Ответ при ошибке:**
```json
{
  "action": "error",
  "status": "error",
  "message": "Вы уже стреляли по этим координатам"
}
```

---

### 3. Получение статуса игры (`get_game_status`)

Запрашивает текущий статус игры.

**Формат:**
```json
{
  "action": "get_game_status",
  "data": {}
}
```

**Ответ:**
```json
{
  "action": "game_status",
  "status": "success",
  "data": {
    "game_id": 1,
    "status": "player1_turn",
    "player1": {
      "id": 1,
      "username": "player1",
      "ships_placed": true
    },
    "player2": {
      "id": 2,
      "username": "player2",
      "ships_placed": true
    },
    "current_turn": {
      "id": 1,
      "username": "player1"
    },
    "winner": null,
    "board_size": 10,
    "started_at": "2026-01-28T12:00:00Z",
    "finished_at": null,
    "moves": [
      {
        "id": 1,
        "player_id": 1,
        "row": 5,
        "col": 3,
        "hit": true,
        "ship_destroyed": false,
        "ship_size": 3,
        "created_at": "2026-01-28T12:01:00Z"
      },
      {
        "id": 2,
        "player_id": 2,
        "row": 0,
        "col": 0,
        "hit": false,
        "ship_destroyed": false,
        "ship_size": null,
        "created_at": "2026-01-28T12:01:30Z"
      }
    ]
  }
}
```

**Возможные статусы игры:**
- `waiting_ships` - ожидание размещения кораблей
- `player1_turn` - ход первого игрока
- `player2_turn` - ход второго игрока
- `finished` - игра завершена
- `cancelled` - игра отменена

---

### 4. Получение состояния доски (`get_board_state`)

Запрашивает состояние доски для текущего игрока.

**Формат:**
```json
{
  "action": "get_board_state",
  "data": {}
}
```

**Ответ:**
```json
{
  "action": "board_state",
  "status": "success",
  "data": {
    "my_ships": [
      {
        "size": 4,
        "cells": [[0, 0], [0, 1], [0, 2], [0, 3]],
        "destroyed": false,
        "hit_cells": []
      },
      {
        "size": 3,
        "cells": [[2, 0], [2, 1], [2, 2]],
        "destroyed": true,
        "hit_cells": [[2, 0], [2, 1], [2, 2]]
      }
    ],
    "my_shots": [
      {
        "row": 5,
        "col": 3,
        "hit": true,
        "ship_destroyed": false,
        "ship_size": 3
      },
      {
        "row": 5,
        "col": 4,
        "hit": false,
        "ship_destroyed": false,
        "ship_size": null
      }
    ],
    "opponent_shots": [
      {
        "row": 0,
        "col": 0,
        "hit": false,
        "ship_destroyed": false,
        "ship_size": null
      },
      {
        "row": 2,
        "col": 0,
        "hit": true,
        "ship_destroyed": true,
        "ship_size": 3
      }
    ],
    "board_size": 10
  }
}
```

---

## Исходящие сообщения (от сервера к клиенту)

### 1. Сообщение об ошибке (`error`)

Отправляется при любой ошибке.

**Формат:**
```json
{
  "action": "error",
  "status": "error",
  "message": "Описание ошибки"
}
```

**Примеры ошибок:**

**Ошибки без дополнительных данных:**
- `"Не указано действие (action)"`
- `"Неверный формат JSON"`
- `"Не указаны корабли для размещения"`
- `"Игра уже начата, нельзя размещать корабли"`
- `"Не указаны координаты выстрела (row, col)"`
- `"Сейчас не ваш ход"`
- `"Вы уже стреляли по этим координатам"`

**Ошибки размещения кораблей с координатами (в поле `data`):**
- `"Клетки выходят за границы поля размером 10x10"` - с координатами в `data.error_cells`
- `"Корабли пересекаются"` - с координатами пересекающихся клеток
- `"Корабли не должны соприкасаться"` - с координатами соприкасающихся клеток
- `"Корабль должен быть размещен горизонтально или вертикально"` - с координатами корабля

**Примеры ошибок с координатами:**

**Ошибка: клетки выходят за границы**
```json
{
  "action": "error",
  "status": "error",
  "message": "Клетки выходят за границы поля размером 10x10",
  "data": {
    "error_cells": [[10, 5], [11, 6]],
    "error_type": "out_of_bounds"
  }
}
```

**Ошибка: корабли пересекаются**
```json
{
  "action": "error",
  "status": "error",
  "message": "Корабли пересекаются",
  "data": {
    "error_cells": [[5, 5], [5, 6]],
    "error_type": "intersection"
  }
}
```

**Ошибка: корабли соприкасаются**
```json
{
  "action": "error",
  "status": "error",
  "message": "Корабли не должны соприкасаться",
  "data": {
    "error_cells": [[0, 0], [1, 0], [0, 1]],
    "error_type": "touching"
  }
}
```

**Ошибка: неверная форма корабля**
```json
{
  "action": "error",
  "status": "error",
  "message": "Корабль должен быть размещен горизонтально или вертикально",
  "data": {
    "error_cells": [[0, 0], [0, 1], [1, 2]],
    "error_type": "invalid_shape"
  }
}
```

**Типы ошибок размещения кораблей:**
- `out_of_bounds` - клетки выходят за границы поля
- `intersection` - корабли пересекаются
- `touching` - корабли соприкасаются
- `invalid_shape` - корабль размещен не горизонтально/вертикально

---

### 2. Автоматические обновления статуса игры

После размещения кораблей или выполнения выстрела все участники игры автоматически получают обновленный статус игры:

```json
{
  "action": "game_status",
  "status": "success",
  "data": {
    "game_id": 1,
    "status": "player2_turn",
    "current_turn": {
      "id": 2,
      "username": "player2"
    },
    ...
  }
}
```

**Как определить чей ход:**
- Проверьте поле `current_turn` в ответе `game_status`
- Если `current_turn.id` совпадает с ID текущего пользователя - это его ход
- Если `current_turn` равен `null` - игра еще не начата или завершена

---

### 3. Уведомление о начале игры (`game_started`)

Автоматически отправляется всем участникам игры, когда оба игрока разместили корабли и игра началась.

```json
{
  "action": "game_started",
  "status": "success",
  "data": {
    "game_id": 1,
    "current_turn": {
      "id": 1,
      "username": "player1"
    },
    "started_at": "2026-01-28T12:00:00Z"
  }
}
```

**Примечание:** После получения этого сообщения игра переходит в активную фазу, и игрок, указанный в `current_turn`, может делать первый ход.

---

### 4. Уведомление о завершении игры (`game_finished`)

Автоматически отправляется всем участникам игры, когда один из игроков победил.

```json
{
  "action": "game_finished",
  "status": "success",
  "data": {
    "game_id": 1,
    "winner": {
      "id": 1,
      "username": "player1"
    },
    "finished_at": "2026-01-28T12:30:00Z"
  }
}
```

**Примечание:** После получения этого сообщения игра завершена, и дальнейшие действия (выстрелы, размещение кораблей) невозможны.

---

### 5. Автоматические обновления результатов выстрелов

После выполнения выстрела все участники игры получают результат:

```json
{
  "action": "shot_result",
  "status": "success",
  "data": {
    "success": true,
    "hit": true,
    "ship_destroyed": false,
    "ship_size": 3,
    "game_finished": false,
    "winner": null,
    "move_id": 42,
    "row": 5,
    "col": 3
  }
}
```

---

## Протокол игры

### Этап 1: Создание игры

Игра создается через REST API (не через WebSocket). После создания игры оба игрока подключаются к WebSocket.

### Этап 2: Размещение кораблей

1. Оба игрока подключаются к WebSocket с токеном аутентификации
2. Каждый игрок отправляет `place_ships` со своими кораблями
3. После размещения кораблей обоими игроками игра автоматически начинается
4. Все участники получают уведомление `game_started` с информацией о первом ходе
5. Статус игры меняется на `player1_turn` или `player2_turn`

### Этап 3: Игровой процесс

1. Игрок, чей сейчас ход, отправляет `make_shot` с координатами
2. Сервер проверяет выстрел и отправляет результат всем участникам
3. Если промах - ход переходит к противнику
4. Если попадание - игрок продолжает ходить
5. Если все корабли противника уничтожены - игра завершается

### Этап 5: Завершение игры

1. Когда все корабли одного из игроков уничтожены, игра завершается
2. Статус игры меняется на `finished`
3. Устанавливается победитель
4. Все участники получают уведомление `game_finished` с информацией о победителе
5. Все участники также получают финальный статус игры через `game_status`

---

## Matchmaking WebSocket

### Действия для matchmaking

#### 1. Поиск игры (`find_game`)

Запрашивает поиск противника и добавление в очередь. Если у пользователя уже есть активная игра, возвращается информация о ней вместо начала нового поиска.

**Формат:**
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
`ws://host/ws/game/<game_id>/?token=<token>`

#### 2. Отмена поиска (`cancel_search`)

Отменяет поиск игры и удаляет игрока из очереди.

**Формат:**
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

---

## Игровой WebSocket

---

## Примеры использования

### Пример 1: Полный цикл игры

**Шаг 1: Подключение игрока 1**
```javascript
const ws1 = new WebSocket('ws://localhost:8000/ws/game/1/?token=token1');
```

**Шаг 2: Подключение игрока 2**
```javascript
const ws2 = new WebSocket('ws://localhost:8000/ws/game/1/?token=token2');
```

**Шаг 3: Размещение кораблей игроком 1**
```javascript
ws1.send(JSON.stringify({
  action: 'place_ships',
  data: {
    ships: [
      {size: 4, cells: [[0,0], [0,1], [0,2], [0,3]]},
      {size: 3, cells: [[2,0], [2,1], [2,2]]},
      // ... остальные корабли
    ]
  }
}));
```

**Шаг 4: Размещение кораблей игроком 2**
```javascript
ws2.send(JSON.stringify({
  action: 'place_ships',
  data: {
    ships: [
      {size: 4, cells: [[5,5], [5,6], [5,7], [5,8]]},
      // ... остальные корабли
    ]
  }
}));
```

**Шаг 5: Выполнение выстрела игроком 1**
```javascript
ws1.send(JSON.stringify({
  action: 'make_shot',
  data: {
    row: 5,
    col: 5
  }
}));
```

**Шаг 6: Обработка результата (получают оба игрока)**
```javascript
ws1.onmessage = (event) => {
  const message = JSON.parse(event.data);
  if (message.action === 'shot_result') {
    console.log('Попадание:', message.data.hit);
    console.log('Корабль уничтожен:', message.data.ship_destroyed);
  }
};
```

---

### Пример 2: Обработка ошибок с подсветкой проблемных клеток

```javascript
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  if (message.action === 'error') {
    console.error('Ошибка:', message.message);
    
    // Если есть координаты проблемных клеток, подсвечиваем их
    if (message.data && message.data.error_cells) {
      const errorCells = message.data.error_cells;
      const errorType = message.data.error_type;
      
      // Подсвечиваем проблемные клетки на доске
      errorCells.forEach(([row, col]) => {
        highlightErrorCell(row, col, errorType);
      });
      
      // Показываем сообщение пользователю
      showError(message.message, errorType);
    } else {
      // Просто показываем сообщение об ошибке
      showError(message.message);
    }
  }
};

function highlightErrorCell(row, col, errorType) {
  const cell = document.querySelector(`[data-row="${row}"][data-col="${col}"]`);
  if (cell) {
    // Добавляем класс для подсветки в зависимости от типа ошибки
    cell.classList.add(`error-${errorType}`);
    
    // Убираем подсветку через 3 секунды
    setTimeout(() => {
      cell.classList.remove(`error-${errorType}`);
    }, 3000);
  }
}

function showError(message, errorType) {
  // Показываем сообщение об ошибке пользователю
  const errorMessages = {
    'out_of_bounds': 'Клетки выходят за границы поля',
    'intersection': 'Корабли пересекаются',
    'touching': 'Корабли соприкасаются',
    'invalid_shape': 'Корабль должен быть размещен горизонтально или вертикально'
  };
  
  const errorText = errorType ? errorMessages[errorType] || message : message;
  alert(errorText);
}
```

---

### Пример 3: Отслеживание статуса игры

```javascript
// Запросить статус
ws.send(JSON.stringify({
  action: 'get_game_status',
  data: {}
}));

// Обработка обновлений статуса
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  if (message.action === 'game_status') {
    const status = message.data.status;
    
    if (status === 'finished') {
      console.log('Игра завершена!');
      console.log('Победитель:', message.data.winner.username);
    } else if (status === 'player1_turn') {
      console.log('Ход первого игрока');
    } else if (status === 'player2_turn') {
      console.log('Ход второго игрока');
    }
  }
};
```

---

## Примечания

1. **Аутентификация**: Все WebSocket соединения требуют JWT токен в query параметрах или заголовке Authorization
2. **Автоматические обновления**: После каждого действия (размещение кораблей, выстрел) все участники игры автоматически получают обновления
3. **Валидация**: Все действия валидируются на сервере перед выполнением
4. **Порядок ходов**: Сервер автоматически управляет очередностью ходов. Клиенты определяют чей ход по полю `current_turn` в ответах `game_status` и `game_started`
5. **Завершение игры**: Игра автоматически завершается при уничтожении всех кораблей одного из игроков. Все участники получают уведомление `game_finished`
6. **Автоматическая отмена игры**: Если оба игрока отключились от игрового WebSocket, игра автоматически отменяется (статус меняется на `cancelled`)
7. **Уведомления о статусе**: Игра автоматически отправляет уведомления `game_started` при начале игры и `game_finished` при завершении всем участникам
