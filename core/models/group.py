from django.db import models


class PlayerGroup(models.Model):
    """Учебная группа в рамках одного университета (инстанса)."""

    name = models.CharField(max_length=128, unique=True, verbose_name='Название')
    description = models.TextField(blank=True, default='', verbose_name='Описание')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')

    class Meta:
        verbose_name = 'Группа игроков'
        verbose_name_plural = 'Группы игроков'
        ordering = ['name']

    def __str__(self):
        return self.name
