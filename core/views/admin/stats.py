from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.auth.admin_access import IsActiveUser, IsAdminUser
from core.models.user import User
from core.models.user_bot import UserBot
from warship.models import GameSession
from warship.utils import build_leaderboard, get_bot_stats, get_player_stats


class AdminStatsOverviewAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def get(self, request):
        active_statuses = [
            GameSession.GameStatus.WAITING_CHALLENGE,
            GameSession.GameStatus.WAITING_SHIPS,
            GameSession.GameStatus.PLAYER1_TURN,
            GameSession.GameStatus.PLAYER2_TURN,
        ]
        active_games = GameSession.objects.filter(status__in=active_statuses)
        today = timezone.now().date()

        return Response({
            'active_games': active_games.count(),
            'active_player_vs_player': active_games.filter(
                player1_bot__isnull=True,
                player2_bot__isnull=True,
            ).count(),
            'active_with_bots': active_games.filter(
                Q(player1_bot__isnull=False) | Q(player2_bot__isnull=False)
            ).count(),
            'active_training': active_games.filter(is_training=True).count(),
            'active_ranked': active_games.filter(is_training=False).count(),
            'finished_today': GameSession.objects.filter(
                status=GameSession.GameStatus.FINISHED,
                finished_at__date=today,
            ).count(),
            'total_users': User.objects.count(),
            'total_bots': UserBot.objects.count(),
            'banned_users': User.objects.filter(is_active=False, banned_at__isnull=False).count(),
        })


class AdminStatsGamesByDayAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def get(self, request):
        days = int(request.query_params.get('days', 30))
        since = timezone.now() - timedelta(days=days - 1)

        finished = (
            GameSession.objects.filter(
                status=GameSession.GameStatus.FINISHED,
                finished_at__gte=since,
            )
            .annotate(day=TruncDate('finished_at'))
            .values('day', 'is_training')
            .annotate(count=Count('id'))
            .order_by('day')
        )

        by_day = {}
        for row in finished:
            day_str = row['day'].isoformat()
            if day_str not in by_day:
                by_day[day_str] = {'date': day_str, 'total': 0, 'ranked': 0, 'training': 0}
            by_day[day_str]['total'] += row['count']
            if row['is_training']:
                by_day[day_str]['training'] += row['count']
            else:
                by_day[day_str]['ranked'] += row['count']

        return Response(list(by_day.values()))


class AdminLeaderboardStudentsAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def get(self, request):
        queryset = User.objects.filter(is_staff=False).select_related('group')
        group_id = request.query_params.get('group_id')
        if group_id:
            queryset = queryset.filter(group_id=group_id)

        entries = []
        for user in queryset:
            stats = user.metadata.get('stats') or get_player_stats(user)
            entries.append({
                'user_id': user.id,
                'username': user.username,
                'group_id': user.group_id,
                'group_name': user.group.name if user.group_id else None,
                'stats': stats,
            })

        return Response(build_leaderboard(entries))


class AdminLeaderboardBotsAPIView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdminUser]

    def get(self, request):
        queryset = UserBot.objects.select_related('user', 'user__group')
        group_id = request.query_params.get('group_id')
        if group_id:
            queryset = queryset.filter(user__group_id=group_id)

        entries = []
        for bot in queryset:
            stats = bot.metadata.get('stats') or get_bot_stats(bot)
            entries.append({
                'bot_id': bot.id,
                'bot_name': bot.name,
                'owner_id': bot.user_id,
                'owner_username': bot.user.username,
                'group_id': bot.user.group_id,
                'group_name': bot.user.group.name if bot.user.group_id else None,
                'stats': stats,
            })

        return Response(build_leaderboard(entries))
