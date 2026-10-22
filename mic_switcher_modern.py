# -*- coding: utf-8 -*-
"""
Переключатель микрофонов — современный интерфейс (CustomTkinter).

Вся аудио-логика, конфиг, горячая клавиша и роутинг VAC переиспользуются
импортом из mic_switcher.py (чистые модульные сущности). Здесь — только
новый UI-класс App и main() с single-instance mutex.
"""
import ctypes
import math
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk

import customtkinter as ctk

import mic_switcher as ms
import sounddevice as sd

# ─────────────────────────────────────────────────────────────
# Отладочный лог: %TEMP%\micswitcher_debug.log
# (в TEMP, чтобы не зависеть от прав на папку приложения)
# ─────────────────────────────────────────────────────────────
def _dbg(msg):
    try:
        p = os.path.join(os.environ.get("TEMP") or os.environ.get("TMP") or ".",
                         "micswitcher_debug.log")
        with open(p, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────
# Дизайн-токены (та же палитра «аудио-консоль», что в mic_switcher.py)
# ─────────────────────────────────────────────────────────────
BG          = ms.BG           # фон приложения
CARD        = ms.CARD         # карточки
SURFACE_2   = ms.SURFACE_2    # hover-поверхность
BORDER      = ms.BORDER       # границы / разделители
TEXT        = ms.TEXT         # основной текст
DIM         = ms.DIM          # вторичный текст
TEXT_3      = ms.TEXT_3       # приглушённый
BTN         = ms.BTN          # акцент
BTN_HOVER   = ms.BTN_HOVER
ACTIVE      = ms.ACTIVE       # успех / активен
ACCENT_SOFT = ms.ACCENT_SOFT  # выделенный элемент
DANGER      = ms.DANGER
WARNING     = ms.WARNING
FONT        = ms.FONT

# Иконка (base64). Заполняется автоматически при сборке exe.
ICON_B64 = ""

# Релиз
VERSION = "1.0.0"

# ─────────────────────────────────────────────────────────────
# Локализация (RU / EN)
# ─────────────────────────────────────────────────────────────
STRINGS = {
    "ru": {
        "app_title":          "Переключатель микрофонов",
        "footer":             "Переключатель микрофонов  •  v{ver}",
        "hotkey_badge":       "Клавиша: {hk}",
        "section_mics":       "Микрофоны",
        "reset_vol":          "↺ Сброс громкости",
        "switch_btn":         "Сменить микрофон  ({hk})",
        "btn_settings":       "Настройки",
        "btn_quit":           "Завершить сеанс программы",
        "hint_main":          "ЛКМ — выбрать   •   колесо — громкость (0–250%)   •   тумблер — вкл/выкл микрофона",
        "vac_title":          "Виртуальный микрофон",
        "vac_not_found":      "не найден",
        "vac_active":         "активен",
        "vac_inactive":       "не активен",
        "vac_unavailable":    "недоступен",
        "vac_status_active":  "Активен: {name}  →  Виртуальный микрофон",
        "vac_status_inactive":"Виртуальный микрофон: роутинг не активен",
        "vac_status_novac":   "VAC не установлен — виртуальный микрофон недоступен",
        "vac_discord":        "Discord: настроить звук",
        "vac_windows":        "Windows: настройки звука",
        "vac_test_btn":       "Проверить виртуальный микрофон",
        "vac_mon_title":      "Прослушать виртуальный микрофон",
        "vac_mon_desc":       "Ведёт звук вирт. микрофона на устройство вывода, чтобы его услышать",
        "vac_mon_out":        "Устройство вывода:",
        "vac_mon_start":      "Прослушать",
        "vac_mon_stop":       "Остановить прослушку",
        "sec_hotkey":         "Горячая клавиша",
        "hk_hint":            "Кликните по полю и нажмите нужную клавишу (Esc — отмена)",
        "hk_press":           "Нажмите клавишу… (Esc — отмена)",
        "hk_add_main":        "Добавьте основную клавишу…",
        "hk_invalid":         "Эту клавишу нельзя назначить",
        "sec_autostart":      "Автозапуск",
        "autostart_chk":      "Запускать при входе в Windows",
        "sec_lang":           "Язык",
        "btn_back":           "←  Назад",
        "mics_empty":         "Микрофоны не найдены",
        "mic_excluded":       "исключён",
        "vol_label":          "Громкость",
        "tray_show":          "Показать окно",
        "tray_quit":          "Завершить сеанс программы",
        "tray_tooltip":       "Переключатель микрофонов",
        "err_title":          "Ошибка",
        "err_hotkey_input":   "Не удалось начать ввод: {e}",
        "err_badkey_title":   "Неверная клавиша",
        "msg_already_run":    "Программа уже запущена — ищи её окно в трее или на рабочем столе.",
        "toast_vac_fail":     "⚠️ Виртуальный микрофон: {e}",
        "toast_hotkey":       "🔑 Горячая клавиша: {hk}",
        "toast_autostart_on": "🚀 Автозапуск: включён",
        "toast_autostart_off":"🚀 Автозапуск: выключен",
        "vac_test_checking":  "Проверяю виртуальный микрофон…",
        "vac_test_notfound":  "VAC не найден — установите Virtual Audio Cable",
        "vac_test_error":     "Ошибка при проверке: {e}",
        "vac_test_ok":        "Виртуальный микрофон работает (уровень {rms}). В Discord/Windows будет слышно.",
        "vac_test_weak":      "Сигнал слабый (уровень {rms}). Убедитесь, что в Discord выбран микрофон «{vac}»",
        "mon_select_out":     "Выберите устройство вывода",
        "mon_start_fail":     "Не удалось начать прослушку: {e}",
        "mon_listening":      "Слушайте: вирт. микрофон → «{name}»",
        "mon_stopped":        "Прослушка остановлена",
    },
    "en": {
        "app_title":          "Mic Switcher",
        "footer":             "Mic Switcher  •  v{ver}",
        "hotkey_badge":       "Key: {hk}",
        "section_mics":       "Microphones",
        "reset_vol":          "↺ Reset volume",
        "switch_btn":         "Switch mic  ({hk})",
        "btn_settings":       "Settings",
        "btn_quit":           "Exit",
        "hint_main":          "LMB — select   •   wheel — volume (0–250%)   •   toggle — enable/disable mic",
        "vac_title":          "Virtual microphone",
        "vac_not_found":      "not found",
        "vac_active":         "active",
        "vac_inactive":       "inactive",
        "vac_unavailable":    "unavailable",
        "vac_status_active":  "Active: {name}  →  Virtual mic",
        "vac_status_inactive":"Virtual mic: routing inactive",
        "vac_status_novac":   "VAC not installed — virtual mic unavailable",
        "vac_discord":        "Discord: audio settings",
        "vac_windows":        "Windows: sound settings",
        "vac_test_btn":       "Test virtual microphone",
        "vac_mon_title":      "Monitor virtual microphone",
        "vac_mon_desc":       "Routes virtual mic audio to an output device so you can hear it",
        "vac_mon_out":        "Output device:",
        "vac_mon_start":      "Monitor",
        "vac_mon_stop":       "Stop monitoring",
        "sec_hotkey":         "Hotkey",
        "hk_hint":            "Click the field and press the desired key (Esc — cancel)",
        "hk_press":           "Press a key… (Esc — cancel)",
        "hk_add_main":        "Add a main key…",
        "hk_invalid":         "This key cannot be assigned",
        "sec_autostart":      "Autostart",
        "autostart_chk":      "Launch at Windows startup",
        "sec_lang":           "Language",
        "btn_back":           "←  Back",
        "mics_empty":         "No microphones found",
        "mic_excluded":       "excluded",
        "vol_label":          "Volume",
        "tray_show":          "Show window",
        "tray_quit":          "Exit",
        "tray_tooltip":       "Mic Switcher",
        "err_title":          "Error",
        "err_hotkey_input":   "Failed to start input: {e}",
        "err_badkey_title":   "Invalid key",
        "msg_already_run":    "Already running — find its window in the tray or on the desktop.",
        "toast_vac_fail":     "⚠️ Virtual microphone: {e}",
        "toast_hotkey":       "🔑 Hotkey: {hk}",
        "toast_autostart_on": "🚀 Autostart: enabled",
        "toast_autostart_off":"🚀 Autostart: disabled",
        "vac_test_checking":  "Testing virtual microphone…",
        "vac_test_notfound":  "VAC not found — install Virtual Audio Cable",
        "vac_test_error":     "Test error: {e}",
        "vac_test_ok":        "Virtual microphone is working (level {rms}). Will be audible in Discord/Windows.",
        "vac_test_weak":      "Signal weak (level {rms}). Make sure «{vac}» is selected in Discord.",
        "mon_select_out":     "Select an output device",
        "mon_start_fail":     "Failed to start monitoring: {e}",
        "mon_listening":      "Listening: virtual mic → «{name}»",
        "mon_stopped":        "Monitoring stopped",
    },
}


# Анимации: длительность в шагах и easing-кривые
ANIM_TRANS_STEPS = 12      # смена экрана
ANIM_TOAST_IN    = 10      # тост: появление
ANIM_TOAST_OUT   = 8       # тост: исчезновение

# Сколько микрофонов окно «растягивается» под них; дальше — скролл
MAX_VISIBLE_MICS = 5
ANIM_FLASH_STEPS = 20      # вспышка активной карточки (плавнее)
ANIM_OUT_STEPS   = 8       # (legacy) — заменено кроссфейдом
ANIM_IN_STEPS    = 10      # (legacy) — заменено кроссфейдом
ANIM_FADE_OUT    = 6       # кроссфейд: ступени fade-out (ease-in)
ANIM_FADE_IN     = 8       # кроссфейд: ступени fade-in (ease-out)
ANIM_STEP_MS     = 20      # период кадра (плавнее, без дёрганий)


def _ease_out_cubic(t):
    return 1.0 - (1.0 - t) ** 3


def _ease_in_cubic(t):
    return t ** 3


def _mix_hex(h1, h2, t):
    """Смешать два hex-цвета (#rrggbb) с коэффициентом t (0..1)."""
    a = h1.lstrip("#"); b = h2.lstrip("#")
    return "#%02x%02x%02x" % tuple(
        int(int(a[i:i + 2], 16) + (int(b[i:i + 2], 16) - int(a[i:i + 2], 16)) * t)
        for i in (0, 2, 4))


def _norm_color(v):
    """Нормализовать CTk-цвет в '#rrggbb' (None если не hex / transparent)."""
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        v = v[1] if len(v) >= 2 else v[0]
    if not isinstance(v, str):
        return None
    v = v.strip().lower()
    if v in ("", "transparent"):
        return None
    if v.startswith("#") and len(v) == 7:
        try:
            int(v[1:3], 16); int(v[3:5], 16); int(v[5:7], 16)
            return v
        except Exception:
            return None
    return None


def _collect_faders(root, out):
    """Рекурсивно собрать (виджет, attr, hex) для окрашиваемых CTk-виджетов."""
    try:
        if isinstance(root, ctk.CTkFrame):
            for attr in ("fg_color", "border_color"):
                hc = _norm_color(root.cget(attr))
                if hc:
                    out.append((root, attr, hc))
        elif isinstance(root, ctk.CTkLabel):
            hc = _norm_color(root.cget("text_color"))
            if hc:
                out.append((root, "text_color", hc))
        elif isinstance(root, (ctk.CTkSwitch, ctk.CTkSlider, ctk.CTkCheckBox, ctk.CTkButton)):
            for attr in ("fg_color", "progress_color", "button_color", "button_hover_color"):
                try:
                    hc = _norm_color(root.cget(attr))
                except Exception:
                    hc = None
                if hc:
                    out.append((root, attr, hc))
    except Exception:
        pass
    try:
        for ch in root.winfo_children():
            _collect_faders(ch, out)
    except Exception:
        pass


def _apply_fade(specs, t):
    """t=0 → всё в BG (скрыто), t=1 → родной цвет. Мёртвые пропускаются."""
    for w, attr, color in specs:
        try:
            if not w.winfo_exists():
                continue
            w.configure(**{attr: _mix_hex(BG, color, t)})
        except Exception:
            pass


def _blank_image(size):
    """Прозрачный CTkImage (для скрытия точки без сдвига вёрстки)."""
    try:
        from PIL import Image
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    except Exception:
        return None


def _round_window(widget, radius):
    """Вырезать окна по-настоящему скруглённую область (Windows, SetWindowRgn).

    -transparentcolor (color-key) оставляет видимую квадратную подложку и
    подкрашенное «ореолированное» ребро; window region физически вырезает
    углы окна — за ними виден desktop, без артефактов.
    """
    if os.name != "nt":
        return
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        hwnd = widget.winfo_id()
        LOGPIXELSX = 88
        hdc = user32.GetWindowDC(hwnd)
        dpi = gdi32.GetDeviceCaps(hdc, LOGPIXELSX) if hdc else 96
        if hdc:
            user32.ReleaseDC(hwnd, hdc)
        scale = max(1, dpi) / 96.0

        # Физический размер окна в пикселях
        class _RECT(ctypes.Structure):
            _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                        ("r", ctypes.c_long), ("b", ctypes.c_long)]
        rc = _RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rc)):
            return
        W = rc.r - rc.l
        H = rc.b - rc.t
        R = max(2, int(round(radius * scale)))
        R = min(R, W // 2, H // 2)

        # Точки скруглённого прямоугольника: 4 дуги + 4 прямые стороны
        STEPS = 16
        pts = []

        def _arc(cx, cy, a0, a1):
            for k in range(STEPS + 1):
                a = a0 + (a1 - a0) * k / STEPS
                pts.append((cx + R * math.cos(a), cy + R * math.sin(a)))

        _arc(R, R, math.pi, 1.5 * math.pi)              # левый верхний
        _arc(W - R, R, 1.5 * math.pi, 2 * math.pi)      # правый верхний
        _arc(W - R, H - R, 0, 0.5 * math.pi)            # правый нижний
        _arc(R, H - R, 0.5 * math.pi, math.pi)          # левый нижний

        class _POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        arr = (_POINT * len(pts))(*[(int(round(x)), int(round(y))) for x, y in pts])
        hrgn = gdi32.CreatePolygonRgn(arr, len(pts), 1)  # ALTERNATE
        if hrgn:
            # Старая область освобождается самим SetWindowRgn — DeleteObject не нужен
            user32.SetWindowRgn(hwnd, hrgn, True)
    except Exception:
        pass


def _glow_dot(color, size=20, levels=28):
    """Свечение: попиксельный гаусс (привычный вид) + радиальная маска (чистый круглый край).

    Ядро — компактный яркий центр, гало — мягкое свечение вокруг.
    Радиальная маска (1-t²) обрезает квадрат → чистая круглая прозрачность.
    «Дыхание» — плавная смена 28 уровней яркости.
    """
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        c = color.lstrip("#")
        rgb = (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
        core_rgb = tuple(min(255, v + 110) for v in rgb)
        S = size * 8
        c0 = S / 2.0
        dist = []
        for y in range(S):
            dy = y - c0 + 0.5
            row = []
            for x in range(S):
                dx = x - c0 + 0.5
                row.append(dx * dx + dy * dy)
            dist.append(row)
        inv2h = 1.0 / (2.0 * (0.17 * S) ** 2)
        inv2c = 1.0 / (2.0 * (0.07 * S) ** 2)
        Re = S / 2.0
        radial = []
        for y in range(S):
            dy = y - c0
            row = []
            for x in range(S):
                dx = x - c0
                t = math.sqrt(dx * dx + dy * dy) / Re
                row.append(max(0.0, 1.0 - t * t) if t < 1.0 else 0.0)
            radial.append(row)
        out = []
        for k in range(levels):
            b = k / (levels - 1)
            halo_max = int(80 + 80 * b)
            core_max = int(220 + 35 * b)
            img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            px = img.load()
            for y in range(S):
                g = dist[y]
                r2 = radial[y]
                for x in range(S):
                    gg = g[x]
                    rm = r2[x]
                    if rm <= 0:
                        continue
                    w_c = math.exp(-gg * inv2c)
                    a = max(halo_max * math.exp(-gg * inv2h), core_max * w_c) * rm
                    if a < 1:
                        continue
                    a = 255 if a > 255 else int(a)
                    r = int(rgb[0] + (core_rgb[0] - rgb[0]) * w_c)
                    g2 = int(rgb[1] + (core_rgb[1] - rgb[1]) * w_c)
                    b2 = int(rgb[2] + (core_rgb[2] - rgb[2]) * w_c)
                    px[x, y] = (r, g2, b2, a)
            img = img.resize((size, size), Image.LANCZOS)
            out.append(ctk.CTkImage(light_image=img, dark_image=img, size=(size, size)))
        return out
    except Exception:
        return None


def _embedded_icon_bytes():
    """Байты встроенной иконки (base64, вшивается при сборке exe)."""
    b64 = ICON_B64 or getattr(ms, "ICON_B64", "")
    if not b64:
        return None
    import base64
    try:
        return base64.b64decode(b64)
    except Exception:
        return None


def get_icon_bytes():
    """Байты .ico: встроенные (frozen) — всегда свежие; в dev — файл mic.ico рядом."""
    if getattr(sys, "frozen", False):
        return _embedded_icon_bytes()
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mic.ico")
    if os.path.exists(p):
        with open(p, "rb") as f:
            return f.read()
    return None


def get_icon_path():
    """Путь к .ico на диске (для iconbitmap). ВСЕГДА распаковываем свежую
    встроенную иконку. Раньше кэш в temp (if not exists) подхватывал устаревшую
    иконку из прошлой сессии — из-за этого трей показывал старую (квадратную)."""
    data = get_icon_bytes()
    if not data:
        return None
    import tempfile
    p = os.path.join(tempfile.gettempdir(), "mic_switcher_ico.ico")
    try:
        with open(p, "wb") as f:
            f.write(data)
        return p
    except Exception:
        return None


def get_tray_image():
    """PIL-изображение для трея: свежая встроенная иконка; фолбэк — КРУГ, не квадрат."""
    from PIL import Image
    data = get_icon_bytes()
    if data:
        import io
        try:
            return Image.open(io.BytesIO(data)).convert("RGBA")
        except Exception:
            pass
    S = 64
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, S - 2, S - 2), fill=(76, 141, 255, 255))
    return img


