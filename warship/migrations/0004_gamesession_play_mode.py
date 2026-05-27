from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warship', '0003_gamesession_admin_control_mode_gamesession_is_paused_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='gamesession',
            name='play_mode',
            field=models.CharField(
                choices=[('server', 'Серверные ходы'), ('peer', 'Ходы через Centrifugo')],
                default='server',
                max_length=20,
                verbose_name='Режим игры',
            ),
        ),
    ]
