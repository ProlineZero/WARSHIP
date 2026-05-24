import os

try:
    import psutil
except ImportError:
    psutil = None


class ResourceSampler:
    def __init__(self):
        self._process = psutil.Process(os.getpid()) if psutil else None
        if self._process:
            self._process.cpu_percent(interval=None)

    def sample(self) -> tuple[float, float]:
        if not self._process:
            return 0.0, 0.0
        cpu = self._process.cpu_percent(interval=None)
        memory_mb = self._process.memory_info().rss / (1024 * 1024)
        return cpu, memory_mb

    @staticmethod
    def system_memory_percent() -> float:
        if not psutil:
            return 0.0
        return psutil.virtual_memory().percent
