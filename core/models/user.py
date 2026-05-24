import requests
import re
import random
import string
from datetime import timedelta

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.forms import ValidationError
from django.conf import settings
from django.utils import timezone

from core.common import get_logger

class OTPVerifier:
    call_url = "https://restapi.plusofon.ru/api/v1/flash-call"
    username = 'loyalitycard'
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Client': '10553',  # КОНСТАНТА ДЛЯ ВСЕХ ЗАПРОСОВ
        'Authorization': f'Bearer {settings.PLUSOFON_TOKEN}'  # Теперь подставляется реальный токен
    }
        
    @classmethod
    def send_call(cls, phone):
        payload = {
            "phone": phone
        }
        response = requests.request('POST', f"{cls.call_url}/send", headers=cls.headers, json=payload).json()
        print(response)
        return response.get('success', False), response
        

class User(AbstractUser):
    phone = models.CharField("Телефон", max_length=12, unique=True, null=True)
    tmp_phone = models.CharField("Не проверенный телефон", max_length=12, null=True)

    otp_code = models.CharField(max_length=6, null=True, blank=True)
    otp_expiry = models.DateTimeField(null=True, blank=True)

    metadata = models.JSONField(default=dict, blank=True)

    group = models.ForeignKey(
        'core.PlayerGroup',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='members',
        verbose_name='Группа',
    )
    ban_reason = models.TextField(blank=True, default='', verbose_name='Причина бана')
    banned_at = models.DateTimeField(null=True, blank=True, verbose_name='Забанен')
    banned_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='banned_users',
        verbose_name='Забанил',
    )

    @staticmethod
    def _parse_phone_number(phone_str: str) -> (str):
        """
        Парсит мобильный номер российского оператора в любом формате.
        Возвращает нормализованный номер в формате +7xxxxxxxxxx или ошибку.
        """
        # Удаляем все символы кроме цифр и +, заменяем пробелы, тире, скобки и т.д.
        cleaned = re.sub(r'[^\d+]', '', phone_str)
        
        # Если начинается с 8, заменяем на 7
        if cleaned.startswith('8'):
            cleaned = '7' + cleaned[1:]
        
        # Добавляем + если нет
        if not cleaned.startswith('+'):
            cleaned = '+' + cleaned
        
        # Проверяем формат: +7 и ровно 10 цифр после (всего 11 цифр)
        if re.match(r'^\+7\d{10}$', cleaned):
            return cleaned
        else:
            raise ValidationError("Неверный формат номера. Используйте: +79991234567")


    @classmethod
    def check_phone_exists(cls, phone):
        return cls.objects.filter(phone=phone).exists()

    def generate_otp(self):
        """Генерирует 6-значный OTP-код и устанавливает срок действия (5 минут)."""
        self.otp_code = ''.join(random.choices(string.digits, k=6))
        self.otp_expiry = timezone.localtime() + timedelta(minutes=5)
        self.save()
        return self.otp_code


    def verify_otp(self, code: str) -> (bool):
        """Проверяет OTP-код и его срок действия."""
        if self.otp_code and self.otp_expiry:
            if timezone.localtime() <= self.otp_expiry and self.otp_code == code:
                self.otp_code = None
                self.otp_expiry = None
                if self.tmp_phone:
                    phone_taken = (
                        self.__class__.objects
                        .filter(phone=self.tmp_phone)
                        .exclude(pk=self.pk)
                        .exists()
                    )
                    if phone_taken:
                        raise ValidationError("Пользователь с таким номером телефона уже существует.")

                    self.phone = self.tmp_phone

                self.tmp_phone = None
                self.save(update_fields=["phone", "tmp_phone", "otp_code", "otp_expiry"])
                return True
        return False

    def bind_phone(self, phone: str, code: str = None) -> (str):
        """
        Привязывает номер телефона. Если код не передан, генерирует OTP и отправляет его через SMS.
        Если код передан, проверяет его и привязывает номер.
        """
        logger = get_logger("user_phone_binding")
        if not code:
            try:
                phone = self._parse_phone_number(phone)
            except ValidationError as exc:
                return str(exc)
            print(phone)
            
            
            try:
                success_call, resp = OTPVerifier.send_call(phone)
                if not success_call:
                    return "Ошибка при отправке звонка. Попробуйте позже."
                
                self.tmp_phone = phone
                otp = resp["data"]["pin"]
                self.otp_code = otp
                self.otp_expiry = timezone.localtime() + timedelta(minutes=3)
                self.save()
                return "На ваш номер поступит звонок. Введите последние 4 цифры номера."
            except Exception as e:
                logger.error(f"SMS error: {e}")
                return "Ошибка при отправке звонка. Попробуйте позже."
        else:
            if self.verify_otp(code):
                self.phone = self.tmp_phone
                self.tmp_phone = None
                self.save()
                return True, "Номер успешно привязан!"
            return False, "Неверный или просроченный код."