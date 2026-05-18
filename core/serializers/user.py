from django.contrib.auth import get_user_model
from django.db.models import Q
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken


User = get_user_model()


class UserOTPRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)

    def validate_phone(self, value: str) -> str:
        try:
            return User._parse_phone_number(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def create(self, validated_data: dict) -> dict:
        phone = validated_data["phone"]

        user = (
            User.objects
            .filter(Q(phone=phone) | Q(tmp_phone=phone) | Q(username=phone))
            .order_by("-id")
            .first()
        )
        is_new_user = False
        if not user:
            user = User(
                username=phone,
                phone=None,
                tmp_phone=phone,
                is_active=True,
            )
            user.set_unusable_password()
            user.save()
            is_new_user = True

        message = user.bind_phone(phone=phone)
        return {
            "message": message,
            "is_new_user": is_new_user,
        }


class UserOTPConfirmSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)
    code = serializers.CharField(max_length=6)
    password = serializers.CharField(required=False, allow_blank=False, write_only=True, min_length=6)

    def validate_phone(self, value: str) -> str:
        try:
            return User._parse_phone_number(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate(self, attrs: dict) -> dict:
        phone = attrs["phone"]

        user = (
            User.objects.filter(Q(phone=phone) | Q(tmp_phone=phone))
            .exclude(otp_code__isnull=True)
            .order_by("-id")
            .first()
        )
        if not user:
            raise serializers.ValidationError({"phone": "Для этого номера не запрошен OTP-код."})

        attrs["user"] = user
        return attrs

    def save(self, **kwargs) -> dict:
        user: User = self.validated_data["user"]
        code: str = self.validated_data["code"]
        password = self.validated_data.get("password")

        success, message = user.bind_phone(phone=user.tmp_phone or user.phone, code=code)
        if not success:
            raise serializers.ValidationError({"code": message})

        user.refresh_from_db()

        if password:
            user.set_password(password)
            user.save()
        # else:
        #     user.set_password(code)
        #     user.save()

        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "message": message,
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "phone": user.phone,
            },
        }


class UserPasswordLoginSerializer(serializers.Serializer):
    login = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs: dict) -> dict:
        login = attrs.get("login")
        password = attrs.get("password")

        user = None

        # Пытаемся интерпретировать логин как телефон
        try:
            phone = User._parse_phone_number(login)
        except DjangoValidationError:
            phone = None

        qs = User.objects.all()
        if phone:
            user = qs.filter(Q(phone=phone) | Q(tmp_phone=phone)).order_by("-id").first()
        if not user:
            user = qs.filter(username=login).order_by("-id").first()

        if not user or not user.check_password(password):
            raise serializers.ValidationError({"non_field_errors": "Неверный логин или пароль."})

        if not user.is_active:
            raise serializers.ValidationError({"non_field_errors": "Пользователь деактивирован."})

        attrs["user"] = user
        return attrs

    def save(self, **kwargs) -> dict:
        user: User = self.validated_data["user"]
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "phone": user.phone,
            },
        }


class UserPasswordResetRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)

    def validate_phone(self, value: str) -> str:
        try:
            return User._parse_phone_number(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def save(self, **kwargs) -> dict:
        phone = self.validated_data["phone"]

        user = User.objects.filter(
            Q(phone=phone) | 
            Q(username=phone)
        ).order_by("-id").first()
        if not user:
            raise serializers.ValidationError({"phone": "Пользователь с таким номером не найден."})

        if not user.is_active:
            raise serializers.ValidationError({"phone": "Пользователь деактивирован."})

        message = user.bind_phone(phone=phone)
        if message.startswith("Ошибка") or message.startswith("Неверный"):
            raise serializers.ValidationError({"phone": message})

        return {"message": message}


class UserPasswordResetConfirmSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)
    code = serializers.CharField(max_length=6)
    password = serializers.CharField(write_only=True, min_length=6)

    def validate_phone(self, value: str) -> str:
        try:
            return User._parse_phone_number(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate(self, attrs: dict) -> dict:
        phone = attrs["phone"]

        user = (
            User.objects.filter(Q(phone=phone) | Q(tmp_phone=phone))
            .exclude(otp_code__isnull=True)
            .order_by("-id")
            .first()
        )
        if not user:
            raise serializers.ValidationError({"phone": "Для этого номера не запрошен OTP-код."})

        attrs["user"] = user
        return attrs

    def save(self, **kwargs) -> dict:
        user: User = self.validated_data["user"]
        code: str = self.validated_data["code"]
        password: str = self.validated_data["password"]

        success, message = user.bind_phone(phone=user.tmp_phone or user.phone, code=code)
        if not success:
            raise serializers.ValidationError({"code": message})

        user.set_password(password)
        user.save(update_fields=["password"])

        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "message": "Пароль успешно изменён.",
            "user": {
                "id": user.id,
                "phone": user.phone,
            },
        }
