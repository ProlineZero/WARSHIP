from rest_framework import serializers

from core.models.group import PlayerGroup
from core.models.user import User
from warship.utils import get_player_stats


class PlayerGroupSerializer(serializers.ModelSerializer):
    members_count = serializers.SerializerMethodField()

    class Meta:
        model = PlayerGroup
        fields = ['id', 'name', 'description', 'created_at', 'members_count']

    def get_members_count(self, obj):
        return obj.members.count()


class AdminUserCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=128, write_only=True)
    group_id = serializers.IntegerField(required=False, allow_null=True)
    is_staff = serializers.BooleanField(required=False, default=False)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('Пользователь с таким логином уже существует.')
        return value

    def validate_group_id(self, value):
        if value is not None and not PlayerGroup.objects.filter(id=value).exists():
            raise serializers.ValidationError('Группа не найдена.')
        return value

    def create(self, validated_data):
        group_id = validated_data.pop('group_id', None)
        password = validated_data.pop('password')
        user = User.objects.create(**validated_data)
        user.set_password(password)
        if group_id:
            user.group_id = group_id
        user.save()
        return user


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    group_id = serializers.IntegerField(required=False, allow_null=True)
    password = serializers.CharField(max_length=128, write_only=True, required=False)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'group_id', 'is_staff', 'password']

    def validate_group_id(self, value):
        if value is not None and not PlayerGroup.objects.filter(id=value).exists():
            raise serializers.ValidationError('Группа не найдена.')
        return value

    def update(self, instance, validated_data):
        group_id = validated_data.pop('group_id', serializers.empty)
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if group_id is not serializers.empty:
            instance.group_id = group_id
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class AdminUserSerializer(serializers.ModelSerializer):
    group = PlayerGroupSerializer(read_only=True)
    group_id = serializers.IntegerField(source='group.id', read_only=True, allow_null=True)
    stats = serializers.SerializerMethodField()
    is_banned = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 'phone',
            'is_active', 'is_staff', 'is_banned', 'ban_reason', 'banned_at',
            'group', 'group_id', 'stats', 'date_joined', 'last_login',
        ]

    def get_stats(self, obj):
        return obj.metadata.get('stats') or get_player_stats(obj)

    def get_is_banned(self, obj):
        return not obj.is_active and bool(obj.banned_at)


class AdminGroupMemberAddSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=False)
    username = serializers.CharField(required=False)
    password = serializers.CharField(required=False, write_only=True)

    def validate(self, attrs):
        user_id = attrs.get('user_id')
        username = attrs.get('username')
        password = attrs.get('password')

        if user_id:
            if not User.objects.filter(id=user_id).exists():
                raise serializers.ValidationError({'user_id': 'Пользователь не найден.'})
            return attrs

        if username and password:
            if User.objects.filter(username=username).exists():
                raise serializers.ValidationError({'username': 'Пользователь с таким логином уже существует.'})
            return attrs

        raise serializers.ValidationError('Укажите user_id или пару username/password.')


class AdminBanSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)
