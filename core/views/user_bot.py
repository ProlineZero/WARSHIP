from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.auth import BotAccessMixin, deny_bot
from core.auth.admin_access import IsActiveUser
from core.models.user_bot import UserBot
from core.serializers.user_bot import UserBotCreateSerializer, UserBotLoginSerializer, UserBotSerializer


class UserBotLoginAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        serializer = UserBotLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return Response(payload, status=status.HTTP_200_OK)

class UserBotAPIView(BotAccessMixin, APIView):
    permission_classes = [IsAuthenticated, IsActiveUser]


    def get(self, request, *args, **kwargs):
        bot_id = kwargs.pop("id", None)
        qs = request.user.user_bots.all()
        if bot_id:
            try:
                qs = qs.get(id=bot_id)
            except UserBot.DoesNotExist as exc:
                raise NotFound(detail="Бот не найден.") from exc
        return Response(UserBotSerializer(qs, many=not bot_id).data, status=status.HTTP_200_OK)
    
    @deny_bot
    def post(self, request, *args, **kwargs):
        request.data["user"] = request.user.id
        serializer = UserBotCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return Response(payload, status=status.HTTP_201_CREATED)
    
    @deny_bot
    def put(self, request, *args, **kwargs):
        serializer = UserBotCreateSerializer(instance=request.user.user_bots.get(id=kwargs["id"]), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return Response(payload, status=status.HTTP_200_OK)
    
    @deny_bot
    def delete(self, request, *args, **kwargs):
        try:
            user_bot = request.user.user_bots.get(id=kwargs["id"])
        except UserBot.DoesNotExist as exc:
            raise NotFound(detail="Бот не найден.") from exc
        user_bot.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)