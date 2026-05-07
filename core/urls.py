from django.urls import path

from core.views.user import (
    UserJWTRefreshAPIView,
    UserMeAPIView,
    UserMeConfirmPhoneAPIView,
    UserPasswordLoginAPIView,
    UserOTPConfirmAPIView,
    UserOTPRequestAPIView,
)


urlpatterns = [
    path("auth/otp/request/", UserOTPRequestAPIView.as_view(), name="auth-otp-request"),
    path("auth/otp/confirm/", UserOTPConfirmAPIView.as_view(), name="auth-otp-confirm"),
    path("auth/login/", UserPasswordLoginAPIView.as_view(), name="auth-password-login"),
    path("auth/jwt/refresh/", UserJWTRefreshAPIView.as_view(), name="auth-jwt-refresh"),

    path("user/me/", UserMeAPIView.as_view(), name="user-me"),
    path("user/me/confirm-phone/", UserMeConfirmPhoneAPIView.as_view(), name="user-me-confirm-phone"),

    # Backward compatibility
    path("auth/register/request-otp/", UserOTPRequestAPIView.as_view(), name="auth-register-request-otp"),
    path("auth/register/confirm-otp/", UserOTPConfirmAPIView.as_view(), name="auth-register-confirm-otp"),
]
