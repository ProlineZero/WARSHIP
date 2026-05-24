import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.models.user_bot import UserBot

User = get_user_model()


class Command(BaseCommand):
    help = 'Создаёт пользователей и ботов для нагрузочного тестирования'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=200, help='Число пользователей')
        parser.add_argument('--password', type=str, default='loadtest123', help='Общий пароль')
        parser.add_argument('--prefix', type=str, default='loadtest', help='Префикс username')
        parser.add_argument(
            '--output',
            type=str,
            default='game_client/load_test/accounts.json',
            help='Путь к JSON с учётными данными',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Удалить существующих пользователей с prefix перед созданием',
        )

    def handle(self, *args, **options):
        count = options['count']
        password = options['password']
        prefix = options['prefix']
        output_path = Path(options['output'])
        force = options['force']

        if force:
            deleted_users, _ = User.objects.filter(username__startswith=f'{prefix}_').delete()
            self.stdout.write(f'Удалено связанных объектов: {deleted_users}')

        accounts = []
        created_users = 0
        created_bots = 0

        for index in range(count):
            username = f'{prefix}_{index}'
            bot_name = f'{prefix}_bot_{index}'

            user, user_created = User.objects.get_or_create(
                username=username,
                defaults={'is_active': True},
            )
            if user_created:
                user.set_password(password)
                user.save(update_fields=['password'])
                created_users += 1
            elif force or not user.check_password(password):
                user.set_password(password)
                user.save(update_fields=['password'])

            user_bot, bot_created = UserBot.objects.get_or_create(
                user=user,
                name=bot_name,
                defaults={'description': f'Load test bot #{index}'},
            )
            if bot_created:
                created_bots += 1

            accounts.append({
                'user_id': user.id,
                'username': user.username,
                'password': password,
                'bot_token': str(user_bot.token),
                'bot_name': user_bot.name,
            })

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(accounts, ensure_ascii=False, indent=2), encoding='utf-8')

        self.stdout.write(self.style.SUCCESS(
            f'Готово: {len(accounts)} аккаунтов '
            f'(новых users: {created_users}, новых bots: {created_bots}) -> {output_path}'
        ))
