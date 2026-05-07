
import json
import logging
import os

from django.utils.translation import gettext_lazy as _

from config.settings import BASE_LOG_DIR




def get_logger(
    file_name, sub_directory="", 
    level=logging.INFO, 
    use_rotation=False, 
    max_bytes=10 * 1024 * 1024, 
    backup_count=5,
    clear=False,
    log_num=0):
    """
    Создает или возвращает logger с указанным именем.
    
    :param file_name: Имя файла лога.
    :param sub_directory: Подкаталог для логов.
    :param level: Уровень логирования (default: logging.INFO).
    :param use_rotation: Использовать ротацию логов (default: False).
    :param max_bytes: Максимальный размер файла для ротации (default: 10 MB).
    :param backup_count: Количество резервных копий при ротации (default: 5).
    :param clear: Очищать ли файл перед логированием (default: False).
    :param log_num: Дополнительное числовое значение, которое записывается в лог (default: 0).
    
    :return: Настроенный logger.
    """
    from concurrent_log_handler import ConcurrentRotatingFileHandler
    class MyRotatingFileHandler(ConcurrentRotatingFileHandler):
        def doRollover(self):
            # Вызовем стандартный метод doRollover для выполнения ротации
            super().doRollover()
            
            # Установим права доступа к основному файлу
            os.chmod(self.baseFilename, 0o664)  # Устанавливаем права на чтение и запись для владельца и группы
    
    class JsonFormatter(logging.Formatter):
        def __init__(self, log_num, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.log_num = log_num

        def format(self, record):
            log_record = {
                "time": self.formatTime(record, self.datefmt),
                "level": record.levelname,
                "log_num": getattr(self, "log_num", None),
                "message": record.getMessage(),
                "name": record.name,
                "pathname": record.pathname,
                "lineno": record.lineno,
            }

            if record.exc_info:
                log_record["exception"] = self.formatException(record.exc_info)

            try:
                # Добавляем любые дополнительные аргументы из record.__dict__
                for key, value in record.__dict__.items():
                    if key not in log_record and key.startswith('_'):
                        log_record[key[1:]] = value


                return json.dumps(log_record, ensure_ascii=False)
            except (TypeError, ValueError, Exception) as e:
                log_record_info = {key: type(value) for key,value in record.__dict__.items()}
                return json.dumps({"error": "Failed to serialize log", "exception": str(e), "log_record_info": log_record_info}, ensure_ascii=False)
        

    logger = logging.getLogger(file_name)
    logger.setLevel(level)


    if sub_directory:
        log_dir = os.path.join(BASE_LOG_DIR, sub_directory)
    else:
        log_dir = BASE_LOG_DIR

    os.makedirs(log_dir, exist_ok=True)

    log_file_path = os.path.join(log_dir, f"{file_name}.log")

    
    if clear:
        with open(log_file_path, 'w') as f:
            pass
        os.chmod(log_file_path, 0o664)  # Устанавливаем права на чтение и запись для владельца и группы
    
    logger.handlers.clear()
    
    if use_rotation:
        handler = MyRotatingFileHandler(log_file_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
    else:
        handler = logging.FileHandler(log_file_path, encoding="utf-8")

    formatter = JsonFormatter(log_num)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    

    return logger