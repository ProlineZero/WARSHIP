from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from warship.game_presence import cancel_game_if_abandoned, finalize_game_cancellation, is_player_online
from warship.models import GameSession


class Command(BaseCommand):
    help = 'Отменяет зависшие игры: оба офлайн или слишком долго без активности'

    def handle(self, *args, **options):
        stale_timeout = int(getattr(settings, 'GAME_STALE_TIMEOUT_SECONDS', 7200))
        cutoff = timezone.now() - timedelta(seconds=stale_timeout)

        active_games = GameSession.objects.filter(
            player2__isnull=False,
        ).exclude(
            status__in=[
                GameSession.GameStatus.FINISHED,
                GameSession.GameStatus.CANCELLED,
            ],
        ).select_related('player1', 'player2')

        cancelled_abandoned = 0
        cancelled_stale = 0

        for game_session in active_games:
            if cancel_game_if_abandoned(game_session):
                cancelled_abandoned += 1
                continue

            if game_session.started_at >= cutoff:
                continue

            if is_player_online(game_session.id, game_session.player1_id):
                continue
            if is_player_online(game_session.id, game_session.player2_id):
                continue

            if finalize_game_cancellation(game_session, reason='таймаут неактивности'):
                cancelled_stale += 1
                self.stdout.write(f'Отменена устаревшая игра #{game_session.id}')

        self.stdout.write(
            self.style.SUCCESS(
                f'Готово: abandoned={cancelled_abandoned}, stale={cancelled_stale}'
            )
        )
