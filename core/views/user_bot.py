from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.serializers.user_bot import UserBotLoginSerializer


class UserBotLoginAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        serializer = UserBotLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return Response(payload, status=status.HTTP_200_OK)
