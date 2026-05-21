import os

API_BASE_URL = os.getenv('WARSHIP_API_URL', 'http://localhost:8000/api')
CENTRIFUGO_WS_URL = os.getenv('WARSHIP_CENTRIFUGO_WS', 'ws://localhost:8001/connection/websocket')
BOARD_SIZE = 10
