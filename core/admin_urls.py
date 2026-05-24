from django.urls import path

from core.views.admin.bots_games import (
    AdminActiveGamesAPIView,
    AdminBotChallengeAPIView,
    AdminBotListAPIView,
    AdminBotVersusAPIView,
    AdminCentrifugoTokenAPIView,
    AdminGameApproveMoveAPIView,
    AdminGameBoardAPIView,
    AdminGameControlAPIView,
    AdminGameDetailAPIView,
)
from core.views.admin.groups import (
    AdminGroupDetailAPIView,
    AdminGroupListCreateAPIView,
    AdminGroupMemberRemoveAPIView,
    AdminGroupMembersAPIView,
    AdminUserBanAPIView,
    AdminUserDetailAPIView,
    AdminUserListCreateAPIView,
    AdminUserUnbanAPIView,
)
from core.views.admin.stats import (
    AdminLeaderboardBotsAPIView,
    AdminLeaderboardStudentsAPIView,
    AdminStatsGamesByDayAPIView,
    AdminStatsOverviewAPIView,
)

urlpatterns = [
    path('groups/', AdminGroupListCreateAPIView.as_view(), name='admin-groups'),
    path('groups/<int:group_id>/', AdminGroupDetailAPIView.as_view(), name='admin-group-detail'),
    path('groups/<int:group_id>/members/', AdminGroupMembersAPIView.as_view(), name='admin-group-members'),
    path(
        'groups/<int:group_id>/members/<int:user_id>/',
        AdminGroupMemberRemoveAPIView.as_view(),
        name='admin-group-member-remove',
    ),
    path('users/', AdminUserListCreateAPIView.as_view(), name='admin-users'),
    path('users/<int:user_id>/', AdminUserDetailAPIView.as_view(), name='admin-user-detail'),
    path('users/<int:user_id>/ban/', AdminUserBanAPIView.as_view(), name='admin-user-ban'),
    path('users/<int:user_id>/unban/', AdminUserUnbanAPIView.as_view(), name='admin-user-unban'),
    path('stats/overview/', AdminStatsOverviewAPIView.as_view(), name='admin-stats-overview'),
    path('stats/games-by-day/', AdminStatsGamesByDayAPIView.as_view(), name='admin-stats-games-by-day'),
    path('leaderboard/students/', AdminLeaderboardStudentsAPIView.as_view(), name='admin-leaderboard-students'),
    path('leaderboard/bots/', AdminLeaderboardBotsAPIView.as_view(), name='admin-leaderboard-bots'),
    path('bots/', AdminBotListAPIView.as_view(), name='admin-bots'),
    path('bots/versus/', AdminBotVersusAPIView.as_view(), name='admin-bots-versus'),
    path('bots/<int:bot_id>/challenge/', AdminBotChallengeAPIView.as_view(), name='admin-bot-challenge'),
    path('games/active/', AdminActiveGamesAPIView.as_view(), name='admin-games-active'),
    path('games/<int:game_id>/', AdminGameDetailAPIView.as_view(), name='admin-game-detail'),
    path('games/<int:game_id>/board/', AdminGameBoardAPIView.as_view(), name='admin-game-board'),
    path('games/<int:game_id>/control/', AdminGameControlAPIView.as_view(), name='admin-game-control'),
    path('games/<int:game_id>/approve-move/', AdminGameApproveMoveAPIView.as_view(), name='admin-game-approve-move'),
    path('centrifugo/token/', AdminCentrifugoTokenAPIView.as_view(), name='admin-centrifugo-token'),
]
