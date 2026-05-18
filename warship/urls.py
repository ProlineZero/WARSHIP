from django.urls import path
from warship import views
from warship.centrifugo_proxy import CentrifugoSubscribeProxyView, CentrifugoSubRefreshProxyView

urlpatterns = [
    # Matchmaking
    path('matchmaking/find/', views.MatchmakingFindAPIView.as_view(), name='matchmaking-find'),
    path('matchmaking/cancel/', views.MatchmakingCancelAPIView.as_view(), name='matchmaking-cancel'),
    
    # Game actions
    path('game/<int:game_id>/status/', views.GameStatusAPIView.as_view(), name='game-status'),
    path('game/<int:game_id>/board/', views.GameBoardAPIView.as_view(), name='game-board'),
    path('game/<int:game_id>/place_ships/', views.GamePlaceShipsAPIView.as_view(), name='game-place-ships'),
    path('game/<int:game_id>/make_shot/', views.GameMakeShotAPIView.as_view(), name='game-make-shot'),
    path('game/<int:game_id>/leave/', views.GameLeaveAPIView.as_view(), name='game-leave'),
    
    # Centrifugo connection token
    path('centrifugo/token/', views.CentrifugoTokenAPIView.as_view(), name='centrifugo-token'),
    path(
        'centrifugo/proxy/subscribe/',
        CentrifugoSubscribeProxyView.as_view(),
        name='centrifugo-proxy-subscribe',
    ),
    path(
        'centrifugo/proxy/sub_refresh/',
        CentrifugoSubRefreshProxyView.as_view(),
        name='centrifugo-proxy-sub-refresh',
    ),
]