class App:
    def __init__(self):
        # ── Состояние (данные и логика) ──
        self.hidden = False
        self.popup = None
        self.index = 0
        self.hotkey, self.exclude, self.mic_vol = ms.load_config()
        self.listener = None
        self.tray_icon = None
        self._tray_q = queue.Queue()
        self._hk_capturing = False
        self._cap_old_listener = None
        self._hotkey_q = queue.Queue()
        self._lvl = 0.0
        self.router = None
        self.monitor = None
        self.mic_rows = []
        self.screen = "main"
        self._mon_devices = []
        self._mon_by_name = {}

        # ── Язык ──
        self.lang = ms.load_lang()  # "ru" или "en"

        # ── Окно ──
        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk()
        self.root.title(self.t("app_title"))
        self.root.configure(fg_color=BG)
        self.root.geometry("500x748")
        self.root.minsize(470, 680)
        self.root.attributes("-topmost", True)
        # Крестик в заголовке прячет окно в трей, а не закрывает программу.
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        icon = get_icon_path()
        if icon:
            try:
                self.root.iconbitmap(icon)
            except Exception:
                pass

        # Шрифты (после создания корневых окон)
        global F_TITLE, F_H2, F_BODY, F_BODY_B, F_CAP, F_CAP_B, F_MICRO, F_BTN
        F_TITLE  = ctk.CTkFont(family=FONT, size=18, weight="bold")
        F_H2     = ctk.CTkFont(family=FONT, size=13, weight="bold")
        F_BODY   = ctk.CTkFont(family=FONT, size=12)
        F_BODY_B = ctk.CTkFont(family=FONT, size=12, weight="bold")
        F_CAP    = ctk.CTkFont(family=FONT, size=11)
        F_CAP_B  = ctk.CTkFont(family=FONT, size=11, weight="bold")
        F_MICRO  = ctk.CTkFont(family=FONT, size=10)
        F_BTN    = ctk.CTkFont(family=FONT, size=14, weight="bold")

        # ── Данные ──
        self.refresh()

        # Виртуальный микрофон (VAC)
        self.cable_idx = ms.find_cable_input()
        self.vac_name = ms.find_cable_input_name() or "Line 1 (Virtual Audio Cable)"
        if self.cable_idx is not None and self.current is not None:
            try:
                r = ms.CableRouter(self.cable_idx)
                if r.start(self.current.FriendlyName):
                    r.set_gain(self._gain_for(self.current.id))
                    self.router = r
                else:
                    self.router = None
                    self.root.after(0, lambda e=r.last_error: self.show_notification(
                        self.t("toast_vac_fail", e=(e or "?"))))
            except Exception as e:
                self.router = None
                self.root.after(0, lambda e=e: self.show_notification(
                    self.t("toast_vac_fail", e=str(e))))

        # ── Экраны ──
        self._build_main()
        self._build_settings()
        self._show_screen("main")
        self.update_ui()
        # после первой отрисовки окна — проверить, нужен ли скроллбар,
        # и подогнать высоты под фактическое число микрофонов
        self.root.after(250, self._initial_fit)

        self._start_tray()
        self.root.after(100, self._poll_hotkey)

    def t(self, key, **kw):
        """Вернуть строку локализованного текста для текущего языка."""
        d = STRINGS.get(self.lang, STRINGS["ru"])
        s = d.get(key, key)
        if kw:
            try:
                s = s.format(**kw)
            except Exception:
                pass
        return s

    def _initial_fit(self):
        self._resync_layout()
        # после полной отрисовки окна высоты могут чуть поменяться — перепроверяем
        self.root.after(150, self._resync_layout)

    # ═══════════════════════════ ЭКРАН: ГЛАВНЫЙ ═══════════════════════════
    def _build_main(self):
        self.main = ctk.CTkFrame(self.root, fg_color="transparent")

        # ── Заголовок: название + бейдж клавиши / статус + VU-метр ──
        hdr = ctk.CTkFrame(self.main, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(18, 4))

        row1 = ctk.CTkFrame(hdr, fg_color="transparent")
        row1.pack(fill="x")
        self._title_lbl = ctk.CTkLabel(row1, text=self.t("app_title"), font=F_TITLE,
                     text_color=TEXT, anchor="w")
        self._title_lbl.pack(side="left")
        self.hk_pill = ctk.CTkFrame(row1, fg_color=SURFACE_2, corner_radius=999)
        self.hk_pill.pack(side="right")
        self.hk_badge_lbl = ctk.CTkLabel(self.hk_pill, text=self.t("hotkey_badge", hk=self.display_hotkey()),
                                         font=F_CAP_B, text_color=DIM)
        self.hk_badge_lbl.pack(padx=10, pady=5)

        row2 = ctk.CTkFrame(hdr, fg_color="transparent")
        row2.pack(fill="x", pady=(8, 0))
        self.hdr_dot = ctk.CTkLabel(row2, text="●", font=F_CAP_B, text_color=DIM)
        self.hdr_dot.pack(side="left")
        self.hdr_sub = ctk.CTkLabel(row2, text="", font=F_CAP, text_color=DIM, anchor="w")
        self.hdr_sub.pack(side="left", padx=(8, 0))
        self.vu = ctk.CTkProgressBar(row2, width=110, height=8, corner_radius=4,
                                     fg_color=BORDER, progress_color=ACTIVE)
        self._vu_prev = 0.0
        def vu_set(v):
            if abs(float(v) - self._vu_prev) > 0.01:
                self._vu_prev = float(v)
                self.vu.set(self._vu_prev)
            else:
                # Если значение не изменилось — принудительно обновляем отрисовку
                try:
                    self.vu._draw()
                except Exception:
                    pass
        self.vu_set = vu_set
        self.vu.pack(side="right")

        # ── Секция «Микрофоны» ──
        sec = ctk.CTkFrame(self.main, fg_color="transparent")
        sec.pack(fill="x", padx=20, pady=(12, 4))
        self._sec_mics_lbl = ctk.CTkLabel(sec, text=self.t("section_mics"), font=F_H2, text_color=TEXT, anchor="w")
        self._sec_mics_lbl.pack(side="left")
        self._reset_vol_btn = ctk.CTkButton(sec, text=self.t("reset_vol"), command=self.reset_volumes,
                      fg_color=SURFACE_2, hover_color=BTN, text_color=DIM,
                      corner_radius=999, height=28, font=F_CAP_B)
        self._reset_vol_btn.pack(side="right")

        # Список микрофонов (скролл-область фиксированной высоты —
        # размер окна одинаков для обоих экранов)
        self.mic_list = ctk.CTkScrollableFrame(self.main, fg_color="transparent",
                                               height=308, scrollbar_fg_color=BORDER,
                                               scrollbar_button_color=SURFACE_2,
                                               scrollbar_button_hover_color=BTN)
        self.mic_list.pack(fill="x", padx=20)

        # ── Карточка виртуального микрофона ──
        self._build_vac_card()

        # ── Основное действие ──
        self.switch_btn = ctk.CTkButton(self.main,
                                        text=self.t("switch_btn", hk=self.display_hotkey()),
                                        command=self.toggle,
                                        fg_color=BTN, hover_color=BTN_HOVER, text_color="white",
                                        font=F_BTN, height=46, corner_radius=12)
        self.switch_btn.pack(fill="x", padx=20, pady=(10, 10))

        # ── Вторичные действия (симметрично, равной шириной) ──
        row = ctk.CTkFrame(self.main, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 8))
        self._btn_settings = ctk.CTkButton(row, text=self.t("btn_settings"), command=self.open_settings,
                      fg_color=CARD, hover_color=SURFACE_2, text_color=TEXT,
                      corner_radius=999, height=36, font=F_CAP_B,
                      border_width=1, border_color=BORDER)
        self._btn_settings.pack(side="left", fill="x",
                                                                expand=True, padx=(0, 4))
        self._btn_quit = ctk.CTkButton(row, text=self.t("btn_quit"), command=self.quit_app,
                      fg_color=CARD, hover_color="#3a2030", text_color=DANGER,
                      corner_radius=999, height=36, font=F_CAP_B,
                      border_width=1, border_color=BORDER)
        self._btn_quit.pack(side="left", fill="x",
                                                                expand=True, padx=(4, 0))

        # ── Подсказка + версия ──
        self._hint_lbl = ctk.CTkLabel(self.main,
                     text=self.t("hint_main"),
                     font=F_MICRO, text_color=TEXT_3, anchor="w")
        self._hint_lbl.pack(fill="x", padx=20, pady=(2, 4))
        self._footer_lbl = ctk.CTkLabel(self.main, text=self.t("footer", ver=VERSION),
                     font=F_MICRO, text_color=TEXT_3)
        self._footer_lbl.pack(pady=(0, 12))

    def _build_vac_card(self):
        card = ctk.CTkFrame(self.main, fg_color=CARD, corner_radius=14,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", padx=20, pady=(8, 8))
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(8, 0))
        self._vac_title_lbl = ctk.CTkLabel(top, text=self.t("vac_title"), font=F_H2, text_color=TEXT,
                     anchor="w")
        self._vac_title_lbl.pack(side="left")
        self.vac_status_pill = ctk.CTkFrame(top, fg_color=SURFACE_2, corner_radius=999)
        self.vac_status_pill.pack(side="right")
        self.vac_status_lbl = ctk.CTkLabel(self.vac_status_pill, text="…", font=F_CAP_B,
                                           text_color=DIM)
        self.vac_status_lbl.pack(padx=10, pady=4)
        self._vac_name_lbl = ctk.CTkLabel(card, text=(self.vac_name or self.t("vac_not_found")), font=F_CAP, text_color=DIM,
                     anchor="w")
        self._vac_name_lbl.pack(fill="x", padx=14, pady=(2, 6))
        links = ctk.CTkFrame(card, fg_color="transparent")
        links.pack(fill="x", padx=14, pady=(0, 10))
        self._vac_discord_btn = ctk.CTkButton(links, text=self.t("vac_discord"),
                      command=self.open_discord_voice_settings,
                      fg_color=SURFACE_2, hover_color=BTN, text_color=TEXT,
                      corner_radius=999, height=30, font=F_CAP_B)
        self._vac_discord_btn.pack(side="left")
        self._vac_windows_btn = ctk.CTkButton(links, text=self.t("vac_windows"),
                      command=self.open_windows_sound_settings,
                      fg_color=SURFACE_2, hover_color=BTN, text_color=TEXT,
                      corner_radius=999, height=30, font=F_CAP_B)
        self._vac_windows_btn.pack(side="left", padx=(8, 0))

    # ═══════════════════════════ ЭКРАН: НАСТРОЙКИ ═══════════════════════════
    def _build_settings(self):
        s = ctk.CTkFrame(self.root, fg_color="transparent")
        self.settings = s

        # Футер с версией — как на главном экране (прижат к низу)
        self._settings_footer = ctk.CTkLabel(s, text=self.t("footer", ver=VERSION),
                     font=F_MICRO, text_color=TEXT_3)
        self._settings_footer.pack(side="bottom", pady=(0, 14))

        hdr = ctk.CTkFrame(s, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(18, 4))
        self._settings_title = ctk.CTkLabel(hdr, text=self.t("btn_settings"), font=F_TITLE, text_color=TEXT, anchor="w")
        self._settings_title.pack(side="left")
        self._btn_back = ctk.CTkButton(hdr, text=self.t("btn_back"), command=self.close_settings,
                      fg_color=SURFACE_2, hover_color=BTN, text_color=TEXT,
                      corner_radius=999, height=32, font=F_CAP_B)
        self._btn_back.pack(side="right")

        # ── Виртуальный микрофон ──
        c1 = ctk.CTkFrame(s, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        c1.pack(fill="x", padx=20, pady=(12, 10), expand=True)
        self._settings_vac_title = ctk.CTkLabel(c1, text=self.t("vac_title"), font=F_H2, text_color=TEXT,
                     anchor="w")
        self._settings_vac_title.pack(fill="x", padx=14, pady=(12, 4))
        self.vac_status_row = ctk.CTkLabel(c1, text="", font=F_CAP, text_color=DIM,
                                           anchor="w", justify="left")
        self.vac_status_row.pack(fill="x", padx=14)
        self._settings_test_btn = ctk.CTkButton(c1, text=self.t("vac_test_btn"), command=self.test_virtual_mic,
                      fg_color=BTN, hover_color=BTN_HOVER, text_color="white",
                      corner_radius=10, height=36, font=F_BODY_B)
        self._settings_test_btn.pack(fill="x", padx=14, pady=(8, 4))
        self.vac_test_lbl = ctk.CTkLabel(c1, text="", font=F_CAP, text_color=DIM,
                                         anchor="w", justify="left", height=1)
        self.vac_test_lbl.pack(fill="x", padx=14)

        ctk.CTkFrame(c1, fg_color=BORDER, height=1).pack(fill="x", padx=14, pady=10)

        self._settings_mon_title = ctk.CTkLabel(c1, text=self.t("vac_mon_title"), font=F_H2, text_color=TEXT,
                     anchor="w")
        self._settings_mon_title.pack(fill="x", padx=14, pady=(0, 2))
        self._settings_mon_desc = ctk.CTkLabel(c1, text=self.t("vac_mon_desc"),
                     font=F_MICRO, text_color=TEXT_3, anchor="w", justify="left")
        self._settings_mon_desc.pack(fill="x", padx=14, pady=(0, 8))
        dev_row = ctk.CTkFrame(c1, fg_color="transparent")
        dev_row.pack(fill="x", padx=14)
        self._settings_mon_out_lbl = ctk.CTkLabel(dev_row, text=self.t("vac_mon_out"), font=F_CAP, text_color=DIM)
        self._settings_mon_out_lbl.pack(side="left")
        self.mon_out_menu = ctk.CTkOptionMenu(dev_row, values=[], command=lambda v: None,
                                              fg_color=SURFACE_2, button_color=BORDER,
                                              button_hover_color=BTN, text_color=TEXT,
                                              font=F_CAP, height=32, corner_radius=8)
        self.mon_out_menu.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.mon_btn = ctk.CTkButton(c1, text=self.t("vac_mon_start"), command=self.toggle_monitor,
                                     fg_color=BTN, hover_color=BTN_HOVER, text_color="white",
                                     corner_radius=10, height=36, font=F_BODY_B)
        self.mon_btn.pack(fill="x", padx=14, pady=(10, 4))
        self.mon_lbl = ctk.CTkLabel(c1, text="", font=F_CAP, text_color=DIM,
                                    anchor="w", justify="left", height=1)
        self.mon_lbl.pack(fill="x", padx=14, pady=(0, 12))

        # ── Горячая клавиша ──
        c2 = ctk.CTkFrame(s, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        c2.pack(fill="x", padx=20, pady=(0, 10), expand=True)
        self._settings_hk_title = ctk.CTkLabel(c2, text=self.t("sec_hotkey"), font=F_H2, text_color=TEXT,
                     anchor="w")
        self._settings_hk_title.pack(fill="x", padx=14, pady=(12, 4))
        self.hk_field = ctk.CTkButton(c2, text=self.display_hotkey(),
                                      command=self._begin_hotkey_capture,
                                      fg_color=SURFACE_2, hover_color=ACCENT_SOFT,
                                      text_color=TEXT, corner_radius=10, height=40,
                                      font=F_BODY_B)
        self.hk_field.pack(fill="x", padx=14)
        self._settings_hk_hint = ctk.CTkLabel(c2, text=self.t("hk_hint"),
                     font=F_MICRO, text_color=TEXT_3, anchor="w")
        self._settings_hk_hint.pack(fill="x", padx=14, pady=(8, 12))

        # ── Автозапуск ──
        c3 = ctk.CTkFrame(s, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        c3.pack(fill="x", padx=20, pady=(0, 10), expand=True)
        self._settings_autostart_title = ctk.CTkLabel(c3, text=self.t("sec_autostart"), font=F_H2, text_color=TEXT,
                     anchor="w")
        self._settings_autostart_title.pack(fill="x", padx=14, pady=(12, 4))
        self.auto_var = tk.BooleanVar(value=ms.autostart_enabled())
        self._autostart_chk = ctk.CTkCheckBox(c3, text=self.t("autostart_chk"), variable=self.auto_var,
                        command=self._apply_autostart,
                        fg_color=ACTIVE, hover_color=ACTIVE, text_color=TEXT, font=F_BODY,
                        checkbox_width=18, checkbox_height=18, corner_radius=5,
                        border_width=1, border_color=BORDER)
        self._autostart_chk.pack(fill="x", padx=14, pady=(0, 12))

        # ── Язык ──
        c4 = ctk.CTkFrame(s, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        c4.pack(fill="x", padx=20, pady=(0, 10), expand=True)
        self._settings_lang_title = ctk.CTkLabel(c4, text=self.t("sec_lang"), font=F_H2, text_color=TEXT,
                     anchor="w")
        self._settings_lang_title.pack(fill="x", padx=14, pady=(12, 4))
        self.lang_menu = ctk.CTkOptionMenu(c4, values=["Русский", "English"],
                                           command=self._on_lang_change,
                                           fg_color=SURFACE_2, button_color=BORDER,
                                           button_hover_color=BTN, text_color=TEXT,
                                           font=F_BODY, height=36, corner_radius=8)
        self.lang_menu.set("Русский" if self.lang == "ru" else "English")
        self.lang_menu.pack(fill="x", padx=14, pady=(0, 12))

    def _show_screen(self, name):
        """Смена экрана с плавным въездом нового (slide-in, ~190 мс).
        Счётчик поколений гасит анимацию предыдущей смены, если новая
        началась раньше, чем старая доиграла (иначе старая «возродит» свой экран)."""
        if name == "main":
            old, new = self.settings, self.main
        else:
            old, new = self.main, self.settings
        for w in (old, new):
            try:
                w.place_forget()
            except Exception:
                pass
            try:
                w.pack_forget()
            except Exception:
                pass
        self.screen = name
        self._anim_gen = getattr(self, "_anim_gen", 0) + 1
        gen = self._anim_gen
        off = 48  # стартовое смещение въезда
        new.place(relx=0, rely=0, relwidth=1, relheight=1, x=off)
        new.update_idletasks()

        def _settle():
            if getattr(self, "_anim_gen", 0) != gen:
                return  # анимация уже устарела
            try:
                new.place_forget()
                new.pack(fill="both", expand=True)
            except Exception:
                pass

        def step(i):
            try:
                if getattr(self, "_anim_gen", 0) != gen or not new.winfo_exists():
                    return
                if i > ANIM_TRANS_STEPS:
                    _settle()
                    return
                t = _ease_out_cubic(i / ANIM_TRANS_STEPS)
                new.place_configure(x=int(off * (1.0 - t)))
                self.root.after(ANIM_STEP_MS, lambda: step(i + 1))
            except Exception:
                _settle()

        step(1)

    def open_settings(self):
        self._refresh_settings_values()
        self._show_screen("settings")
        self._fit_window("settings")
        try:
            self.root.lift()
        except Exception:
            pass

    def close_settings(self):
        if self._hk_capturing:
            self._end_hotkey_capture()
        try:
            self.stop_monitor()
        except Exception:
            pass
        self._show_screen("main")
        self._fit_window("main")
        try:
            self.root.lift()
        except Exception:
            pass

    def _refresh_settings_values(self):
        if not self._hk_capturing:
            try:
                self.hk_field.configure(text=self.display_hotkey())
            except Exception:
                pass
        try:
            self.auto_var.set(ms.autostart_enabled())
        except Exception:
            pass
        devices = self._list_monitor_devices()
        if devices:
            names = [d["name"] for d in devices]
            try:
                self.mon_out_menu.configure(values=names)
                self.mon_out_menu.set(names[self._find_default_index(devices)])
            except Exception:
                pass
        if self.monitor is not None:
            try:
                self.mon_btn.configure(text=self.t("vac_mon_stop"), fg_color=DANGER,
                                       hover_color="#d95560")
            except Exception:
                pass
        else:
            try:
                self.mon_btn.configure(text=self.t("vac_mon_start"), fg_color=BTN, hover_color=BTN_HOVER)
            except Exception:
                pass
        routing = self.t("vac_active") if (self.cable_idx is not None and self.router is not None) else self.t("vac_inactive")
        try:
            self.vac_status_row.configure(
                text="VAC: " + (self.vac_name or self.t("vac_not_found")) + "    ·    " + routing)
        except Exception:
            pass

    # ═══════════════════════════ ЯЗЫК ═══════════════════════════
    def _on_lang_change(self, choice):
        """Сменить язык интерфейса."""
        new_lang = "ru" if choice == "Русский" else "en"
        if new_lang == self.lang:
            return
        self.lang = new_lang
        ms.save_lang(new_lang)
        self.retranslate()
        # Пересоздать трей (текст пунктов меню)
        self._rebuild_tray()

    def retranslate(self):
        """Обновить все тексты UI на текущий язык."""
        try:
            self.root.title(self.t("app_title"))
            # Главный экран
            self._title_lbl.configure(text=self.t("app_title"))
            self.hk_badge_lbl.configure(text=self.t("hotkey_badge", hk=self.display_hotkey()))
            self._sec_mics_lbl.configure(text=self.t("section_mics"))
            self._reset_vol_btn.configure(text=self.t("reset_vol"))
            self.switch_btn.configure(text=self.t("switch_btn", hk=self.display_hotkey()))
            self._btn_settings.configure(text=self.t("btn_settings"))
            self._btn_quit.configure(text=self.t("btn_quit"))
            self._hint_lbl.configure(text=self.t("hint_main"))
            self._footer_lbl.configure(text=self.t("footer", ver=VERSION))
            # VAC карточка
            self._vac_title_lbl.configure(text=self.t("vac_title"))
            self._vac_name_lbl.configure(text=(self.vac_name or self.t("vac_not_found")))
            self._vac_discord_btn.configure(text=self.t("vac_discord"))
            self._vac_windows_btn.configure(text=self.t("vac_windows"))
            # Настройки
            self._settings_footer.configure(text=self.t("footer", ver=VERSION))
            self._settings_title.configure(text=self.t("btn_settings"))
            self._btn_back.configure(text=self.t("btn_back"))
            self._settings_vac_title.configure(text=self.t("vac_title"))
            self._settings_test_btn.configure(text=self.t("vac_test_btn"))
            self._settings_mon_title.configure(text=self.t("vac_mon_title"))
            self._settings_mon_desc.configure(text=self.t("vac_mon_desc"))
            self._settings_mon_out_lbl.configure(text=self.t("vac_mon_out"))
            self.mon_btn.configure(text=self.t("vac_mon_start") if self.monitor is None else self.t("vac_mon_stop"))
            self._settings_hk_title.configure(text=self.t("sec_hotkey"))
            self._settings_hk_hint.configure(text=self.t("hk_hint"))
            self._settings_autostart_title.configure(text=self.t("sec_autostart"))
            self._autostart_chk.configure(text=self.t("autostart_chk"))
            self._settings_lang_title.configure(text=self.t("sec_lang"))
            # Статус-строка в заголовке
            self._update_header_status()
            self._update_vac_card()
            # Строки микрофонов (пересоздаём)
            self._build_mic_rows()
        except Exception:
            pass

    def _rebuild_tray(self):
        """Пересоздать трей с новым языком."""
        try:
            if self.tray_icon is not None:
                self.tray_icon.stop()
        except Exception:
            pass
        self._start_tray()

    # ═══════════════════════════ СПИСОК МИКРОФОНОВ ═══════════════════════════
    def _build_mic_rows(self):
        """Карточки микрофонов: активный — сверху, исключённые — вниз.

        ЛКМ — выбрать, колесо — громкость, тумблер / ПКМ — выключить (исключить из переключения).
        """
        for w in self.mic_list.winfo_children():
            w.destroy()
        self.mic_rows = []
        # VAC не показываем в списке: это приёмник звука, а не источник.
        mics = [m for m in self.mics
                if "virtual audio cable" not in (m.FriendlyName or "").lower()]
        if not mics:
            ctk.CTkLabel(self.mic_list, text=self.t("mics_empty"), font=F_CAP,
                         text_color=DIM, anchor="w").pack(anchor="w", pady=8)
            return

        def _rank(mic):
            excluded = self.is_excluded(mic)
            is_active = (not excluded) and (self.current is not None and mic.id == self.current.id)
            return 0 if is_active else (2 if excluded else 1)

        ordered = sorted(mics, key=lambda m: (_rank(m), mics.index(m)))
        divider_done = False
        for mic in ordered:
            excluded = self.is_excluded(mic)
            is_active = (not excluded) and (self.current is not None and mic.id == self.current.id)

            if excluded and not divider_done:
                ctk.CTkFrame(self.mic_list, fg_color=BORDER, height=1).pack(fill="x", pady=5)
                divider_done = True

            row_bg = ACCENT_SOFT if is_active else CARD
            if excluded:
                name_fg, name_font, tag, tag_fg, tag_bg = TEXT_3, F_CAP, self.t("mic_excluded"), DANGER, SURFACE_2
            else:
                name_fg, name_font = TEXT, (F_BODY_B if is_active else F_BODY)
                tag, tag_fg, tag_bg = "", TEXT_3, SURFACE_2

            card = ctk.CTkFrame(self.mic_list, fg_color=row_bg, corner_radius=14,
                                border_width=0 if is_active else 1,
                                border_color=BORDER)
            card.pack(fill="x", pady=3)

            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=14, pady=(8, 0))
            # Тумблер пакуем ПЕРВЫМ: он сразу бронирует место справа,
            # поэтому его не «съедает» длинное имя + пиллы (раньше на
            # активной карточке тумблер сжимался до нуля и исчезал).
            cb_var = tk.BooleanVar(value=not excluded)  # вкл = участвует в переключении
            # width/height = размер самого тумблера: иначе виджет по умолчанию
            # 100px шириной, а тумблер рисуется в его левом углу (виден отступ справа)
            cb = ctk.CTkSwitch(top, text="", variable=cb_var,
                               command=lambda m=mic: self.toggle_exclude(m),
                               progress_color=ACTIVE,
                               fg_color=BORDER,
                               button_color=TEXT, button_hover_color=TEXT,
                               switch_width=36, switch_height=20, corner_radius=999,
                               width=36, height=20)
            cb.pack(side="right", padx=(10, 0))

            accent = ctk.CTkFrame(top, width=3, height=22, corner_radius=2,
                                  fg_color=ACTIVE if is_active else (BORDER if not excluded else SURFACE_2))
            accent.pack(side="left", fill="y", padx=(0, 10))
            name_lbl = ctk.CTkLabel(top, text=mic.FriendlyName, font=name_font,
                                    text_color=name_fg, anchor="w")
            name_lbl.pack(side="left")
            dot = None
            dot_levels = None
            if is_active:
                # «Светящаяся» точка-индикатор: круглый свечной градиент,
                # мягко «дышит» (28 уровней яркости, период ~3.6 c)
                dot_levels = _glow_dot(ACTIVE, 20)
                if dot_levels is not None:
                    dot = ctk.CTkLabel(top, image=dot_levels[0], text="")
                    dot.pack(side="left", padx=(10, 0))

                    def _breathe(i, dt=dot, lv=dot_levels):
                        try:
                            if not dt.winfo_exists():
                                return
                            if getattr(self, "_fade_hidden", False):
                                self.root.after(120, lambda: _breathe(i + 1, dt, lv))
                                return
                            t = (1.0 - math.cos(math.pi * (i % 30) / 15.0)) / 2.0  # 0→1→0
                            dt.configure(image=lv[min(len(lv) - 1, int(t * (len(lv) - 1)))])
                            self.root.after(120, lambda: _breathe(i + 1, dt, lv))
                        except Exception:
                            pass

                    _breathe(0)
            elif tag:
                pill = ctk.CTkFrame(top, fg_color=tag_bg, corner_radius=999)
                pill.pack(side="left", padx=(8, 0))
                ctk.CTkLabel(pill, text=tag, font=F_MICRO, text_color=tag_fg).pack(padx=8, pady=3)
            # громкость (0–250%)
            vol_row = ctk.CTkFrame(card, fg_color="transparent")
            vol_row.pack(fill="x", padx=14, pady=(4, 8))
            ctk.CTkLabel(vol_row, text=self.t("vol_label"), font=F_MICRO, text_color=TEXT_3).pack(side="left", padx=(0, 8))
            vol = self.get_mic_volume(mic)
            stored = self.mic_vol.get(mic.id)
            val = int(stored) if stored is not None else (100 if vol is None else int(round(vol * 100)))
            slider = ctk.CTkSlider(vol_row, from_=0, to=250, number_of_steps=250,
                                   command=lambda v, m=mic: self._on_volume_change(m, v),
                                   progress_color=BTN, button_color=TEXT,
                                   button_hover_color=BTN, fg_color=BORDER, height=14)
            slider.pack(side="left", fill="x", expand=True)
            try:
                slider.set(val)
            except Exception:
                pass
            if vol is None and stored is None:
                slider.configure(state="disabled")
            val_lbl = ctk.CTkLabel(vol_row, text=str(val) + "%", font=F_CAP_B, text_color=DIM,
                                   width=44, anchor="e")
            val_lbl.pack(side="right", padx=(8, 0))

            # взаимодействия: ЛКМ — выбрать, ПКМ — исключить, колесо — громкость
            for wdg in (card, top, name_lbl):
                wdg.bind("<Button-1>", lambda e, m=mic: self.activate_mic(m))
                wdg.bind("<Double-Button-1>", lambda e, m=mic: self.activate_mic(m))
                wdg.bind("<Button-3>", lambda e, m=mic: self.toggle_exclude(m))
                wdg.bind("<MouseWheel>", lambda e, m=mic, s=slider: self._wheel_volume(e, m, s))
            # hover-эффект и курсор (у активных и исключённых — своя роль)
            if not is_active and not excluded:
                def _hov(e, c=card):
                    try:
                        c.configure(fg_color=SURFACE_2)
                    except Exception:
                        pass

                def _unhov(e, c=card):
                    try:
                        c.configure(fg_color=CARD)
                    except Exception:
                        pass

                for wdg in (card, top, name_lbl):
                    wdg.bind("<Enter>", _hov)
                    wdg.bind("<Leave>", _unhov)
            if not excluded:
                card.configure(cursor="hand2")
            self.mic_rows.append({"mic": mic, "card": card, "label": name_lbl,
                                  "slider": slider, "val": val_lbl, "cb": cb,
                                  "dot": dot, "dot_levels": dot_levels})
        self._resync_layout()

    def _resync_layout(self):
        """Подгонка в правильном порядке: высота списка → высота окна → скроллбар.
        Скроллбар проверяется последним — уже против финальной высоты канваса."""
        self._fit_mic_list()
        self._fit_window()
        self._maybe_hide_scrollbar()

    def _fit_mic_list(self):
        """Высота списка = высоте содержимого, пока микрофонов не больше MAX_VISIBLE_MICS.
        Дальше список ограничивается высотой пяти карточек и получает скроллбар."""
        try:
            self.mic_list.update_idletasks()
            bb = self.mic_list._parent_canvas.bbox("all")
            content = bb[3] if bb else 0
            if content <= 0:
                return  # окно ещё не отрисовано — подгоним позже
            n = max(1, len(self.mic_rows))
            if n <= MAX_VISIBLE_MICS:
                list_h = content + 10
            else:
                list_h = (content / n) * MAX_VISIBLE_MICS + 10
            list_h = max(110, min(1200, int(list_h)))
            if abs(int(self.mic_list.cget("height")) - list_h) > 4:
                self.mic_list.configure(height=list_h)
        except Exception:
            pass

    def _fit_window(self, screen_name=None):
        """Высота окна = максимум из высот основного и настроек.
        Оба экрана всегда одного размера — окно не «прыгает» при переключении."""
        try:
            self.root.update_idletasks()
            h = max(int(self.main.winfo_reqheight()),
                    int(self.settings.winfo_reqheight()))
            if h <= 100:
                return
            h = max(560, min(960, h))
            self.root.minsize(470, min(680, h))
            self.root.geometry("500x%d" % h)
        except Exception:
            pass

    def _maybe_hide_scrollbar(self):
        """Скроллбар показываем только если микрофоны не помещаются
        (больше MAX_VISIBLE_MICS)."""
        try:
            sb = self.mic_list._scrollbar
            canvas = self.mic_list._parent_canvas
            self.mic_list.update_idletasks()
            view_h = canvas.winfo_height()
            if view_h < 50:
                return  # окно ещё не отрисовано — проверим позже
            bb = canvas.bbox("all")
            if bb is None or bb[3] <= view_h + 2:
                sb.grid_remove()
            else:
                sb.grid()
        except Exception:
            pass

    def _wheel_volume(self, event, mic, slider):
        """Колесо мыши над карточкой — подкрутить громкость этого микрофона."""
        try:
            cur = int(slider.get())
        except Exception:
            cur = self.mic_vol.get(mic.id, 100)
        step = 5 if event.delta > 0 else -5
        nv = max(0, min(250, cur + step))
        try:
            slider.set(nv)
        except Exception:
            pass
        self._on_volume_change(mic, nv)
        return "break"

    def _on_volume_change(self, mic, value):
        try:
            val = float(value)
        except Exception:
            return
        val = max(0.0, min(250.0, val))
        self.mic_vol[mic.id] = int(round(val))
        for row in self.mic_rows:
            if row["mic"].id == mic.id and "val" in row:
                try:
                    row["val"].configure(text=str(int(round(val))) + "%")
                except Exception:
                    pass
                break
        if val <= 100.0:
            self.set_mic_volume(mic, val / 100.0)
        else:
            self.set_mic_volume(mic, 1.0)
            gain = self._gain_for(mic.id)
            if self.current is not None and mic.id == self.current.id and self.router is not None:
                self.router.set_gain(gain)
        ms.save_config(self.hotkey, self.exclude, self.mic_vol)

    def reset_volumes(self):
        for mic in self.mics:
            self.mic_vol[mic.id] = 100
            self.set_mic_volume(mic, 1.0)
        if self.current is not None and self.router is not None:
            try:
                self.router.set_gain(1.0)
            except Exception:
                pass
        ms.save_config(self.hotkey, self.exclude, self.mic_vol)
        self._animated_update(flash=False)
        self.show_notification("🎚 Громкость сброшена: все микрофоны 100%")

    def _flash_active(self):
        """Мягкий пульс рамки: плавное в-и-вы (2 фазы, ~240 мс)."""
        card = None
        for r in self.mic_rows:
            if r["mic"].id == self.current.id:
                card = r.get("card")
                break
        if card is None:
            return
        seq = getattr(self, "_flash_seq", 0) + 1
        self._flash_seq = seq
        steps = 12  # 12 × 20 мс = 240 мс

        rest_border = BORDER
        rest_bg     = ACCENT_SOFT
        peak_border = ACTIVE
        peak_bg     = _mix_hex(ACCENT_SOFT, BTN, 0.2)

        def _apply(intensity):
            try:
                bw = 2 if intensity > 0.05 else 0
                card.configure(
                    border_width=bw,
                    border_color=_mix_hex(rest_border, peak_border, intensity),
                    fg_color=_mix_hex(rest_bg, peak_bg, intensity))
            except Exception:
                pass

        def step(i):
            if seq != self._flash_seq or i > steps:
                return
            p = i / steps  # 0 → 1
            if p <= 0.5:
                intensity = _ease_out_cubic(p / 0.5)
            else:
                intensity = 1.0 - _ease_in_cubic((p - 0.5) / 0.5)
            _apply(intensity)
            if i < steps:
                self.root.after(ANIM_STEP_MS, lambda: step(i + 1))

        _apply(0.0)
        self.root.after(ANIM_STEP_MS, lambda: step(1))

    def _animated_update(self, flash=False):
        """Плавная смена списка микрофонов — кроссфейд.

        Карточки «растворяются» в цвет фона (fade-out, ease-in) →
        пересборка → проявление из фона (fade-in, ease-out) → мягкий
        пульс активной. Без шторки, бегущей линии и жёсткой вспышки.
        Сбой → мгновенный update_ui().
        """
        def _plain():
            try:
                self.update_ui()
                if flash:
                    self._flash_active()
            except Exception:
                pass

        try:
            if self.screen != "main" or self.mic_list.winfo_width() < 50:
                _plain()
                return
            seq = getattr(self, "_fade_seq", 0) + 1
            self._fade_seq = seq

            # Собираем текущие «окрашиваемые» виджеты
            old_specs = []
            for row in self.mic_rows:
                card = row.get("card")
                if card is not None:
                    _collect_faders(card, old_specs)

            # Скрываем точки (прозрачный placeholder того же размера)
            blank = _blank_image(20)
            self._fade_hidden = True
            for row in self.mic_rows:
                d = row.get("dot")
                if d is not None and blank is not None:
                    try:
                        d.configure(image=blank)
                    except Exception:
                        pass

            N_OUT = ANIM_FADE_OUT
            N_IN  = ANIM_FADE_IN

            def _begin_fade_in():
                # Пересборка выполнена — собираем новые виджеты
                new_specs = []
                for row in self.mic_rows:
                    card = row.get("card")
                    if card is not None:
                        _collect_faders(card, new_specs)
                self._fade_new_specs = new_specs
                # Скрываем новые точки
                if blank is not None:
                    for row in self.mic_rows:
                        d = row.get("dot")
                        if d is not None:
                            try:
                                d.configure(image=blank)
                            except Exception:
                                pass
                _apply_fade(new_specs, 0.0)
                self.root.update_idletasks()
                _fade_in(0)

            def _fade_in(i):
                if seq != self._fade_seq:
                    return
                new_specs = getattr(self, "_fade_new_specs", [])
                if i >= N_IN:
                    _apply_fade(new_specs, 1.0)
                    # Показываем точки
                    for row in self.mic_rows:
                        d = row.get("dot")
                        lv = row.get("dot_levels")
                        if d is not None and lv is not None:
                            try:
                                d.configure(image=lv[0])
                            except Exception:
                                pass
                    self._fade_hidden = False
                    if flash:
                        self._flash_active()
                    return
                t = _ease_out_cubic(i / max(1, N_IN - 1))
                _apply_fade(new_specs, t)
                self.root.after(ANIM_STEP_MS, lambda: _fade_in(i + 1))

            def _fade_out(i):
                if seq != self._fade_seq:
                    return
                if i >= N_OUT:
                    # Полностью растворились — пересобираем
                    try:
                        self.update_ui()
                        self.root.update_idletasks()
                    except Exception:
                        pass
                    _begin_fade_in()
                    return
                t = 1.0 - _ease_in_cubic(i / max(1, N_OUT - 1))
                _apply_fade(old_specs, t)
                self.root.after(ANIM_STEP_MS, lambda: _fade_out(i + 1))

            _apply_fade(old_specs, 1.0)  # гарантированно полный цвет на старте
            _fade_out(0)
        except Exception as e:
            try:
                import traceback as _tb
                self._log("_animated_update fallback: %r\n%s" % (e, _tb.format_exc()))
            except Exception:
                pass
            _plain()

    # ═══════════════════════════ ЛОГИКА ═══════════════════════════
    def get_enumerator(self):
        return ms.comtypes.CoCreateInstance(
            ms.CLSID_MMDeviceEnumerator, ms.IMMDeviceEnumerator,
            ms.comtypes.CLSCTX_INPROC_SERVER)

    def is_excluded(self, mic):
        name = mic.FriendlyName.lower()
        if "virtual audio cable" in name or "virtual cable" in name:
            return True
        return any(e in name for e in self.exclude)

    def refresh(self):
        enum = self.get_enumerator()
        coll = enum.EnumAudioEndpoints(ms.EDataFlow.eCapture.value, ms.DEVICE_STATE.ACTIVE.value)
        self.mics = []
        for i in range(coll.GetCount()):
            self.mics.append(ms.AudioUtilities.CreateDevice(coll.Item(i)))
        self.active = [m for m in self.mics if not self.is_excluded(m)]
        self.current = None
        if self.mics:
            try:
                cur = enum.GetDefaultAudioEndpoint(ms.EDataFlow.eCapture.value, ms.ERole.eConsole.value)
                cur_id = cur.GetId()
                for m in self.mics:
                    if m.id == cur_id:
                        self.current = m
                        break
            except Exception:
                pass
        if self.active:
            try:
                self.index = self.active.index(self.current)
            except (ValueError, AttributeError):
                self.index = 0
        else:
            self.index = 0
        _dbg("refresh: mics=%d active=%d current=%r idx=%s" % (
            len(self.mics), len(self.active),
            self.current.FriendlyName if self.current else None, self.index))

    def set_default(self):
        _dbg("set_default: target=%r" % self.active[self.index].FriendlyName)
        try:
            cfg = ms.comtypes.CoCreateInstance(
                ms.CLSID_CPolicyConfigClient, ms.IPolicyConfig,
                ms.comtypes.CLSCTX_INPROC_SERVER)
            cfg.SetDefaultEndpoint(self.active[self.index].id, ms.ERole.eConsole.value)
        except Exception as e:
            _dbg("set_default: FAILED: %r" % e)
            raise
        _dbg("set_default: ok")

    def _switch_to(self, mic):
        _dbg("_switch_to: enter -> %r" % mic.FriendlyName)
        prev = self.current
        self.set_default()
        self.current = mic
        vac_ok = True
        vac_err = None
        if self.cable_idx is not None:
            # Гарантированно останавливаем старый роутер
            if self.router is not None:
                try:
                    self.router.stop()
                except Exception:
                    pass
                self.router = None
            # Создаём новый роутер на целевой микрофон
            try:
                r = ms.CableRouter(self.cable_idx)
                if r.start(mic.FriendlyName):
                    r.set_gain(self._gain_for(mic.id))
                    self.router = r
                else:
                    vac_ok = False
                    vac_err = r.last_error or "не удалось запустить"
            except Exception as e:
                vac_ok = False
                vac_err = str(e)
        self._animated_update(flash=True)
        name = self._clean_mic_name(mic.FriendlyName)
        if self.router is not None and vac_ok:
            act = None
            if prev is not None and prev.id != mic.id and not self.is_excluded(prev):
                act = ("Отменить" if self.lang == "ru" else "Undo", lambda pv=prev: self._switch_to(pv))
            self.show_notification("🎤 " + name + "  →  " + self.t("vac_title"), action=act)
        elif self.router is not None and not vac_ok:
            self.show_notification("🎤 " + name + "   ⚠️ VAC: " + (vac_err or "?"))
        else:
            self.show_notification("🎤 " + name)

    def toggle(self):
        _dbg("toggle: enter (active=%s)" % (len(self.active) if self.active else 0))
        self.refresh()
        if not self.active:
            _dbg("toggle: no active mics — abort")
            return
        self.index = (self.index + 1) % len(self.active)
        _dbg("toggle: target=%r" % self.active[self.index].FriendlyName)
        self._switch_to(self.active[self.index])
        _dbg("toggle: done")

    def activate_mic(self, mic):
        if self.is_excluded(mic):
            return
        if mic not in self.active:
            self.refresh()
        if mic not in self.active:
            return
        self.index = self.active.index(mic)
        self._switch_to(mic)

    def toggle_exclude(self, mic):
        name = mic.FriendlyName.lower()
        if name in self.exclude:
            self.exclude.discard(name)
        else:
            self.exclude.add(name)
        ms.save_config(self.hotkey, self.exclude)
        self.refresh()
        self._animated_update(flash=False)
        if self.is_excluded(mic):
            self.show_notification("🎤 " + self.t("mic_excluded") + ": " + mic.FriendlyName)
        else:
            self.show_notification("🎤 ✓ " + mic.FriendlyName)

    # ---------- громкость ----------
    def get_mic_volume(self, mic):
        try:
            return float(mic.EndpointVolume.GetMasterVolumeLevelScalar())
        except Exception:
            return None

    def set_mic_volume(self, mic, frac):
        try:
            mic.EndpointVolume.SetMasterVolumeLevelScalar(max(0.0, min(1.0, float(frac))), None)
        except Exception:
            pass

    def _gain_for(self, mic_id):
        v = self.mic_vol.get(mic_id, 100)
        try:
            v = float(v)
        except Exception:
            return 1.0
        return (v / 100.0) if v > 100.0 else 1.0

    # ---------- горячая клавиша ----------
    def on_hotkey(self):
        _dbg("on_hotkey: called (thread=%s)" % threading.current_thread().name)
        self._hotkey_q.put(1)

    def _poll_hotkey(self):
        # Цикл опроса должен жить вечно: любая ошибка ловится, и повторный
        # after() ставится безусловно (иначе VU-метр и трей «замораживаются»).
        try:
            while True:
                self._hotkey_q.get_nowait()
                _dbg("poll: hotkey flag -> toggle()")
                self.toggle()
        except queue.Empty:
            pass
        except Exception as e:
            _dbg("poll: hotkey loop error: %r" % e)
        try:
            while True:
                cmd = self._tray_q.get_nowait()
                if cmd == "show":
                    self.restore()
                elif cmd == "quit":
                    self.quit_app()
        except queue.Empty:
            pass
        except Exception:
            pass
        try:
            self._update_level()
        except Exception:
            pass
        try:
            self.root.after(100, self._poll_hotkey)
        except Exception:
            pass
        self._poll_n = getattr(self, "_poll_n", 0) + 1
        if self._poll_n % 300 == 0:  # ~30 c
            try:
                _lr = self.listener.listener.is_running if self.listener else None
            except Exception:
                _lr = "?"
            _dbg("heartbeat: listener_is_running=%s" % _lr)

    def display_hotkey(self):
        s = self.hotkey.replace("<", "").replace(">", "")
        parts = [p.strip() for p in s.split("+") if p.strip()]
        if not parts:
            return self.hotkey
        names = {
            "ctrl": "Ctrl", "control": "Ctrl", "shift": "Shift", "alt": "Alt",
            "cmd": "Win", "command": "Win", "scroll_lock": "Scroll Lock",
            "caps_lock": "Caps Lock", "num_lock": "Num Lock",
            "print_screen": "Print Screen", "page_up": "PgUp", "page_down": "PgDn",
            "enter": "Enter", "space": "Space", "backspace": "Backspace",
            "tab": "Tab", "esc": "Esc", "delete": "Del", "pause": "Pause",
        }
        out = []
        for p in parts:
            if p in names:
                out.append(names[p])
            elif p.startswith("f") and p[1:].isdigit():
                out.append(p.upper())
            elif len(p) == 1:
                out.append(p.upper())
            else:
                out.append(p.replace("_", " ").capitalize())
        return "+".join(out)

    def _clean_mic_name(self, name):
        s = str(name).strip()
        m = re.match(r'^[^\s(]+\s*\((.+)\)$', s)
        if m:
            return m.group(1).strip()
        m = re.match(r'^[^\s(]+\s*\((.+)$', s)
        if m:
            return m.group(1).strip()
        return s

    # ---------- назначение горячей клавиши (захват нажатием) ----------
    def _begin_hotkey_capture(self):
        self._log("begin capture called")
        if self._hk_capturing:
            return
        self._hk_capturing = True
        self._log("begin capture")
        try:
            self.hk_field.configure(text=self.t("hk_press"),
                                    fg_color=ACTIVE, hover_color=ACTIVE, text_color="#05231a")
        except Exception:
            pass
        # Временно остановить глобальный слушатель, чтобы старая клавиша
        # не переключила микрофон прямо во время ввода.
        old = self.listener
        if old is not None:
            try:
                old.stop()
            except Exception:
                pass
        self._cap_old_listener = old
        try:
            self.root.update_idletasks()
            self.root.lift()
            self.root.focus_set()
            self.root.bind_all("<Key>", self._cap_on_key)
            self._log("tk capture bound")
        except Exception as e:
            self._end_hotkey_capture(restart_old=True)
            self._log("bind failed: %s" % e)
            from tkinter import messagebox
            messagebox.showerror(self.t("err_title"), self.t("err_hotkey_input", e=str(e)), parent=self.root)

    def _cap_on_key(self, event):
        if not self._hk_capturing:
            return
        if event.keysym == "Escape":
            self._log("capture cancelled")
            self._end_hotkey_capture(restart_old=True)
            return "break"
        if event.keysym in ms._TK_MOD_KEYS:
            self._set_cap_text(self.t("hk_add_main"))
            return "break"
        res = self._tk_key_to_spec(event)
        if res is None:
            self._cap_fail(self.t("hk_invalid"))
            return "break"
        mods, main = res
        full = "+".join(sorted(mods) + [main])
        try:
            ms.Hotkey(full, lambda: None)  # валидация
        except Exception as e:
            self._cap_fail(str(e))
            return "break"
        self._log("apply hotkey: %s" % full)
        self._cap_apply(full)
        return "break"

    def _tk_key_to_spec(self, event):
        state = event.state
        mods = []
        if state & 0x0001:
            mods.append("shift")
        if state & 0x0004:
            mods.append("ctrl")
        if state & 0x0008:
            mods.append("alt")
        if state & 0x0040:
            mods.append("cmd")
        keysym = event.keysym
        char = event.char
        if keysym in ms._TK_SPECIAL:
            main = ms._TK_SPECIAL[keysym]
        elif char and len(char) == 1:
            main = char.lower()
        else:
            return None
        return mods, main

    def _set_cap_text(self, t):
        try:
            self.hk_field.configure(text=t, fg_color=ACTIVE, hover_color=ACTIVE,
                                    text_color="#05231a")
        except Exception:
            pass

    def _cap_fail(self, msg):
        self._end_hotkey_capture(restart_old=True)
        from tkinter import messagebox
        messagebox.showerror(self.t("err_badkey_title"), msg, parent=self.root)

    def _cap_apply(self, full):
        self._hk_capturing = False
        try:
            self.root.unbind_all("<Key>")
        except Exception:
            pass
        self._cap_old_listener = None
        self._apply_hotkey(full)

    def _end_hotkey_capture(self, restart_old=True):
        self._hk_capturing = False
        try:
            self.root.unbind_all("<Key>")
        except Exception:
            pass
        old = self._cap_old_listener
        self._cap_old_listener = None
        if restart_old and old is not None:
            try:
                old.start()
            except Exception:
                pass
        try:
            self.hk_field.configure(text=self.display_hotkey(),
                                    fg_color=SURFACE_2, hover_color=ACCENT_SOFT, text_color=TEXT)
        except Exception:
            pass

    def _apply_hotkey(self, spec):
        self.hotkey = spec
        ms.save_config(self.hotkey, self.exclude, self.mic_vol)
        if self.listener is not None:
            try:
                self.listener.stop()
            except Exception:
                pass
        self.listener = ms.Hotkey(spec, self.on_hotkey)
        self.listener.start()
        try:
            self.hk_badge_lbl.configure(text=self.t("hotkey_badge", hk=self.display_hotkey()))
            self.switch_btn.configure(text=self.t("switch_btn", hk=self.display_hotkey()))
            self.hk_field.configure(text=self.display_hotkey(),
                                    fg_color=SURFACE_2, hover_color=ACCENT_SOFT, text_color=TEXT)
        except Exception:
            pass
        self.show_notification(self.t("toast_hotkey", hk=self.display_hotkey()))

    def _log(self, msg):
        try:
            base = os.path.dirname(sys.executable if getattr(sys, "frozen", False)
                                   else os.path.abspath(__file__))
            with open(os.path.join(base, "mic_switcher_err.log"), "a", encoding="utf-8") as f:
                f.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
        except Exception:
            pass

    # ---------- Discord / Windows ----------
    def open_discord_voice_settings(self):
        try:
            os.startfile("discord://-/settings/voice")
        except Exception:
            pass
        threading.Thread(target=self._raise_discord, daemon=True).start()

    def open_windows_sound_settings(self):
        for uri in ("ms-settings:sound", "control mmsys.cpl"):
            try:
                os.startfile(uri)
                return
            except Exception:
                continue

    def _raise_discord(self):
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = None
        for _ in range(30):
            hwnd = ms._find_discord_hwnd()
            if hwnd:
                break
            time.sleep(0.1)
        if not hwnd:
            return
        SW_RESTORE = 9
        attached = False
        cur_tid = 0
        fore_tid = 0
        try:
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
            fore = user32.GetForegroundWindow()
            cur_tid = kernel32.GetCurrentThreadId()
            if fore:
                fore_tid = user32.GetWindowThreadProcessId(fore, None)
                if fore_tid and fore_tid != cur_tid:
                    user32.AttachThreadInput(cur_tid, fore_tid, True)
                    attached = True
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass
        finally:
            if attached:
                try:
                    user32.AttachThreadInput(cur_tid, fore_tid, False)
                except Exception:
                    pass

    # ---------- уведомления ----------
    def show_notification(self, text, action=None):
        """Тост в правом верхнем углу экрана. action — (label, callback)."""
        if self.popup is not None:
            try:
                self.popup.destroy()
            except Exception:
                pass
            self.popup = None
        try:
            p = ctk.CTkToplevel(self.root)
            p.overrideredirect(True)
            p.attributes("-topmost", True)
            # Окно-подложка того же цвета, что карточка; скругление углов окна
            # вырезает SetWindowRgn (см. _round_window) — по-настоящему прозрачные углы
            p.configure(bg=CARD)
            card = ctk.CTkFrame(p, fg_color=CARD, corner_radius=0, border_width=1, border_color=BORDER)
            card.pack(fill="both", expand=True)
            warn = ("⚠" in text)
            bar = ctk.CTkFrame(card, width=4, height=1, fg_color=WARNING if warn else BTN, corner_radius=2)
            bar.pack(side="left", fill="y", padx=(6, 0), pady=8)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(side="left", padx=10, pady=8)
            text_lbl = ctk.CTkLabel(inner, text=text, text_color=TEXT, font=F_BODY_B,
                                    anchor="w", justify="left")
            text_lbl.pack(fill="x", anchor="w")
            if action is not None:
                lbl, cb = action

                def _do(c=cb, p=p):
                    try:
                        p.destroy()
                    except Exception:
                        pass
                    if self.popup is p:
                        self.popup = None
                    if c is not None:
                        c()

                b = ctk.CTkButton(inner, text=lbl, command=_do, fg_color=BTN,
                                  hover_color=BTN_HOVER, text_color="white",
                                  corner_radius=8, height=24, width=88, font=F_CAP_B)
                b.pack(anchor="w", pady=(8, 0))
            p.update_idletasks()
            w = max(p.winfo_reqwidth(), 200)  # широкая, плоская плашка — текст в одну строку
            h = max(p.winfo_reqheight(), 48)
            sw = self.root.winfo_screenwidth()
            x = max(sw - w - 24, 0)
            y = 24
            p.withdraw()
            p.geometry("%dx%d+%d+%d" % (w, h, x, y - h))  # стартует над краем экрана
            p.deiconify()
            p.update_idletasks()
            _round_window(p, 14)
            self.popup = p

            def _toast_out(pl):
                """Плавное улетание тоста вверх."""
                def out_step(i):
                    try:
                        if not pl.winfo_exists():
                            return
                        if i > ANIM_TOAST_OUT:
                            pl.destroy()
                            if self.popup is pl:
                                self.popup = None
                            return
                        t = _ease_in_cubic(i / ANIM_TOAST_OUT)
                        pl.geometry("%dx%d+%d+%d" % (w, h, x, int(y - h * t)))
                        pl.after(ANIM_STEP_MS, lambda: out_step(i + 1))
                    except Exception:
                        try:
                            pl.destroy()
                        except Exception:
                            pass
                out_step(1)

            def toast_in(i):
                try:
                    if not p.winfo_exists():
                        return
                    if i > ANIM_TOAST_IN:
                        p.after(4200 if action else 2600, lambda: _toast_out(p) if self.popup is p else None)
                        return
                    t = _ease_out_cubic(i / ANIM_TOAST_IN)
                    p.geometry("%dx%d+%d+%d" % (w, h, x, int((y - h) + h * t)))
                    p.after(ANIM_STEP_MS, lambda: toast_in(i + 1))
                except Exception:
                    pass

            toast_in(1)
        except Exception:
            pass

    # ---------- окно / трей ----------
    def quit_app(self):
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        if self.listener is not None:
            try:
                self.listener.stop()
            except Exception:
                pass
        if self.router is not None:
            try:
                self.router.stop()
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def hide_window(self):
        self.hidden = True
        if self.tray_icon is not None:
            self.root.withdraw()
        else:
            self.root.iconify()

    def restore(self):
        self.hidden = False
        if self.popup is not None:
            try:
                self.popup.destroy()
            except Exception:
                pass
            self.popup = None
        self.root.deiconify()
        try:
            self.root.lift()
        except Exception:
            pass

    def _start_tray(self):
        try:
            import pystray
            img = get_tray_image()
            show_item = pystray.MenuItem(self.t("tray_show"), self._tray_show, default=True)
            quit_item = pystray.MenuItem(self.t("tray_quit"), self._tray_quit)
            self.tray_icon = pystray.Icon("MicSwitcher", img, self.t("tray_tooltip"),
                                          pystray.Menu(show_item, quit_item))
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as e:
            print("tray error:", e)
            self.tray_icon = None

    def _tray_show(self, icon, item):
        self._tray_q.put("show")

    def _tray_quit(self, icon, item):
        self._tray_q.put("quit")

    # ---------- обновление UI ----------
    def update_ui(self):
        self._build_mic_rows()
        self._update_header_status()
        self._update_vac_card()

    def _update_header_status(self):
        try:
            if self.router is not None and self.current is not None:
                self.hdr_dot.configure(text_color=ACTIVE)
                self.hdr_sub.configure(text=self.t("vac_status_active", name=self._clean_mic_name(self.current.FriendlyName)))
            elif getattr(self, "cable_idx", None) is not None:
                self.hdr_dot.configure(text_color=WARNING)
                self.hdr_sub.configure(text=self.t("vac_status_inactive"))
            else:
                self.hdr_dot.configure(text_color=DANGER)
                self.hdr_sub.configure(text=self.t("vac_status_novac"))
        except Exception:
            pass

    def _update_vac_card(self):
        try:
            if self.cable_idx is not None and self.router is not None:
                txt, fg, bg = self.t("vac_active"), ACTIVE, ACCENT_SOFT
            elif self.cable_idx is not None:
                txt, fg, bg = self.t("vac_inactive"), WARNING, SURFACE_2
            else:
                txt, fg, bg = self.t("vac_unavailable"), DANGER, SURFACE_2
            self.vac_status_lbl.configure(text=txt, text_color=fg)
            self.vac_status_pill.configure(fg_color=bg)
        except Exception:
            pass

    def _update_level(self):
        try:
            target = 0.0
            if self.router is not None and self.current is not None:
                # усиление: обычная речь (пик 0.05–0.3) должна заметно двигать бар
                target = max(0.0, min(1.0, float(self.router.level) * 3.5))
            if target > self._lvl:
                self._lvl = 0.6 * target + 0.4 * self._lvl
            else:
                self._lvl = 0.25 * target + 0.75 * self._lvl
            frac = max(0.0, min(1.0, self._lvl))
            self.vu_set(frac)
            if frac > 0.97:
                col = DANGER
            elif frac > 0.8:
                col = WARNING
            else:
                col = ACTIVE
            self.vu.configure(progress_color=col)
        except Exception:
            pass

    # ---------- настройки: виртуальный микрофон ----------
    def _find_vac_capture(self):
        """Устройство захвата VAC (предпочитаем WASAPI), или None."""
        w = ms._wasapi_hostapi()
        cap = None
        try:
            for d in sd.query_devices():
                if d["max_input_channels"] > 0 and "virtual audio cable" in d["name"].lower():
                    if w is not None and d["hostapi"] == w:
                        return d
                    if cap is None:
                        cap = d
        except Exception:
            pass
        return cap

    def _list_monitor_devices(self):
        cap = self._find_vac_capture()
        cap_api = cap["hostapi"] if cap else None
        devices = ms.list_output_devices()
        if cap_api is not None:
            compat = [d for d in devices if d["hostapi"] == cap_api]
            if compat:
                devices = compat
        self._mon_devices = devices
        self._mon_by_name = {d["name"]: d for d in devices}
        return devices

    def _find_default_index(self, devices):
        """Индекс в `devices` устройства вывода, выбранного по умолчанию в Windows."""
        try:
            out_idx = sd.default.device[1]
            if out_idx is None:
                return 0
            def_name = sd.query_devices(out_idx)["name"]
        except Exception:
            return 0
        names = [d["name"] for d in devices]
        if def_name in names:
            return names.index(def_name)
        best, best_len = 0, 0
        for i, n in enumerate(names):
            if n and (n.startswith(def_name) or def_name.startswith(n)):
                common = min(len(n), len(def_name))
                if common > best_len:
                    best_len, best = common, i
        return best

    def _set_status(self, lbl, text, color=None):
        """Статус-строка: с текстом — видна, пустая — свёрнута (без дыры в карточке)."""
        try:
            if text:
                lbl.configure(text=text, text_color=color or DIM, height=25)
            else:
                lbl.configure(text="", height=1)
        except Exception:
            pass

    def test_virtual_mic(self):
        self._set_status(self.vac_test_lbl, self.t("vac_test_checking"), DIM)
        threading.Thread(target=self._run_vac_test, daemon=True).start()

    def _run_vac_test(self):
        """Round-trip: пишем тон в выход VAC и считываем с входа. Громко => работает."""
        import numpy as np
        render = ms.find_cable_input()
        cap = self._find_vac_capture()
        if render is None or cap is None:
            self.root.after(0, lambda: self._set_status(
                self.vac_test_lbl, self.t("vac_test_notfound"), WARNING))
            return
        sr = 48000
        nch = max(1, int(cap["max_input_channels"]))
        collected = []

        def incb(indata, frames, t_, status):
            collected.append(indata.copy())

        pos = [0]

        def outcb(outdata, frames, t_, status):
            i = np.arange(pos[0], pos[0] + frames) / sr
            pos[0] += frames
            mono = (0.3 * np.sin(2 * np.pi * 440 * i)).astype("float32")
            if outdata.shape[1] == 1:
                outdata[:] = mono.reshape(-1, 1)
            else:
                outdata[:] = np.stack([mono, mono], axis=1)

        try:
            in_s = sd.InputStream(samplerate=sr, device=cap["index"], channels=nch,
                                  dtype="float32", callback=incb)
            out_s = sd.OutputStream(samplerate=sr, device=render, channels=2,
                                   dtype="float32", callback=outcb)
            in_s.start(); out_s.start()
            time.sleep(1.8)
            out_s.stop(); out_s.close()
            in_s.stop(); in_s.close()
        except Exception as e:
            self.root.after(0, lambda e=e: self._set_status(
                self.vac_test_lbl, self.t("vac_test_error", e=str(e)), WARNING))
            return
        arr = np.concatenate(collected) if collected else np.zeros((1, nch), "float32")
        rms = float(np.sqrt(np.mean(arr ** 2)))
        if rms > 5e-3:
            msg = self.t("vac_test_ok", rms="%.3f" % rms)
            self.root.after(0, lambda: self._set_status(self.vac_test_lbl, msg, ACTIVE))
        else:
            msg = self.t("vac_test_weak", rms="%.6f" % rms, vac=self.vac_name)
            self.root.after(0, lambda: self._set_status(self.vac_test_lbl, msg, WARNING))

    # ---------- прослушка виртуального микрофона ----------
    def _mon_set(self, text, fg=DIM):
        self._set_status(self.mon_lbl, text, fg)

    def toggle_monitor(self):
        if self.monitor is not None:
            self.stop_monitor()
            return
        self.start_monitor()

    def start_monitor(self):
        cap = self._find_vac_capture()
        if cap is None:
            self._mon_set(self.t("vac_test_notfound"), WARNING)
            return
        name = self.mon_out_menu.get().strip()
        out = self._mon_by_name.get(name)
        if out is None:
            self._mon_set(self.t("mon_select_out"), WARNING)
            return
        if out["hostapi"] != cap["hostapi"]:
            compat = [d for d in self._mon_devices if d["hostapi"] == cap["hostapi"]]
            if compat:
                out = compat[0]
        try:
            m = ms.CableMonitor(cap["index"], out["index"])
            if not m.start():
                self._mon_set(self.t("mon_start_fail", e=(m.last_error or "")), WARNING)
                return
        except Exception as e:
            self._mon_set(self.t("mon_start_fail", e=str(e)), WARNING)
            return
        self.monitor = m
        try:
            self.mon_btn.configure(text=self.t("vac_mon_stop"), fg_color=DANGER, hover_color="#d95560")
        except Exception:
            pass
        self._mon_set(self.t("mon_listening", name=out["name"]), ACTIVE)

    def stop_monitor(self):
        if self.monitor is not None:
            try:
                self.monitor.stop()
            except Exception:
                pass
            self.monitor = None
        try:
            self.mon_btn.configure(text=self.t("vac_mon_start"), fg_color=BTN, hover_color=BTN_HOVER)
        except Exception:
            pass
        self._mon_set(self.t("mon_stopped"), DIM)

    # ---------- автозапуск ----------
    def _apply_autostart(self):
        on = bool(self.auto_var.get())
        ms.set_autostart(on)
        self.show_notification(self.t("toast_autostart_on" if on else "toast_autostart_off"))


# Шрифты (заполняются в App.__init__ после создания окна)
F_TITLE = F_H2 = F_BODY = F_BODY_B = F_CAP = F_CAP_B = F_MICRO = F_BTN = None


_mutex = None


def main():
    global _mutex
    # Защита от запуска второго экземпляра (иначе горячая клавиша сработает дважды)
    _dbg("main: start (pid=%s)" % os.getpid())
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\MicSwitcher_SingleInstance")
    _gle = ctypes.windll.kernel32.GetLastError()
    _dbg("main: mutex created, gle=%s" % _gle)
    if _gle == 183:  # ERROR_ALREADY_EXISTS
        from tkinter import messagebox
        lang = ms.load_lang()
        d = STRINGS.get(lang, STRINGS["ru"])
        messagebox.showinfo(
            d.get("app_title", "Mic Switcher"),
            d.get("msg_already_run", "Already running"),
        )
        return

    app = App()
    _dbg("main: App() ok, hotkey=%r" % app.hotkey)
    app.listener = ms.Hotkey(app.hotkey, app.on_hotkey)
    _dbg("main: Hotkey created")
    app.listener.start()
    try:
        _running = app.listener.listener.is_running
    except Exception:
        _running = "?"
    _dbg("main: listener.start() done, is_running=%s" % _running)
    print("Горячая клавиша: %s" % app.display_hotkey())
    app.root.mainloop()


if __name__ == "__main__":
    main()
