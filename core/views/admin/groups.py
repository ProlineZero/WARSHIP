from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.auth.admin_access import IsActiveUser, IsAdminUser
from core.models.group import PlayerGroup
from core.models.user import User
from core.serializers.admin.users import (
    AdminBanSerializer,
    AdminGroupMemberAddSerializer,
    AdminUserCreateSerializer,
    AdminUserSerializer,
    AdminUserUpdateSerializer,
    PlayerGroupSerializer,
)
from warship.utils import get_player_stats


class AdminGroupListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def get(self, request):
        groups = PlayerGroup.objects.all()
        return Response(PlayerGroupSerializer(groups, many=True).data)

    def post(self, request):
        serializer = PlayerGroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group = serializer.save()
        return Response(PlayerGroupSerializer(group).data, status=status.HTTP_201_CREATED)


class AdminGroupDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def _get_group(self, group_id):
        group = PlayerGroup.objects.filter(id=group_id).first()
        if not group:
            raise NotFound(detail='Группа не найдена.')
        return group

    def get(self, request, group_id):
        return Response(PlayerGroupSerializer(self._get_group(group_id)).data)

    def put(self, request, group_id):
        group = self._get_group(group_id)
        serializer = PlayerGroupSerializer(group, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, group_id):
        group = self._get_group(group_id)
        User.objects.filter(group=group).update(group=None)
        group.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminGroupMembersAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def get(self, request, group_id):
        if not PlayerGroup.objects.filter(id=group_id).exists():
            raise NotFound(detail='Группа не найдена.')
        members = User.objects.filter(group_id=group_id).select_related('group')
        return Response(AdminUserSerializer(members, many=True).data)

    def post(self, request, group_id):
        if not PlayerGroup.objects.filter(id=group_id).exists():
            raise NotFound(detail='Группа не найдена.')

        serializer = AdminGroupMemberAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data.get('user_id'):
            user = User.objects.get(id=data['user_id'])
        else:
            user = User.objects.create(username=data['username'])
            user.set_password(data['password'])
            user.save()

        user.group_id = group_id
        user.save(update_fields=['group'])
        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)


class AdminGroupMemberRemoveAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def delete(self, request, group_id, user_id):
        user = User.objects.filter(id=user_id, group_id=group_id).first()
        if not user:
            raise NotFound(detail='Участник группы не найден.')
        user.group = None
        user.save(update_fields=['group'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def get(self, request):
        queryset = User.objects.select_related('group', 'banned_by').all()

        group_id = request.query_params.get('group_id')
        if group_id:
            queryset = queryset.filter(group_id=group_id)

        is_active = request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() in ('1', 'true', 'yes'))

        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) | Q(first_name__icontains=search) | Q(last_name__icontains=search)
            )

        return Response(AdminUserSerializer(queryset, many=True).data)

    def post(self, request):
        serializer = AdminUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)


class AdminUserDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def _get_user(self, user_id):
        user = User.objects.select_related('group').filter(id=user_id).first()
        if not user:
            raise NotFound(detail='Пользователь не найден.')
        return user

    def get(self, request, user_id):
        return Response(AdminUserSerializer(self._get_user(user_id)).data)

    def put(self, request, user_id):
        user = self._get_user(user_id)
        serializer = AdminUserUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(AdminUserSerializer(user).data)


class AdminUserBanAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def post(self, request, user_id):
        user = User.objects.filter(id=user_id).first()
        if not user:
            raise NotFound(detail='Пользователь не найден.')
        if user.id == request.user.id:
            return Response({'error': 'Нельзя забанить самого себя.'}, status=400)

        serializer = AdminBanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user.is_active = False
        user.ban_reason = serializer.validated_data['reason']
        user.banned_at = timezone.now()
        user.banned_by = request.user
        user.save(update_fields=['is_active', 'ban_reason', 'banned_at', 'banned_by'])

        return Response(AdminUserSerializer(user).data)


class AdminUserUnbanAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def post(self, request, user_id):
        user = User.objects.filter(id=user_id).first()
        if not user:
            raise NotFound(detail='Пользователь не найден.')

        user.is_active = True
        user.ban_reason = ''
        user.banned_at = None
        user.banned_by = None
        user.save(update_fields=['is_active', 'ban_reason', 'banned_at', 'banned_by'])

        return Response(AdminUserSerializer(user).data)
