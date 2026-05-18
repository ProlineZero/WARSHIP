from django.urls import include, path

from core.views.user import (
    UserJWTRefreshAPIView,
    UserMeAPIView,
    UserMeConfirmPhoneAPIView,
    UserPasswordLoginAPIView,
    UserPasswordResetConfirmAPIView,
    UserPasswordResetRequestAPIView,
    UserOTPConfirmAPIView,
    UserOTPRequestAPIView,
)
from core.views.user_bot import UserBotAPIView, UserBotLoginAPIView


urlpatterns = [
    path("user/me/", include(
        [
            path("", UserMeAPIView.as_view(), name="user-me"),
            path("confirm-phone/", UserMeConfirmPhoneAPIView.as_view(), name="user-me-confirm-phone"),
            path("bots/", UserBotAPIView.as_view(), name="user-me-bots"),
            path("bots/<int:id>/", UserBotAPIView.as_view(), name="user-me-bots-detail"),
        ]
    )),
    path("auth/", include(
        [
            path("otp/request/", UserOTPRequestAPIView.as_view(), name="auth-otp-request"),
            path("otp/confirm/", UserOTPConfirmAPIView.as_view(), name="auth-otp-confirm"),
            path("login/", UserPasswordLoginAPIView.as_view(), name="auth-password-login"),
            path("password/reset/request/", UserPasswordResetRequestAPIView.as_view(), name="auth-password-reset-request"),
            path("password/reset/confirm/", UserPasswordResetConfirmAPIView.as_view(), name="auth-password-reset-confirm"),
            path("bot/login/", UserBotLoginAPIView.as_view(), name="auth-bot-login"),
            path("jwt/refresh/", UserJWTRefreshAPIView.as_view(), name="auth-jwt-refresh"),
        ]
    )),

    # Backward compatibility
    path("auth/register/request-otp/", UserOTPRequestAPIView.as_view(), name="auth-register-request-otp"),
    path("auth/register/confirm-otp/", UserOTPConfirmAPIView.as_view(), name="auth-register-confirm-otp"),
]
