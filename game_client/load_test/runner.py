"""
Нагрузочный тест: сотни одновременных игр через bot-токены.

Подготовка:
  python manage.py seed_load_test_users --count 200 --output game_client/load_test/accounts.json

Запуск:
  python run_load_test.py --accounts load_test/accounts.json --players 200
"""
import argparse
import asyncio
import json
import logging
import re
import sys
import threading
from pathlib import Path

from config import API_BASE_URL, CENTRIFUGO_WS_URL
from load_test.monitor import LiveMonitor
from load_test.player import AsyncPlayer, _short_error
from load_test.stats import StatsCollector

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def load_accounts(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, list):
        raise ValueError('accounts.json должен содержать список аккаунтов')
    return data


async def run_load_test(
    accounts: list[dict],
    players: int,
    api_url: str,
    ws_url: str,
    ramp_up: float,
    timeout: float,
    report_interval: float,
    use_ws: bool,
    turn_delay: float,
    poll_interval: float,
    login_concurrency: int,
    login_retries: int,
    stats: StatsCollector | None = None,
) -> StatsCollector:
    if players % 2 != 0:
        raise ValueError('--players должно быть чётным (игра = 2 игрока)')
    if players > len(accounts):
        raise ValueError(f'Недостаточно аккаунтов: нужно {players}, в файле {len(accounts)}')

    selected = accounts[:players]
    if stats is None:
        stats = StatsCollector()
    stats.set_total_players(players)

    barrier = asyncio.Event()
    players_list: list[AsyncPlayer] = []

    for account in selected:
        player = AsyncPlayer(
            account,
            api_url,
            ws_url,
            stats,
            use_ws=use_ws,
            turn_delay=turn_delay,
            poll_interval=poll_interval,
        )
        player.set_barrier(barrier)
        players_list.append(player)

    delay_step = ramp_up / max(players - 1, 1)
    login_semaphore = asyncio.Semaphore(login_concurrency)

    async def prepare_player(player: AsyncPlayer, delay: float) -> None:
        if delay > 0:
            await asyncio.sleep(delay)
        async with login_semaphore:
            try:
                await player.prepare(retries=login_retries)
                stats.record_player_prepared()
            except Exception as exc:
                stats.record_player_error()
                logger.warning('Prepare failed %s: %s', player.account.get('username'), _short_error(exc))

    prepare_tasks = [
        asyncio.create_task(prepare_player(player, index * delay_step))
        for index, player in enumerate(players_list)
    ]
    await asyncio.gather(*prepare_tasks, return_exceptions=True)
    logger.info('All players prepared (%s), releasing matchmaking barrier', len(players_list))
    barrier.set()

    async def reporter() -> None:
        while True:
            await asyncio.sleep(report_interval)
            logger.info('\n--- Progress ---\n%s', stats.snapshot(players))

    report_task = asyncio.create_task(reporter())

    async def play_player(player: AsyncPlayer) -> None:
        try:
            game_id = await player.matchmaking()
            if not game_id:
                logger.warning('Player %s: game not found', player.account.get('username'))
                return
            stats.record_player_in_game()
            await player.place_ships_if_needed()
            await player.play_until_finished(timeout)
        except Exception as exc:
            stats.record_player_error()
            logger.warning('Player %s error: %s', player.account.get('username'), _short_error(exc))
        finally:
            stats.record_player_done()
            await player.cleanup()

    play_tasks = [asyncio.create_task(play_player(player)) for player in players_list]
    await asyncio.gather(*play_tasks, return_exceptions=True)
    report_task.cancel()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description='Warship load test client')
    parser.add_argument('--accounts', type=str, default='load_test/accounts.json')
    parser.add_argument('--players', type=int, default=200)
    parser.add_argument('--api-url', type=str, default=API_BASE_URL)
    parser.add_argument('--ws-url', type=str, default=CENTRIFUGO_WS_URL)
    parser.add_argument('--ramp-up', type=float, default=30.0, help='Секунды на постепенный логин (не влияет на скорость ходов)')
    parser.add_argument('--timeout', type=float, default=600.0, help='Таймаут одной игры (сек)')
    parser.add_argument('--report-interval', type=float, default=5.0)
    parser.add_argument('--turn-delay', type=float, default=0.0, help='Пауза между своими ходами (сек)')
    parser.add_argument('--poll-interval', type=float, default=0.01, help='Интервал ожидания WS-события (сек)')
    parser.add_argument('--login-concurrency', type=int, default=25, help='Макс. одновременных логинов')
    parser.add_argument('--login-retries', type=int, default=5, help='Повторы логина при 5xx')
    parser.add_argument('--turbo', action='store_true', help='Максимальная скорость ходов (turn-delay=0, poll=0)')
    parser.add_argument('--no-ws', action='store_true', help='Без Centrifugo WebSocket')
    parser.add_argument('--no-monitor', action='store_true', help='Без live-монитора')
    args = parser.parse_args()

    if args.turbo:
        args.turn_delay = 0.0
        args.poll_interval = 0.0

    accounts_path = Path(args.accounts)
    if not accounts_path.is_file():
        logger.error('Файл аккаунтов не найден: %s', accounts_path)
        logger.error('Создайте: python manage.py seed_load_test_users --count %s --output %s', args.players, accounts_path)
        return 1

    accounts = load_accounts(accounts_path)
    logger.info('Loaded %s accounts, starting %s players', len(accounts), args.players)

    stats = StatsCollector()
    stats.set_total_players(args.players)
    result: dict = {}

    def run_async_test() -> None:
        result['stats'] = asyncio.run(
            run_load_test(
                accounts=accounts,
                players=args.players,
                api_url=args.api_url,
                ws_url=args.ws_url,
                ramp_up=args.ramp_up,
                timeout=args.timeout,
                report_interval=args.report_interval,
                use_ws=not args.no_ws,
                turn_delay=args.turn_delay,
                poll_interval=args.poll_interval,
                login_concurrency=args.login_concurrency,
                login_retries=args.login_retries,
                stats=stats,
            )
        )

    test_thread = threading.Thread(target=run_async_test, daemon=True)
    test_thread.start()

    if not args.no_monitor:
        monitor = LiveMonitor(stats)
        monitor.run_blocking()
    else:
        test_thread.join()

    test_thread.join(timeout=2)
    final_stats = result.get('stats', stats)

    print('\n=== Final Report ===')
    print(final_stats.snapshot(args.players))
    return 0


if __name__ == '__main__':
    sys.exit(main())
