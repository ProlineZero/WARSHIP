from rest_framework import serializers

from core.models.user import User
from core.models.user_bot import UserBot
from core.tokens.user_bot import UserBotRefreshToken


class UserBotLoginSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=150)

    def validate(self, attrs: dict) -> dict:
        token = attrs.get("token")

        try:
            user_bot = UserBot.objects.select_related("user").get(token=token)
        except UserBot.DoesNotExist as exc:
            raise serializers.ValidationError({"token": "Неверный токен."}) from exc

        user = user_bot.user
        if not user.is_active:
            raise serializers.ValidationError({"token": "Пользователь деактивирован."})

        attrs["user_bot"] = user_bot
        attrs["user"] = user
        return attrs

    def save(self, **kwargs) -> dict:
        user: User = self.validated_data["user"]
        user_bot: UserBot = self.validated_data["user_bot"]
        refresh = UserBotRefreshToken.for_user_bot(user, user_bot)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user_bot": {
                "id": user_bot.id,
                "name": user_bot.name,
                "description": user_bot.description,
            },
        }
