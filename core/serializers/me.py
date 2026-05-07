from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers


def get_user_model():
    """Ленивая загрузка модели пользователя."""
    from django.contrib.auth import get_user_model as django_get_user_model
    return django_get_user_model()


class UserMeSerializer(serializers.ModelSerializer):
    phone_pending = serializers.SerializerMethodField()

    class Meta:
        # Используем строковую ссылку на модель для избежания проблем с импортом
        model = 'core.User'
        fields = (
            "id",
            "phone",
            "username",
            "phone_pending",
            "first_name",
            "last_name",
            "email",
        )
        read_only_fields = ("id", "phone", "phone_pending")

    def get_phone_pending(self, obj) -> str | None:
        return obj.tmp_phone


class UserMeUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        # Используем строковую ссылку на модель для избежания проблем с импортом
        model = 'core.User'
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "phone",
            "password",
        )

    def validate_phone(self, value: str) -> str:
        User = get_user_model()
        try:
            return User._parse_phone_number(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def save(self, **kwargs) -> dict:
        user = self.instance

        update_fields: list[str] = []
        # Обновляем простые поля профиля, включая username
        for field in ("username", "first_name", "last_name", "email"):
            if field in self.validated_data:
                setattr(user, field, self.validated_data[field])
                update_fields.append(field)

        message = None
        phone = self.validated_data.get("phone")
        if phone and phone != user.phone:
            message = user.bind_phone(phone=phone)

        password = self.validated_data.get("password")
        if password:
            user.set_password(password)
            update_fields.append("password")

        if update_fields:
            user.save(update_fields=update_fields)

        user.refresh_from_db()
        return {
            "message": message,
            "user": UserMeSerializer(user).data,
        }


class UserMeConfirmPhoneSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6)

    def save(self, **kwargs) -> dict:
        user = self.context["request"].user
        code: str = self.validated_data["code"]

        if not user.tmp_phone:
            raise serializers.ValidationError({"code": "Нет номера телефона, ожидающего подтверждения."})

        success, message = user.bind_phone(phone=user.tmp_phone, code=code)
        if not success:
            raise serializers.ValidationError({"code": message})

        user.refresh_from_db()
        return {
            "message": message,
            "user": UserMeSerializer(user).data,
        }
