from rest_framework_simplejwt.tokens import RefreshToken

from core.models.user import User
from core.models.user_bot import UserBot


IS_BOT_CLAIM = "is_bot"
USER_BOT_ID_CLAIM = "user_bot_id"


class UserBotRefreshToken(RefreshToken):
    @classmethod
    def for_user_bot(cls, user: User, user_bot: UserBot) -> "UserBotRefreshToken":
        token = cls.for_user(user)
        token[IS_BOT_CLAIM] = True
        token[USER_BOT_ID_CLAIM] = user_bot.id
        return token
