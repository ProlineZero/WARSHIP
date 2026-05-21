import asyncio
import logging
import threading
from collections.abc import Callable
from typing import Any

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
    def __init__(self, on_message: Callable[[dict], None]):
        self._on_message = on_message

    async def on_publication(self, ctx: PublicationContext) -> None:
        data = ctx.pub.data
        if isinstance(data, dict):
            self._on_message(data)


class _GameChannelHandler(SubscriptionEventHandler):
    def __init__(self, on_message: Callable[[dict], None]):
        self._on_message = on_message

    async def on_publication(self, ctx: PublicationContext) -> None:
        data = ctx.pub.data
        if isinstance(data, dict):
            self._on_message(data)


class _ClientHandler(ClientEventHandler):
    async def on_connected(self, ctx: ConnectedContext) -> None:
        logger.info('Centrifugo connected: %s', ctx)

    async def on_disconnected(self, ctx: DisconnectedContext) -> None:
        logger.info('Centrifugo disconnected: %s', ctx)

    async def on_connecting(self, ctx: ConnectingContext) -> None:
        logger.info('Centrifugo connecting: %s', ctx)


class RealtimeClient:
    """Фоновый asyncio-клиент Centrifugo для tkinter."""

    def __init__(self, ws_url: str, get_connection_token: Callable[[], str]):
        self._ws_url = ws_url
        self._get_connection_token = get_connection_token
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client: Client | None = None
        self._user_sub = None
        self._game_subs: dict[str, Any] = {}
        self._on_user_message: Callable[[dict], None] | None = None
        self._on_game_message: Callable[[dict], None] | None = None
        self._user_channel: str | None = None

    def start(
        self,
        on_user_message: Callable[[dict], None],
        on_game_message: Callable[[dict], None],
    ) -> None:
        self._on_user_message = on_user_message
        self._on_game_message = on_game_message
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._disconnect(), self._loop)
        if self._thread:
            self._thread.join(timeout=3)

    def subscribe_user(self, user_id: int) -> None:
        channel = f'user_{user_id}'
        self._user_channel = channel
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._subscribe_user(channel), self._loop)

    def subscribe_game(self, game_id: int) -> None:
        channel = f'game_{game_id}'
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._subscribe_game(channel), self._loop)

    def unsubscribe_game(self, game_id: int) -> None:
        channel = f'game_{game_id}'
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._unsubscribe(channel), self._loop)

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect())
        self._loop.run_forever()

    async def _get_token(self) -> str:
        return self._get_connection_token()

    async def _connect(self) -> None:
        self._client = Client(
            self._ws_url,
            events=_ClientHandler(),
            get_token=self._get_token,
        )
        await self._client.connect()
        if self._user_channel:
            await self._subscribe_user(self._user_channel)

    async def _disconnect(self) -> None:
        if self._client:
            await self._client.disconnect()
        if self._loop:
            self._loop.stop()

    async def _subscribe_user(self, channel: str) -> None:
        if not self._client:
            return
        if self._user_sub:
            await self._user_sub.unsubscribe()
        self._user_sub = self._client.new_subscription(
            channel,
            events=_UserChannelHandler(self._dispatch_user),
        )
        await self._user_sub.subscribe()

    async def _subscribe_game(self, channel: str) -> None:
        if not self._client or channel in self._game_subs:
            return
        sub = self._client.new_subscription(
            channel,
            events=_GameChannelHandler(self._dispatch_game),
        )
        self._game_subs[channel] = sub
        await sub.subscribe()

    async def _unsubscribe(self, channel: str) -> None:
        sub = self._game_subs.pop(channel, None)
        if sub:
            await sub.unsubscribe()

    def _dispatch_user(self, message: dict) -> None:
        if self._on_user_message:
            self._on_user_message(message)

    def _dispatch_game(self, message: dict) -> None:
        if self._on_game_message:
            self._on_game_message(message)
