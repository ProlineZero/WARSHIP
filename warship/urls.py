from django.urls import path
from warship import views

urlpatterns = [
    # Matchmaking
    path('matchmaking/find/', views.MatchmakingFindAPIView.as_view(), name='matchmaking-find'),
    path('matchmaking/cancel/', views.MatchmakingCancelAPIView.as_view(), name='matchmaking-cancel'),
    
    # Game actions
    path('game/<int:game_id>/status/', views.GameStatusAPIView.as_view(), name='game-status'),
    path('game/<int:game_id>/board/', views.GameBoardAPIView.as_view(), name='game-board'),
    path('game/<int:game_id>/place_ships/', views.GamePlaceShipsAPIView.as_view(), name='game-place-ships'),
    path('game/<int:game_id>/make_shot/', views.GameMakeShotAPIView.as_view(), name='game-make-shot'),
    
    # Centrifugo connection token
    path('centrifugo/token/', views.CentrifugoTokenAPIView.as_view(), name='centrifugo-token'),
]
