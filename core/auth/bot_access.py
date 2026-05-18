from functools import wraps
from typing import Callable

from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request

from core.tokens.user_bot import IS_BOT_CLAIM

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
