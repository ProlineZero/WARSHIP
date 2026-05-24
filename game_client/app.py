"""
Графический клиент «Морской бой» (tkinter).
Запуск: python app.py
"""
import json
import threading
import tkinter as tk
from functools import partial
from tkinter import messagebox, scrolledtext, ttk

from api_client import ApiError, WarshipApiClient
from config import API_BASE_URL, BOARD_SIZE, CENTRIFUGO_WS_URL
from realtime import RealtimeClient
from ships import generate_random_fleet

CELL = 28
COLOR_WATER = '#b3d9ff'
COLOR_SHIP = '#6b7280'
COLOR_HIT = '#ef4444'
COLOR_MISS = '#e5e7eb'
COLOR_SUNK = '#7f1d1d'
COLOR_PENDING = '#fbbf24'


class BoardCanvas(tk.Canvas):
    def __init__(self, master, title: str, on_click=None, **kwargs):
        super().__init__(
            master,
            width=BOARD_SIZE * CELL + 2,
            height=BOARD_SIZE * CELL + 2,
            bg=COLOR_WATER,
            highlightthickness=1,
            **kwargs,
        )
        self.title = title
        self.on_cell_click = on_click
        self._cells: dict[tuple[int, int], int] = {}
        self.bind('<Button-1>', self._handle_click)

    def _handle_click(self, event):
        if not self.on_cell_click:
            return
        col = (event.x - 1) // CELL
        row = (event.y - 1) // CELL
        if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE:
            self.on_cell_click(row, col)

    def redraw(
        self,
        ships: list | None = None,
        shots: list | None = None,
        show_ships: bool = True,
        clickable: bool = False,
    ) -> None:
        self.delete('all')
        self._cells.clear()
        ship_cells = set()
        if ships and show_ships:
            for ship in ships:
                for row, col in ship.get('cells', []):
                    ship_cells.add((row, col))

        shot_map = {}
        if shots:
            for shot in shots:
                shot_map[(shot['row'], shot['col'])] = shot

        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                x1, y1 = col * CELL + 1, row * CELL + 1
                x2, y2 = x1 + CELL - 1, y1 + CELL - 1
                key = (row, col)
                fill = COLOR_WATER
                if key in ship_cells and show_ships:
                    fill = COLOR_SHIP
                if key in shot_map:
                    s = shot_map[key]
                    if s.get('hit'):
                        fill = COLOR_SUNK if s.get('ship_destroyed') else COLOR_HIT
                    else:
                        fill = COLOR_MISS
                rect = self.create_rectangle(x1, y1, x2, y2, fill=fill, outline='#94a3b8')
                self._cells[key] = rect

        if clickable:
            self.config(cursor='crosshair')
        else:
            self.config(cursor='')


class WarshipClientApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Warship — клиент')
        self.root.geometry('980x720')
        self.root.minsize(800, 600)

        self.api = WarshipApiClient()
        self.realtime: RealtimeClient | None = None
        self.game_id: int | None = None
        self.game_status: str | None = None
        self.current_turn_id: int | None = None
        self.ships_placed = False
        self._searching = False
        self._refresh_timer: str | None = None

        self._build_auth()
        self._show_login()

    def _build_auth(self):
        self.login_frame = ttk.Frame(self.root, padding=16)
        ttk.Label(self.login_frame, text='Warship', font=('Segoe UI', 16, 'bold')).pack(anchor='w')

        settings = ttk.Frame(self.login_frame)
        settings.pack(fill='x', pady=(8, 4))
        self.api_url_var = tk.StringVar(value=API_BASE_URL)
        self.ws_url_var = tk.StringVar(value=CENTRIFUGO_WS_URL)
        self._add_field(settings, 'API URL', self.api_url_var)
        self._add_field(settings, 'Centrifugo WS', self.ws_url_var)

        notebook = ttk.Notebook(self.login_frame)
        notebook.pack(fill='both', expand=True, pady=8)

        login_tab = ttk.Frame(notebook, padding=8)
        register_tab = ttk.Frame(notebook, padding=8)
        notebook.add(login_tab, text='Вход')
        notebook.add(register_tab, text='Регистрация')

        self.login_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self._add_field(login_tab, 'Логин (username / телефон)', self.login_var)
        self._add_field(login_tab, 'Пароль', self.password_var, show='*')
        self.login_status = ttk.Label(login_tab, text='')
        self.login_status.pack(anchor='w', pady=4)
        ttk.Button(login_tab, text='Войти', command=self._do_login).pack(anchor='w')

        self.register_phone_var = tk.StringVar()
        self.register_code_var = tk.StringVar()
        self.register_password_var = tk.StringVar()
        self._add_field(register_tab, 'Телефон (+7...)', self.register_phone_var)
        ttk.Button(register_tab, text='Получить SMS-код', command=self._do_request_otp).pack(anchor='w', pady=4)
        self._add_field(register_tab, 'Код из SMS', self.register_code_var)
        self._add_field(register_tab, 'Пароль (мин. 6 символов)', self.register_password_var, show='*')
        self.register_status = ttk.Label(register_tab, text='')
        self.register_status.pack(anchor='w', pady=4)
        ttk.Button(register_tab, text='Зарегистрироваться', command=self._do_register).pack(anchor='w')
        ttk.Label(
            register_tab,
            text='После регистрации входите тем же телефоном и паролем.',
            foreground='gray',
        ).pack(anchor='w', pady=(8, 0))

        bot_tab = ttk.Frame(notebook, padding=8)
        notebook.add(bot_tab, text='Бот')
        self.bot_token_var = tk.StringVar()
        self._add_field(bot_tab, 'Токен бота (UUID)', self.bot_token_var)
        self.bot_login_status = ttk.Label(bot_tab, text='')
        self.bot_login_status.pack(anchor='w', pady=4)
        ttk.Button(bot_tab, text='Войти как бот', command=self._do_bot_login).pack(anchor='w')

    def _add_field(self, parent, label, variable, show=None):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=4)
        ttk.Label(row, text=label, width=28).pack(side='left')
        ttk.Entry(row, textvariable=variable, show=show).pack(side='left', fill='x', expand=True)

    def _build_lobby(self):
        self.lobby_frame = ttk.Frame(self.root, padding=12)
        top = ttk.Frame(self.lobby_frame)
        top.pack(fill='x')
        self.user_label = ttk.Label(top, text='', font=('Segoe UI', 12, 'bold'))
        self.user_label.pack(side='left')
        ttk.Button(top, text='Выйти', command=self._logout).pack(side='right')

        self.lobby_notebook = ttk.Notebook(self.lobby_frame)
        self.lobby_notebook.pack(fill='both', expand=True, pady=8)

        game_tab = ttk.Frame(self.lobby_notebook, padding=4)
        self.lobby_notebook.add(game_tab, text='Игра')

        actions = ttk.LabelFrame(game_tab, text='Действия', padding=8)
        actions.pack(fill='x', pady=4)

        mm = ttk.Frame(actions)
        mm.pack(fill='x', pady=4)
        ttk.Button(mm, text='Найти игру (матчмейкинг)', command=self._matchmaking_find).pack(side='left', padx=4)
        ttk.Button(mm, text='Отменить поиск', command=self._matchmaking_cancel).pack(side='left', padx=4)
        self.training_match_var = tk.BooleanVar(value=True)
        self.training_check = ttk.Checkbutton(
            mm, text='Тренировочный матч', variable=self.training_match_var,
        )
        self.training_check.pack(side='left', padx=8)

        ch = ttk.Frame(actions)
        ch.pack(fill='x', pady=4)
        self.opponent_id_var = tk.StringVar()
        ttk.Label(ch, text='ID соперника:').pack(side='left')
        ttk.Entry(ch, textvariable=self.opponent_id_var, width=10).pack(side='left', padx=4)
        ttk.Button(ch, text='Бросить вызов', command=self._send_challenge).pack(side='left', padx=4)

        self.log = scrolledtext.ScrolledText(game_tab, height=22, state='disabled')
        self.log.pack(fill='both', expand=True, pady=8)

        bots_tab = ttk.Frame(self.lobby_notebook, padding=8)
        self.bots_tab = bots_tab
        self.lobby_notebook.add(bots_tab, text='Мои боты')

        bot_toolbar = ttk.Frame(bots_tab)
        bot_toolbar.pack(fill='x', pady=4)
        ttk.Button(bot_toolbar, text='Обновить', command=self._refresh_bots).pack(side='left', padx=4)
        ttk.Button(bot_toolbar, text='Создать', command=self._create_bot).pack(side='left', padx=4)
        ttk.Button(bot_toolbar, text='Удалить', command=self._delete_bot).pack(side='left', padx=4)
        ttk.Button(bot_toolbar, text='Копировать токен', command=self._copy_bot_token).pack(side='left', padx=4)

        create_frame = ttk.LabelFrame(bots_tab, text='Новый бот', padding=8)
        create_frame.pack(fill='x', pady=4)
        self.new_bot_name_var = tk.StringVar()
        self.new_bot_desc_var = tk.StringVar()
        self._add_field(create_frame, 'Имя', self.new_bot_name_var)
        self._add_field(create_frame, 'Описание', self.new_bot_desc_var)

        tree_frame = ttk.Frame(bots_tab)
        tree_frame.pack(fill='both', expand=True, pady=4)
        columns = ('id', 'name', 'description', 'token')
        self.bots_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=12)
        for col, title, width in (
            ('id', 'ID', 50),
            ('name', 'Имя', 120),
            ('description', 'Описание', 180),
            ('token', 'Токен', 280),
        ):
            self.bots_tree.heading(col, text=title)
            self.bots_tree.column(col, width=width, anchor='w')
        scroll = ttk.Scrollbar(tree_frame, orient='vertical', command=self.bots_tree.yview)
        self.bots_tree.configure(yscrollcommand=scroll.set)
        self.bots_tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self._bot_tokens: dict[str, str] = {}

    def _build_game(self):
        self.game_frame = ttk.Frame(self.root, padding=8)
        header = ttk.Frame(self.game_frame)
        header.pack(fill='x')
        self.game_info = ttk.Label(header, text='Игра', font=('Segoe UI', 11, 'bold'))
        self.game_info.pack(side='left')
        ttk.Button(header, text='← В лобби', command=self._leave_to_lobby).pack(side='right', padx=4)
        ttk.Button(header, text='Обновить', command=self._refresh_game).pack(side='right')

        boards = ttk.Frame(self.game_frame)
        boards.pack(fill='both', expand=True, pady=8)

        left = ttk.LabelFrame(boards, text='Моё поле', padding=4)
        left.pack(side='left', padx=8)
        self.my_board = BoardCanvas(left, 'my')
        self.my_board.pack()

        right = ttk.LabelFrame(boards, text='Выстрелы по противнику', padding=4)
        right.pack(side='left', padx=8)
        self.enemy_board = BoardCanvas(right, 'enemy', on_click=self._on_enemy_click)
        self.enemy_board.pack()

        controls = ttk.Frame(self.game_frame)
        controls.pack(fill='x')
        self.game_status_label = ttk.Label(controls, text='')
        self.game_status_label.pack(side='left', padx=4)
        ttk.Button(controls, text='Разместить корабли (случайно)', command=self._auto_place_ships).pack(side='left', padx=4)
        ttk.Button(controls, text='Принять вызов', command=self._accept_pending_challenge).pack(side='left', padx=4)

        self.pending_challenge_id: int | None = None

    def _show_login(self):
        self._hide_all()
        self.login_frame.pack(fill='both', expand=True)

    def _show_lobby(self):
        self._hide_all()
        if not hasattr(self, 'lobby_frame'):
            self._build_lobby()
        if self.api.is_bot:
            self.user_label.config(
                text=f'Бот: {self.api.username} (владелец id={self.api.user_id})',
            )
            self.lobby_notebook.tab(self.bots_tab, state='hidden')
            self.training_check.pack(side='left', padx=8)
        else:
            self.user_label.config(text=f'Игрок: {self.api.username} (id={self.api.user_id})')
            self.lobby_notebook.tab(self.bots_tab, state='normal')
            self.training_check.pack_forget()
        self.lobby_frame.pack(fill='both', expand=True)

    def _show_game(self, game_id: int):
        self.game_id = game_id
        self._hide_all()
        if not hasattr(self, 'game_frame'):
            self._build_game()
        self.game_frame.pack(fill='both', expand=True)
        if self.realtime:
            self.realtime.subscribe_game(game_id)
        self._refresh_game()
        self._schedule_refresh()

    def _schedule_refresh(self):
        if self._refresh_timer:
            self.root.after_cancel(self._refresh_timer)
        if self.game_id and hasattr(self, 'game_frame') and self.game_frame.winfo_ismapped():
            self._refresh_game()
            self._refresh_timer = self.root.after(3000, self._schedule_refresh)

    def _hide_all(self):
        for frame in (getattr(self, 'login_frame', None), getattr(self, 'lobby_frame', None), getattr(self, 'game_frame', None)):
            if frame:
                frame.pack_forget()

    def _ui(self, callback, *args, **kwargs) -> None:
        """Вызов на главном потоке Tk с захватом аргументов по значению."""
        self.root.after(0, partial(callback, *args, **kwargs))

    def _log(self, text: str) -> None:
        def append():
            self.log.config(state='normal')
            self.log.insert('end', text + '\n')
            self.log.see('end')
            self.log.config(state='disabled')
        if hasattr(self, 'log'):
            self.root.after(0, append)

    def _do_login(self):
        self.api.base_url = self.api_url_var.get().strip().rstrip('/')
        login = self.login_var.get().strip()
        password = self.password_var.get()
        if not login or not password:
            self.login_status.config(text='Введите логин и пароль', foreground='red')
            return
        self.login_status.config(text='Вход...', foreground='gray')

        def work():
            try:
                self.api.login(login, password)
                ws_url = self.ws_url_var.get().strip()
                self._start_realtime(ws_url)
                self._ui(self._on_login_ok)
            except ApiError as exc:
                self._ui(self.login_status.config, text=str(exc), foreground='red')
            except Exception as exc:
                self._ui(self.login_status.config, text=str(exc), foreground='red')

        threading.Thread(target=work, daemon=True).start()

    def _do_bot_login(self):
        self.api.base_url = self.api_url_var.get().strip().rstrip('/')
        token = self.bot_token_var.get().strip()
        if not token:
            self.bot_login_status.config(text='Введите токен бота', foreground='red')
            return
        self.bot_login_status.config(text='Вход...', foreground='gray')

        def work():
            try:
                self.api.bot_login(token)
                ws_url = self.ws_url_var.get().strip()
                self._start_realtime(ws_url)
                self._ui(self._on_login_ok)
            except ApiError as exc:
                self._ui(self.bot_login_status.config, text=str(exc), foreground='red')
            except Exception as exc:
                self._ui(self.bot_login_status.config, text=str(exc), foreground='red')

        threading.Thread(target=work, daemon=True).start()

    def _do_request_otp(self):
        phone = self.register_phone_var.get().strip()
        if not phone:
            self.register_status.config(text='Введите номер телефона', foreground='red')
            return
        self.api.base_url = self.api_url_var.get().strip().rstrip('/')
        self.register_status.config(text='Отправка кода...', foreground='gray')

        def work():
            try:
                result = self.api.register_request_otp(phone)
                msg = result.get('message', 'Код отправлен')
                if result.get('is_new_user'):
                    msg += ' (новый пользователь)'
                self._ui(self.register_status.config, text=msg, foreground='green')
            except ApiError as exc:
                self._ui(self.register_status.config, text=str(exc), foreground='red')
            except Exception as exc:
                self._ui(self.register_status.config, text=str(exc), foreground='red')

        threading.Thread(target=work, daemon=True).start()

    def _do_register(self):
        phone = self.register_phone_var.get().strip()
        code = self.register_code_var.get().strip()
        password = self.register_password_var.get()
        if not phone or not code:
            self.register_status.config(text='Укажите телефон и код', foreground='red')
            return
        if len(password) < 6:
            self.register_status.config(text='Пароль не короче 6 символов', foreground='red')
            return
        self.api.base_url = self.api_url_var.get().strip().rstrip('/')
        self.register_status.config(text='Регистрация...', foreground='gray')

        def work():
            try:
                self.api.register_confirm_otp(phone, code, password)
                ws_url = self.ws_url_var.get().strip()
                self._start_realtime(ws_url)
                self._ui(self._on_login_ok)
                self._ui(self.register_status.config, text='Успешно', foreground='green')
            except ApiError as exc:
                self._ui(self.register_status.config, text=str(exc), foreground='red')
            except Exception as exc:
                self._ui(self.register_status.config, text=str(exc), foreground='red')

        threading.Thread(target=work, daemon=True).start()

    def _on_login_ok(self):
        self.login_status.config(text='Успешно', foreground='green')
        if hasattr(self, 'bot_login_status'):
            self.bot_login_status.config(text='Успешно', foreground='green')
        if not hasattr(self, 'lobby_frame'):
            self._build_lobby()
        self._show_lobby()
        self._log(f'Вошли как {self.api.username}')
        if not self.api.is_bot:
            self._refresh_bots()

    @staticmethod
    def _mask_token(token: str) -> str:
        if len(token) <= 12:
            return token
        return f'{token[:8]}...{token[-4:]}'

    def _refresh_bots(self):
        if self.api.is_bot:
            return

        def work():
            try:
                bots = self.api.list_bots()
                self._ui(self._apply_bots_list, bots)
            except ApiError as exc:
                self._ui(messagebox.showerror, 'Боты', str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _apply_bots_list(self, bots: list):
        for item in self.bots_tree.get_children():
            self.bots_tree.delete(item)
        self._bot_tokens.clear()
        for bot in bots:
            token = bot.get('token', '')
            item_id = self.bots_tree.insert(
                '', 'end',
                values=(bot['id'], bot['name'], bot.get('description') or '', self._mask_token(token)),
            )
            self._bot_tokens[item_id] = token

    def _create_bot(self):
        name = self.new_bot_name_var.get().strip()
        if not name:
            messagebox.showwarning('Бот', 'Укажите имя бота')
            return
        description = self.new_bot_desc_var.get().strip()

        def work():
            try:
                bot = self.api.create_bot(name, description)
                self._ui(self._log, f'Бот создан: {bot["name"]}, токен: {bot["token"]}')
                self._ui(self.new_bot_name_var.set, '')
                self._ui(self.new_bot_desc_var.set, '')
                self._refresh_bots()
            except ApiError as exc:
                self._ui(messagebox.showerror, 'Бот', str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _delete_bot(self):
        selected = self.bots_tree.selection()
        if not selected:
            messagebox.showwarning('Бот', 'Выберите бота в списке')
            return
        bot_id = self.bots_tree.item(selected[0])['values'][0]
        if not messagebox.askyesno('Бот', f'Удалить бота id={bot_id}?'):
            return

        def work():
            try:
                self.api.delete_bot(int(bot_id))
                self._ui(self._log, f'Бот id={bot_id} удалён')
                self._refresh_bots()
            except ApiError as exc:
                self._ui(messagebox.showerror, 'Бот', str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _copy_bot_token(self):
        selected = self.bots_tree.selection()
        if not selected:
            messagebox.showwarning('Бот', 'Выберите бота в списке')
            return
        token = self._bot_tokens.get(selected[0])
        if not token:
            messagebox.showwarning('Бот', 'Токен не найден')
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(token)
        self._log(f'Токен скопирован: {self._mask_token(token)}')

    def _start_realtime(self, ws_url: str):
        if self.realtime:
            self.realtime.stop()
        self.realtime = RealtimeClient(ws_url, self.api.get_centrifugo_token)
        self.realtime.start(self._on_user_event, self._on_game_event)
        self.realtime.subscribe_user(self.api.user_id)

    def _on_user_event(self, message: dict):
        action = message.get('action')
        self._ui(self._log, f'[user] {json.dumps(message, ensure_ascii=False)}')
        if action == 'game_found':
            data = message.get('data', {})
            gid = data.get('game_id')
            if gid:
                self._ui(self._enter_game, gid, data.get('game_status') or data.get('status'))
        elif action == 'challenge_created':
            gid = message.get('game_id')
            opponent = message.get('opponent', {})
            self.pending_challenge_id = gid
            name = opponent.get('username', '?')
            self._ui(self._offer_challenge, gid, name)

    def _on_game_event(self, message: dict):
        action = message.get('action')
        self._ui(self._log, f'[game] {action}: {json.dumps(message, ensure_ascii=False)[:200]}')
        if action in ('game_status', 'game_started', 'shot_result', 'game_finished'):
            self._ui(self._refresh_game)

    def _offer_challenge(self, game_id: int | None, challenger: str):
        if not game_id:
            return
        if messagebox.askyesno('Вызов', f'{challenger} бросил вам вызов. Принять?'):
            self._accept_challenge(game_id)
        else:
            self.pending_challenge_id = game_id

    def _enter_game(self, game_id: int, status: str | None = None):
        self._searching = False
        self.game_status = status
        self._show_game(game_id)
        self._log(f'Игра #{game_id}, статус: {status}')

    def _matchmaking_find(self):
        def work():
            try:
                is_training = self.training_match_var.get() if self.api.is_bot else None
                result = self.api.matchmaking_find(is_training=is_training)
                self._ui(self._log, str(result))
                action = result.get('action')
                if action == 'active_game_found':
                    data = result.get('data', {})
                    gid = data.get('game_id')
                    if gid:
                        self._ui(self._enter_game, gid, data.get('status'))
                elif action == 'search_started':
                    self._searching = True
                    self._ui(self._log, 'Поиск противника... ждите событие game_found')
                elif action == 'game_found':
                    self._ui(self._log, 'Противник найден — ждите push или обновите')
            except ApiError as exc:
                self._ui(messagebox.showerror, 'Ошибка', str(exc))
        threading.Thread(target=work, daemon=True).start()

    def _matchmaking_cancel(self):
        def work():
            try:
                result = self.api.matchmaking_cancel()
                self._searching = False
                self._ui(self._log, str(result))
            except ApiError as exc:
                self._ui(messagebox.showerror, 'Ошибка', str(exc))
        threading.Thread(target=work, daemon=True).start()

    def _send_challenge(self):
        raw = self.opponent_id_var.get().strip()
        if not raw.isdigit():
            messagebox.showwarning('Вызов', 'Укажите числовой ID соперника')
            return

        def work():
            try:
                result = self.api.challenge(int(raw))
                self._ui(self._log, str(result))
                gid = result.get('game_id')
                if gid:
                    self._ui(self._enter_game, gid, result.get('game_status'))
            except ApiError as exc:
                self._ui(messagebox.showerror, 'Ошибка', str(exc))
        threading.Thread(target=work, daemon=True).start()

    def _accept_pending_challenge(self):
        if self.pending_challenge_id:
            self._accept_challenge(self.pending_challenge_id)
        elif self.game_id and self.game_status == 'waiting_challenge':
            self._accept_challenge(self.game_id)
        else:
            messagebox.showinfo('Вызов', 'Нет ожидающего вызова')

    def _accept_challenge(self, game_id: int):
        def work():
            try:
                result = self.api.accept_challenge(game_id)
                self.pending_challenge_id = None
                self._ui(self._log, str(result))
                self._ui(self._enter_game, game_id, 'waiting_ships')
            except ApiError as exc:
                self._ui(messagebox.showerror, 'Ошибка', str(exc))
        threading.Thread(target=work, daemon=True).start()

    def _auto_place_ships(self):
        if not self.game_id:
            return

        def work():
            try:
                fleet = generate_random_fleet(BOARD_SIZE)
                self.api.place_ships(self.game_id, fleet)
                self.ships_placed = True
                self._ui(self._log, 'Корабли размещены')
                self._ui(self._refresh_game)
            except ApiError as exc:
                self._ui(messagebox.showerror, 'Размещение', str(exc))
        threading.Thread(target=work, daemon=True).start()

    def _on_enemy_click(self, row: int, col: int):
        if not self.game_id or not self.api.user_id:
            return
        if self.current_turn_id != self.api.user_id:
            messagebox.showinfo('Ход', 'Сейчас не ваш ход')
            return
        if self.game_status not in ('player1_turn', 'player2_turn'):
            messagebox.showinfo('Ход', 'Игра ещё не началась')
            return

        def work():
            try:
                self.api.make_shot(self.game_id, row, col)
                self._ui(self._refresh_game)
            except ApiError as exc:
                self._ui(messagebox.showerror, 'Выстрел', str(exc))
        threading.Thread(target=work, daemon=True).start()

    def _refresh_game(self):
        if not self.game_id:
            return

        def work():
            try:
                status_resp = self.api.game_status(self.game_id)
                board = self.api.game_board(self.game_id)
                self._ui(self._apply_game_state, status_resp, board)
            except ApiError as exc:
                self._ui(self._log, f'Ошибка обновления: {exc}')
        threading.Thread(target=work, daemon=True).start()

    def _apply_game_state(self, status_resp: dict, board: dict):
        data = status_resp.get('data', {})
        self.game_status = data.get('status')
        turn = data.get('current_turn')
        self.current_turn_id = turn.get('id') if turn else None

        p1 = data.get('player1', {})
        p2 = data.get('player2') or {}
        me_p1 = p1.get('id') == self.api.user_id
        my_info = p1 if me_p1 else p2
        opp_info = p2 if me_p1 else p1
        self.ships_placed = bool(my_info.get('ships_placed'))

        opponent_name = opp_info.get('username', '?')
        turn_text = 'ваш ход' if self.current_turn_id == self.api.user_id else 'ход противника'
        if self.game_status == 'waiting_challenge':
            turn_text = 'ожидание принятия вызова'
        elif self.game_status == 'waiting_ships':
            turn_text = 'размещение кораблей'
        elif self.game_status == 'finished':
            winner = data.get('winner')
            turn_text = f'победитель: {winner.get("username")}' if winner else 'завершена'

        self.game_info.config(text=f'Игра #{self.game_id} vs {opponent_name}')
        self.game_status_label.config(
            text=f'Статус: {self.game_status} | {turn_text} | мои корабли: {"да" if self.ships_placed else "нет"}'
        )

        self.my_board.redraw(ships=board.get('my_ships'), shots=board.get('opponent_shots'), show_ships=True)
        clickable = (
            self.game_status in ('player1_turn', 'player2_turn')
            and self.current_turn_id == self.api.user_id
        )
        self.enemy_board.redraw(ships=None, shots=board.get('my_shots'), show_ships=False, clickable=clickable)

    def _leave_to_lobby(self):
        if self._refresh_timer:
            self.root.after_cancel(self._refresh_timer)
            self._refresh_timer = None
        if self.game_id:
            def work():
                try:
                    self.api.leave_game(self.game_id)
                except ApiError:
                    pass
            threading.Thread(target=work, daemon=True).start()
            if self.realtime:
                self.realtime.unsubscribe_game(self.game_id)
        self.game_id = None
        self._show_lobby()

    def _logout(self):
        if self.realtime:
            self.realtime.stop()
            self.realtime = None
        self.api.access_token = None
        self.api.refresh_token = None
        self.api.user_id = None
        self.api.username = None
        self.api.is_bot = False
        self.api.user_bot = None
        self.game_id = None
        self._show_login()

    def run(self):
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.root.mainloop()

    def _on_close(self):
        if self.realtime:
            self.realtime.stop()
        self.root.destroy()


def main():
    WarshipClientApp().run()


if __name__ == '__main__':
    main()
