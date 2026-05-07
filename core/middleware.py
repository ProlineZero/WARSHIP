"""
Кастомный middleware для обработки CORS в ASGI контексте.
"""
from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin


class CorsMiddleware(MiddlewareMixin):
    """
    Middleware для обработки CORS preflight запросов (OPTIONS).
    Работает корректно в ASGI контексте.
    """
    
    def process_request(self, request):
        """
        Обрабатывает OPTIONS запросы для CORS preflight.
        """
        if request.method == 'OPTIONS':
            response = HttpResponse()
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, ngrok-skip-browser-warning'
            response['Access-Control-Max-Age'] = '86400'
            response['Access-Control-Allow-Credentials'] = 'true'
            return response
        return None
    
    def process_response(self, request, response):
        """
        Добавляет CORS заголовки ко всем ответам.
        """
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, ngrok-skip-browser-warning'
        response['Access-Control-Allow-Credentials'] = 'true'
        return response
