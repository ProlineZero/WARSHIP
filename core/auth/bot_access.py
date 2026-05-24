from functools import wraps
from typing import Callable

from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request

from core.tokens.user_bot import IS_BOT_CLAIM, USER_BOT_ID_CLAIM

_DENY_BOT_ATTR = "_deny_bot"
_ALLOW_BOT_ONLY_ATTR = "_allow_bot_only"


def is_bot_request(request: Request) -> bool:
    token = getattr(request, "auth", None)
    if token is None:
        return False
    getter = getattr(token, "get", None)
    if callable(getter):
        return bool(getter(IS_BOT_CLAIM))
    return bool(getattr(token, IS_BOT_CLAIM, False))


def get_request_user_bot_id(request: Request) -> int | None:
    token = getattr(request, "auth", None)
    if token is None:
        return None
    getter = getattr(token, "get", None)
    if callable(getter):
        bot_id = getter(USER_BOT_ID_CLAIM)
    else:
        bot_id = getattr(token, USER_BOT_ID_CLAIM, None)
    return int(bot_id) if bot_id is not None else None


def deny_bot(view_method: Callable) -> Callable:
    @wraps(view_method)
    def wrapper(*args, **kwargs):
        return view_method(*args, **kwargs)

    setattr(wrapper, _DENY_BOT_ATTR, True)
    return wrapper


def allow_bot_only(view_method: Callable) -> Callable:
    @wraps(view_method)
    def wrapper(*args, **kwargs):
        return view_method(*args, **kwargs)

    setattr(wrapper, _ALLOW_BOT_ONLY_ATTR, True)
    return wrapper


class BotAccessMixin:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        handler = getattr(self, request.method.lower(), None)
        if handler is None:
            return

        if getattr(handler, _ALLOW_BOT_ONLY_ATTR, False):
            if not is_bot_request(request):
                raise PermissionDenied("Доступно только для бота.")
            return

        if getattr(handler, _DENY_BOT_ATTR, False) and is_bot_request(request):
            raise PermissionDenied("Действие недоступно для бота.")
