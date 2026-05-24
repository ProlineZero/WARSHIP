import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from centrifuge import (
    Client,
    ClientEventHandler,
    ConnectedContext,
    ConnectingContext,
    DisconnectedContext,
    PublicationContext,
    SubscriptionEventHandler,
)

logger = logging.getLogger(__name__)


class _UserChannelHandler(SubscriptionEventHandler):
    def __init__(self, queue: asyncio.Queue):
        self._queue = queue

    async def on_publication(self, ctx: PublicationContext) -> None:
        data = ctx.pub.data
        if isinstance(data, dict):
            await self._queue.put(data)


class _GameChannelHandler(SubscriptionEventHandler):
    def __init__(self, queue: asyncio.Queue):
        self._queue = queue

    async def on_publication(self, ctx: PublicationContext) -> None:
        data = ctx.pub.data
        if isinstance(data, dict):
            await self._queue.put(data)


class _ClientHandler(ClientEventHandler):
    async def on_connected(self, ctx: ConnectedContext) -> None:
        logger.debug('Centrifugo connected: %s', ctx)

    async def on_disconnected(self, ctx: DisconnectedContext) -> None:
        logger.debug('Centrifugo disconnected: %s', ctx)

    async def on_connecting(self, ctx: ConnectingContext) -> None:
        logger.debug('Centrifugo connecting: %s', ctx)


class AsyncRealtimeClient:
    def __init__(
        self,
        ws_url: str,
        get_connection_token: Callable[[], Awaitable[str]],
    ):
        self._ws_url = ws_url
        self._get_connection_token = get_connection_token
        self._client: Client | None = None
        self._user_sub = None
        self._game_sub = None
        self._user_queue: asyncio.Queue = asyncio.Queue()
        self._game_queue: asyncio.Queue = asyncio.Queue()

    async def connect(self, user_id: int) -> None:
        self._client = Client(
            self._ws_url,
            events=_ClientHandler(),
            get_token=self._get_connection_token,
        )
        await self._client.connect()
        channel = f'user_{user_id}'
        if self._user_sub:
            await self._user_sub.unsubscribe()
        self._user_queue = asyncio.Queue()
        self._user_sub = self._client.new_subscription(
            channel,
            events=_UserChannelHandler(self._user_queue),
        )
        await self._user_sub.subscribe()

    async def subscribe_game(self, game_id: int) -> None:
        if not self._client:
            return
        channel = f'game_{game_id}'
        if self._game_sub:
            await self._game_sub.unsubscribe()
        self._game_queue = asyncio.Queue()
        self._game_sub = self._client.new_subscription(
            channel,
            events=_GameChannelHandler(self._game_queue),
        )
        await self._game_sub.subscribe()

    async def disconnect(self) -> None:
        if self._game_sub:
            await self._game_sub.unsubscribe()
            self._game_sub = None
        if self._user_sub:
            await self._user_sub.unsubscribe()
            self._user_sub = None
        if self._client:
            await self._client.disconnect()
            self._client = None

    async def wait_user_event(self, action: str, timeout: float) -> dict | None:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                message = await asyncio.wait_for(self._user_queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return None
            if message.get('action') == action:
                return message

    async def wait_game_event(self, actions: set[str], timeout: float) -> dict | None:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                message = await asyncio.wait_for(self._game_queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return None
            if message.get('action') in actions:
                return message

    async def drain_user_queue(self) -> None:
        while not self._user_queue.empty():
            self._user_queue.get_nowait()

    async def drain_game_queue(self) -> list[dict]:
        events: list[dict] = []
        while not self._game_queue.empty():
            events.append(self._game_queue.get_nowait())
        return events

    async def wait_game_event_or_drain(self, actions: set[str], timeout: float) -> tuple[list[dict], dict | None]:
        """Ждёт событие из actions; параллельно возвращает все накопившиеся сообщения."""
        drained = await self.drain_game_queue()
        matched = next((event for event in drained if event.get('action') in actions), None)
        if matched:
            return drained, matched
        if timeout <= 0:
            return drained, None
        deadline = time.monotonic() + timeout
        pending = list(drained)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return pending, None
            try:
                message = await asyncio.wait_for(self._game_queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return pending, None
            pending.append(message)
            if message.get('action') in actions:
                return pending, message
