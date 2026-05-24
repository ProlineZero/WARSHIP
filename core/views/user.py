from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from core.auth.admin_access import IsActiveUser
from core.auth.bot_access import BotAccessMixin, deny_bot
from core.serializers.me import UserMeConfirmPhoneSerializer, UserMeSerializer, UserMeUpdateSerializer
from core.serializers.user import (
    UserOTPConfirmSerializer,
    UserOTPRequestSerializer,
    UserPasswordLoginSerializer,
    UserPasswordResetConfirmSerializer,
    UserPasswordResetRequestSerializer,
)


class UserOTPRequestAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        serializer = UserOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return Response(
            payload,
            status=status.HTTP_200_OK,
        )


class UserOTPConfirmAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        serializer = UserOTPConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return Response(
            payload,
            status=status.HTTP_201_CREATED,
        )


class UserPasswordLoginAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        serializer = UserPasswordLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return Response(payload, status=status.HTTP_200_OK)


class UserPasswordResetRequestAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        serializer = UserPasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return Response(payload, status=status.HTTP_200_OK)


class UserPasswordResetConfirmAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        serializer = UserPasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return Response(payload, status=status.HTTP_200_OK)


class UserJWTRefreshAPIView(TokenRefreshView):
    permission_classes = []
    authentication_classes = []


class UserMeAPIView(BotAccessMixin, APIView):
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request, *args, **kwargs):
        return Response(UserMeSerializer(request.user).data, status=status.HTTP_200_OK)

    @deny_bot
    def put(self, request, *args, **kwargs):
        serializer = UserMeUpdateSerializer(
            instance=request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return Response(payload, status=status.HTTP_200_OK)


class UserMeConfirmPhoneAPIView(BotAccessMixin, APIView):
    permission_classes = [IsAuthenticated, IsActiveUser]

    @deny_bot
    def post(self, request, *args, **kwargs):
        serializer = UserMeConfirmPhoneSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return Response(payload, status=status.HTTP_200_OK)
