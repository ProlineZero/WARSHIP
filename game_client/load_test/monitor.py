"""Live-монитор нагрузочного теста: метрики, графики RPS и активных игр, CPU/RAM."""
import threading
import tkinter as tk
from tkinter import ttk

import matplotlib

matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from load_test.resources import ResourceSampler
from load_test.stats import StatsCollector


class LiveMonitor:
    REFRESH_MS = 1000

    def __init__(self, stats: StatsCollector):
        self.stats = stats
        self.resources = ResourceSampler()
        self._root: tk.Tk | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._metric_labels: dict[str, ttk.Label] = {}
        self._canvas = None
        self._figure = None
        self._ax_rps = None
        self._ax_games = None
        self._ax_resources = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_ui, daemon=True)
        self._thread.start()

    def run_blocking(self) -> None:
        if self._running:
            return
        self._running = True
        self._run_ui()

    def stop(self) -> None:
        self._running = False
        if self._root:
            self._root.after(0, self._root.destroy)

    def _run_ui(self) -> None:
        self._root = tk.Tk()
        self._root.title('Warship Load Test — Live Monitor')
        self._root.geometry('1100x780')
        self._root.minsize(900, 650)
        self._build_ui()
        self._root.protocol('WM_DELETE_WINDOW', self._on_close)
        self._tick()
        self._root.mainloop()

    def _on_close(self) -> None:
        self._running = False
        if self._root:
            self._root.destroy()

    def _build_ui(self) -> None:
        assert self._root is not None
        main = ttk.Frame(self._root, padding=8)
        main.pack(fill='both', expand=True)

        metrics_frame = ttk.LabelFrame(main, text='Текущие показатели', padding=8)
        metrics_frame.pack(fill='x', pady=(0, 8))

        grid = ttk.Frame(metrics_frame)
        grid.pack(fill='x')

        fields = [
            ('active_games', 'Активные игры'),
            ('games_started', 'Игр начато'),
            ('games_finished', 'Игр завершено'),
            ('games_cancelled', 'Игр отменено'),
            ('http_requests', 'HTTP запросов'),
            ('rps', 'Запросов/сек'),
            ('http_errors', 'HTTP ошибок'),
            ('error_rate', 'Ошибок %'),
            ('latency_p50', 'Latency p50 ms'),
            ('latency_p95', 'Latency p95 ms'),
            ('latency_p99', 'Latency p99 ms'),
            ('players_prepared', 'Игроков готово'),
            ('players_in_game', 'Игроков в игре'),
            ('players_done', 'Игроков завершило'),
            ('ws_connections', 'WS подключений'),
            ('player_errors', 'Ошибок игроков'),
            ('cpu_percent', 'CPU процесса %'),
            ('memory_mb', 'RAM процесса MB'),
            ('sys_memory', 'RAM системы %'),
            ('elapsed', 'Время (сек)'),
        ]

        for index, (key, title) in enumerate(fields):
            row, col = divmod(index, 4)
            cell = ttk.Frame(grid, padding=4)
            cell.grid(row=row, column=col, sticky='w', padx=4, pady=2)
            ttk.Label(cell, text=title, foreground='gray').pack(anchor='w')
            value_label = ttk.Label(cell, text='—', font=('Segoe UI', 11, 'bold'))
            value_label.pack(anchor='w')
            self._metric_labels[key] = value_label

        charts_frame = ttk.LabelFrame(main, text='Графики', padding=4)
        charts_frame.pack(fill='both', expand=True)

        self._figure = Figure(figsize=(10, 6), dpi=100)
        self._ax_rps = self._figure.add_subplot(3, 1, 1)
        self._ax_games = self._figure.add_subplot(3, 1, 2)
        self._ax_resources = self._figure.add_subplot(3, 1, 3)
        self._figure.tight_layout(pad=2.0)

        self._canvas = FigureCanvasTkAgg(self._figure, master=charts_frame)
        self._canvas.get_tk_widget().pack(fill='both', expand=True)

    def _tick(self) -> None:
        if not self._running or not self._root:
            return

        cpu, memory_mb = self.resources.sample()
        sys_mem = ResourceSampler.system_memory_percent()
        self.stats.sample(cpu_percent=cpu, memory_mb=memory_mb)
        metrics = self.stats.get_live_metrics(cpu_percent=cpu, memory_mb=memory_mb)

        display = {
            'active_games': f'{metrics["active_games"]}',
            'games_started': f'{metrics["games_started"]}',
            'games_finished': f'{metrics["games_finished"]}',
            'games_cancelled': f'{metrics["games_cancelled"]}',
            'http_requests': f'{metrics["http_requests"]}',
            'rps': f'{metrics["rps"]:.1f}',
            'http_errors': f'{metrics["http_errors"]}',
            'error_rate': f'{metrics["error_rate"]:.2f}',
            'latency_p50': f'{metrics["latency_p50"]:.0f}',
            'latency_p95': f'{metrics["latency_p95"]:.0f}',
            'latency_p99': f'{metrics["latency_p99"]:.0f}',
            'players_prepared': f'{metrics["players_prepared"]}/{metrics["total_players"]}',
            'players_in_game': f'{metrics["players_in_game"]}',
            'players_done': f'{metrics["players_done"]}',
            'ws_connections': f'{metrics["ws_connections"]}',
            'player_errors': f'{metrics["player_errors"]}',
            'cpu_percent': f'{metrics["cpu_percent"]:.1f}',
            'memory_mb': f'{metrics["memory_mb"]:.0f}',
            'sys_memory': f'{sys_mem:.1f}',
            'elapsed': f'{metrics["elapsed"]:.0f}',
        }
        for key, text in display.items():
            if key in self._metric_labels:
                self._metric_labels[key].config(text=text)

        self._update_charts()
        self._root.after(self.REFRESH_MS, self._tick)

    def _update_charts(self) -> None:
        history = self.stats.get_history()
        if not history:
            return

        times = [point.timestamp for point in history]
        rps = [point.rps for point in history]
        active = [point.active_games for point in history]
        cpu = [point.cpu_percent for point in history]
        mem = [point.memory_mb for point in history]
        cumulative_requests = [point.http_requests for point in history]

        self._ax_rps.clear()
        self._ax_rps.plot(times, rps, color='#2563eb', label='RPS (instant)')
        self._ax_rps.set_ylabel('req/s')
        self._ax_rps.set_title('HTTP запросы в секунду')
        self._ax_rps.grid(True, alpha=0.3)
        self._ax_rps.legend(loc='upper left')

        ax_req = self._ax_rps.twinx()
        ax_req.plot(times, cumulative_requests, color='#94a3b8', alpha=0.7, label='Всего запросов')
        ax_req.set_ylabel('total')
        ax_req.legend(loc='upper right')

        self._ax_games.clear()
        self._ax_games.plot(times, active, color='#16a34a', label='Активные игры')
        self._ax_games.set_ylabel('игры')
        self._ax_games.set_title('Активные игры')
        self._ax_games.grid(True, alpha=0.3)
        self._ax_games.legend(loc='upper left')

        self._ax_resources.clear()
        self._ax_resources.plot(times, cpu, color='#dc2626', label='CPU %')
        self._ax_resources.set_ylabel('CPU %')
        self._ax_resources.set_xlabel('секунды')
        self._ax_resources.grid(True, alpha=0.3)

        ax_mem = self._ax_resources.twinx()
        ax_mem.plot(times, mem, color='#9333ea', label='RAM MB')
        ax_mem.set_ylabel('MB')
        self._ax_resources.set_title('Ресурсы процесса нагрузочного клиента')

        lines1, labels1 = self._ax_resources.get_legend_handles_labels()
        lines2, labels2 = ax_mem.get_legend_handles_labels()
        self._ax_resources.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

        self._figure.tight_layout(pad=2.0)
        self._canvas.draw_idle()
