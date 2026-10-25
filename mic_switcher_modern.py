# -*- coding: utf-8 -*-
"""
Переключатель микрофонов — современный интерфейс (CustomTkinter).

Вся аудио-логика, конфиг, горячая клавиша и роутинг VAC переиспользуются
импортом из mic_switcher.py (чистые модульные сущности). Здесь — только
новый UI-класс App и main() с single-instance mutex.
"""
import ctypes
import json
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
    line = "[%s] %s\n" % (time.strftime("%H:%M:%S"), msg)
    # Для собранного exe пишем рядом с самим exe: TEMP может указывать не туда
    # (напр. запуск из сервисной сессии), а папка onedir всегда на виду у юзера.
    tries = []
    if getattr(sys, "frozen", False):
        try:
            tries.append(os.path.join(os.path.dirname(sys.executable), "micswitcher_debug.log"))
        except Exception:
            pass
    tries.append(os.path.join(os.environ.get("TEMP") or os.environ.get("TMP") or ".",
                              "micswitcher_debug.log"))
    for p in tries:
        try:
            with open(p, "a", encoding="utf-8") as f:
                f.write(line)
            return
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────
# Оформление: темы в стиле Discord.
# Палитры повторяют фирменные цвета клиента Discord (Dark / Light /
# Midnight) и подхватываются из установленного Discord автоматически.
# ─────────────────────────────────────────────────────────────
THEMES = {
    # Discord Dark — «классическая» тёмная тема клиента
    "dark": {
        "bg": "#313338",           # фон переписки
        "card": "#2B2D31",         # карточки / панели
        "surface2": "#35373C",     # hover-поверхность
        "card_hover": "#35373C",
        "border": "#1E1F22",       # разделители
        "text": "#F2F3F5",
        "dim": "#B5BAC1",
        "text3": "#949BA4",
        "btn": "#5865F2",          # blurple
        "btn_hover": "#4752C4",
        "active": "#23A55A",       # «онлайн»-зелёный
        "accent_soft": "#3C4076",  # выделенная карточка (blurple-тон)
        "danger": "#DA373C",
        "danger_hover": "#A12828",
        "warning": "#F0B232",
        "keycap_bg": "#1E1F22",
        "keycap_border": "#3F4147",
        "btn2": "#4E5058",         # вторичная кнопка Discord
        "btn2_hover": "#6D6F78",
        "btn2_text": "#FFFFFF",
        "track": "#4E5058",        # дорожка слайдера
        "input": "#1E1F22",        # выпадающие списки
        "on_accent": "#FFFFFF",
        "switch_off": "#80848E",
    },
    # Discord Light
    "light": {
        "bg": "#FFFFFF",
        "card": "#F2F3F5",
        "surface2": "#E9EAED",
        "card_hover": "#E9EAED",
        "border": "#E3E5E8",
        "text": "#060607",
        "dim": "#4E5058",
        "text3": "#80848E",
        "btn": "#5865F2",
        "btn_hover": "#4752C4",
        "active": "#248046",
        "accent_soft": "#E7E8FD",
        "danger": "#D83C3E",
        "danger_hover": "#B03234",
        "warning": "#C27C0E",
        "keycap_bg": "#E3E5E8",
        "keycap_border": "#D4D7DC",
        "btn2": "#E3E5E8",
        "btn2_hover": "#D4D7DC",
        "btn2_text": "#060607",
        "track": "#D4D7DC",
        "input": "#FFFFFF",
        "on_accent": "#FFFFFF",
        "switch_off": "#B5BAC1",
    },
    # Discord Midnight — почти чёрная тема
    "midnight": {
        "bg": "#000000",
        "card": "#0E0F11",
        "surface2": "#1A1B1E",
        "card_hover": "#1A1B1E",
        "border": "#232529",
        "text": "#F2F3F5",
        "dim": "#B5BAC1",
        "text3": "#949BA4",
        "btn": "#5865F2",
        "btn_hover": "#4752C4",
        "active": "#23A55A",
        "accent_soft": "#26273D",
        "danger": "#DA373C",
        "danger_hover": "#A12828",
        "warning": "#F0B232",
        "keycap_bg": "#1A1B1E",
        "keycap_border": "#2B2D31",
        "btn2": "#2B2D31",
        "btn2_hover": "#3F4147",
        "btn2_text": "#FFFFFF",
        "track": "#2B2D31",
        "input": "#1A1B1E",
        "on_accent": "#FFFFFF",
        "switch_off": "#80848E",
    },
}
THEME_ORDER = ("dark", "light", "midnight")

# Текущие цвета (перезаписываются apply_palette при смене темы)
BG = CARD = SURFACE_2 = CARD_HOVER = BORDER = TEXT = DIM = TEXT_3 = "#000000"
BTN = BTN_HOVER = ACTIVE = ACCENT_SOFT = DANGER = DANGER_HOVER = WARNING = "#000000"
KEYCAP_BG = KEYCAP_BORDER = BTN2 = BTN2_HOVER = BTN2_TEXT = TRACK = INPUT_BG = "#000000"
ON_ACCENT = "#FFFFFF"
SWITCH_OFF = "#80848E"
FONT = ms.FONT


def apply_palette(name):
    """Применить именованную тему."""
    return apply_palette_dict(THEMES.get(name) or THEMES["dark"])


def apply_palette_dict(pal):
    """Применить готовую палитру (в т.ч. снятую с окна Discord)."""
    global BG, CARD, SURFACE_2, CARD_HOVER, BORDER, TEXT, DIM, TEXT_3
    global BTN, BTN_HOVER, ACTIVE, ACCENT_SOFT, DANGER, DANGER_HOVER, WARNING
    global KEYCAP_BG, KEYCAP_BORDER, BTN2, BTN2_HOVER, BTN2_TEXT, TRACK, INPUT_BG, ON_ACCENT, SWITCH_OFF
    BG = pal["bg"]
    CARD = pal["card"]
    SURFACE_2 = pal["surface2"]
    CARD_HOVER = pal["card_hover"]
    BORDER = pal["border"]
    TEXT = pal["text"]
    DIM = pal["dim"]
    TEXT_3 = pal["text3"]
    BTN = pal["btn"]
    BTN_HOVER = pal["btn_hover"]
    ACTIVE = pal["active"]
    ACCENT_SOFT = pal["accent_soft"]
    DANGER = pal["danger"]
    DANGER_HOVER = pal["danger_hover"]
    WARNING = pal["warning"]
    KEYCAP_BG = pal["keycap_bg"]
    KEYCAP_BORDER = pal["keycap_border"]
    BTN2 = pal["btn2"]
    BTN2_HOVER = pal["btn2_hover"]
    BTN2_TEXT = pal["btn2_text"]
    TRACK = pal["track"]
    INPUT_BG = pal["input"]
    ON_ACCENT = pal["on_accent"]
    SWITCH_OFF = pal["switch_off"]
    return pal


apply_palette("dark")


# ─────────────────────────────────────────────────────────────
# Тема Discord: чтение выбранного в клиенте оформления
# ─────────────────────────────────────────────────────────────
DISCORD_THEME_RE = re.compile(rb'"(midnight|darker|onyx|dark|light|system|auto)"')


def discord_roots():
    """Папки данных установленных клиентов Discord."""
    appdata = os.environ.get("APPDATA") or ""
    if not appdata:
        return []
    out = []
    seen = set()
    for name in ("discord", "Discord", "discordptb", "DiscordPTB",
                 "discordcanary", "DiscordCanary"):
        p = os.path.join(appdata, name)
        key = os.path.normcase(p)
        if key in seen or not os.path.isdir(p):
            continue
        seen.add(key)
        out.append(p)
    return out


def discord_leveldb_dirs():
    """Каталоги localStorage клиента Discord (там лежит настройка темы)."""
    return [os.path.join(r, "Local Storage", "leveldb") for r in discord_roots()
            if os.path.isdir(os.path.join(r, "Local Storage", "leveldb"))]


def _windows_is_light():
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            v, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
            return bool(v)
    except Exception:
        return False


def norm_theme(value):
    """Название темы Discord -> ключ палитры приложения."""
    v = (value or "").lower()
    if v in ("midnight", "darker", "onyx"):
        return "midnight"
    if v == "light":
        return "light"
    if v in ("system", "auto"):
        return "light" if _windows_is_light() else "dark"
    return "dark"


def discord_stamp():
    """Отпечаток свежести настроек Discord (для слежения за сменой темы)."""
    best = 0.0
    for d in discord_leveldb_dirs():
        try:
            for name in os.listdir(d):
                try:
                    best = max(best, os.path.getmtime(os.path.join(d, name)))
                except Exception:
                    pass
        except Exception:
            pass
    return best


def _extract_discord_theme(data):
    """Достать тему из блоба настроек внешнего вида Discord.

    В localStorage Discord лежит запись вида
      {"appearance":{"shouldSync":false,"settings":{"theme":"dark",
        "clientThemeSettings":{...},"developerMode":false}}}
    Клиентская тема (Midnight и подобные) важнее базовой dark/light.
    """
    idx = data.find(b'"appearance"')
    if idx < 0:
        idx = data.find(b"appearance")
    if idx < 0:
        return None
    blob = data[idx:idx + 3000]
    # 1) клиентская тема, если она включена (внутри clientThemeSettings)
    m = re.search(rb'"clientThemeSettings"\s*:\s*\{[^{}]{0,400}?"theme"\s*:\s*"([a-z_]+)"', blob)
    if m:
        return m.group(1).decode("ascii", "replace")
    # 2) обычная тема dark/light
    m = re.search(rb'"theme"\s*:\s*"([a-z_]+)"', blob)
    if m:
        return m.group(1).decode("ascii", "replace")
    return None


def detect_discord_theme():
    """Тема, выбранная в Discord: (ключ палитры, путь к файлу) или (None, None)."""
    for d in discord_leveldb_dirs():
        try:
            names = [n for n in os.listdir(d) if n.endswith((".ldb", ".log"))]
        except Exception:
            continue
        files = []
        for n in names:
            p = os.path.join(d, n)
            try:
                files.append((os.path.getmtime(p), p))
            except Exception:
                pass
        # .log — свежие записи без сжатия, .ldb — старые блоки: свежие проверяем первыми
        files.sort(key=lambda x: (x[0], x[1].endswith(".log")), reverse=True)
        counts = {"midnight": 0, "dark": 0, "light": 0}
        for _, p in files[:8]:
            try:
                with open(p, "rb") as f:
                    data = f.read(8 * 1024 * 1024)
            except Exception:
                continue
            val = _extract_discord_theme(data)
            if val:
                _dbg("theme: discord=%s (%s)" % (val, os.path.basename(p)))
                return norm_theme(val), p
            # Запасной путь: каких значений темы в файле больше
            counts["midnight"] += data.count(b'"midnight"')
            counts["dark"] += data.count(b'"dark"')
            counts["light"] += data.count(b'"light"')
        if counts["midnight"]:
            return "midnight", None
        if counts["dark"] > counts["light"]:
            return "dark", None
        if counts["light"]:
            return "light", None
    return None, None


# ─────────────────────────────────────────────────────────────
# Тема по фактическим цветам окна Discord.
# Локальный JSON хранит только базовую dark/light, а выбранная
# клиентская тема (например «Пепел») видна лишь на экране — поэтому
# снимаем фон и панели прямо с окна и строим палитру из них.
# ─────────────────────────────────────────────────────────────
def _hex_to_rgb(hex_color):
    h = (hex_color or "").lstrip("#")
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:
        return (0, 0, 0)


def _rgb_to_hex(rgb):
    return "#%02X%02X%02X" % (max(0, min(255, int(round(rgb[0])))),
                              max(0, min(255, int(round(rgb[1])))),
                              max(0, min(255, int(round(rgb[2])))))


def _mix(c1, c2, t):
    return (c1[0] + (c2[0] - c1[0]) * t,
            c1[1] + (c2[1] - c1[1]) * t,
            c1[2] + (c2[2] - c1[2]) * t)


def _color_dist(c1, c2):
    return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5


def _luminance(rgb):
    r, g, b = [v / 255.0 for v in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def palette_from_colors(bg_rgb, panel_rgb):
    """Собрать полную палитру из фона чата и цвета панелей Discord."""
    dark = _luminance(bg_rgb) < 0.5
    if _color_dist(bg_rgb, panel_rgb) < 8:
        panel_rgb = _mix(bg_rgb, (255, 255, 255) if dark else (0, 0, 0), 0.05)
    white, black = (255, 255, 255), (0, 0, 0)
    if dark:
        card = panel_rgb
        card_hover = _mix(card, white, 0.07)
        surface2 = _mix(card, white, 0.07)
        border = _mix(panel_rgb, black, 0.35)
        keycap_bg = _mix(panel_rgb, black, 0.35)
        keycap_border = _mix(panel_rgb, white, 0.12)
        btn2 = _mix(panel_rgb, white, 0.14)
        btn2_hover = _mix(panel_rgb, white, 0.26)
        btn2_text = "#FFFFFF"
        track = _mix(panel_rgb, white, 0.16)
        input_bg = _mix(panel_rgb, black, 0.28)
        text, dim, text3 = "#F2F3F5", "#B5BAC1", "#949BA4"
        active = "#23A55A"
        danger, danger_hover = "#DA373C", "#A12828"
        warning = "#F0B232"
        switch_off = "#80848E"
        accent_soft = _mix(card, _hex_to_rgb("#5865F2"), 0.30)
    else:
        card = panel_rgb
        card_hover = _mix(card, black, 0.05)
        surface2 = _mix(card, black, 0.05)
        border = _mix(bg_rgb, black, 0.12)
        keycap_bg = _mix(bg_rgb, black, 0.06)
        keycap_border = _mix(bg_rgb, black, 0.12)
        btn2 = _mix(bg_rgb, black, 0.08)
        btn2_hover = _mix(bg_rgb, black, 0.16)
        btn2_text = "#060607"
        track = _mix(bg_rgb, black, 0.12)
        input_bg = "#FFFFFF"
        text, dim, text3 = "#060607", "#4E5058", "#80848E"
        active = "#248046"
        danger, danger_hover = "#D83C3E", "#B03234"
        warning = "#C27C0E"
        switch_off = "#B5BAC1"
        accent_soft = _mix(card, _hex_to_rgb("#5865F2"), 0.18)
    return {
        "bg": _rgb_to_hex(bg_rgb),
        "card": _rgb_to_hex(card),
        "surface2": _rgb_to_hex(surface2),
        "card_hover": _rgb_to_hex(card_hover),
        "border": _rgb_to_hex(border),
        "text": text,
        "dim": dim,
        "text3": text3,
        "btn": "#5865F2",
        "btn_hover": "#4752C4",
        "active": active,
        "accent_soft": _rgb_to_hex(accent_soft),
        "danger": danger,
        "danger_hover": danger_hover,
        "warning": warning,
        "keycap_bg": _rgb_to_hex(keycap_bg),
        "keycap_border": _rgb_to_hex(keycap_border),
        "btn2": _rgb_to_hex(btn2),
        "btn2_hover": _rgb_to_hex(btn2_hover),
        "btn2_text": btn2_text,
        "track": _rgb_to_hex(track),
        "input": _rgb_to_hex(input_bg),
        "on_accent": "#FFFFFF",
        "switch_off": switch_off,
    }


class _BMIH(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


def sample_discord_colors():
    """Снять с окна Discord фактический фон и цвет панелей: ("#RRGGBB", "#RRGGBB")."""
    try:
        hwnd = ms._find_discord_hwnd()
        if not hwnd:
            return None
        import ctypes.wintypes as wt
        from collections import Counter
        from PIL import Image

        u = ctypes.windll.user32
        gdi = ctypes.windll.gdi32
        if u.IsIconic(hwnd) or not u.IsWindowVisible(hwnd):
            return None
        rect = wt.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width < 300 or height < 200:
            return None
        hdc = u.GetWindowDC(hwnd)
        mdc = gdi.CreateCompatibleDC(hdc)
        bmp = gdi.CreateCompatibleBitmap(hdc, width, height)
        gdi.SelectObject(mdc, bmp)
        try:
            u.PrintWindow(hwnd, mdc, 0x00000002)  # PW_RENDERFULLCONTENT
            bi = _BMIH()
            bi.biSize = ctypes.sizeof(_BMIH)
            bi.biWidth = width
            bi.biHeight = -height
            bi.biPlanes = 1
            bi.biBitCount = 32
            buf = ctypes.create_string_buffer(width * height * 4)
            gdi.GetDIBits(mdc, bmp, 0, height, buf, ctypes.byref(bi), 0)
        finally:
            gdi.DeleteObject(bmp)
            gdi.DeleteDC(mdc)
            u.ReleaseDC(hwnd, hdc)
        img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1).convert("RGB")
        small = img.resize((max(8, width // 10), max(8, height // 10)))
        pixels = list(small.getdata())
        counts = Counter(pixels)
        if not counts:
            return None
        total = len(pixels)
        top = counts.most_common(16)
        bg_rgb, bg_n = top[0]
        if bg_rgb == (0, 0, 0) and bg_n > 0.9 * total:
            return None  # окно не отрисовалось
        panel_rgb = None
        for color, _cnt in top[1:]:
            if _color_dist(color, bg_rgb) >= 10:
                panel_rgb = color
                break
        if panel_rgb is None:
            panel_rgb = _mix(bg_rgb, (0, 0, 0) if _luminance(bg_rgb) > 0.5 else (255, 255, 255), 0.05)
        return _rgb_to_hex(bg_rgb), _rgb_to_hex(panel_rgb)
    except Exception as e:
        _dbg("theme: sample failed: %r" % e)
        return None


# Настройки оформления приложения (отдельный файл, чтобы не менять конфиг логики)
def ui_cfg_path():
    try:
        return os.path.join(os.path.dirname(ms.config_path()), "micswitcher_ui.json")
    except Exception:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "micswitcher_ui.json")


def load_ui_cfg():
    try:
        with open(ui_cfg_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_ui_cfg(cfg):
    try:
        p = ui_cfg_path()
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception as e:
        _dbg("ui cfg save failed: %r" % e)

# Иконка (base64). Заполняется автоматически при сборке exe.
ICON_B64 = ""

# Релиз
VERSION = "1.2.2"

# ─────────────────────────────────────────────────────────────
# Локализация (RU / EN)
# ─────────────────────────────────────────────────────────────
STRINGS = {
    "ru": {
        "app_title":          "Переключатель микрофонов",
        "footer":             "Переключатель микрофонов  •  v{ver}",
        "hotkey_badge":       "⌨  {hk}",
        "section_mics":       "Микрофоны",
        "reset_vol":          "↺ Сброс громкости",
        "switch_btn":         "Сменить микрофон  ({hk})",
        "btn_settings":       "Настройки",
        "btn_quit":           "Выход",
        "hint_main":          "ЛКМ — выбрать  •  колесо — громкость  •  тумблер — вкл/выкл",
        "vac_title":          "Виртуальный микрофон",
        "vac_not_found":      "не найден",
        "vac_active":         "активен",
        "vac_inactive":       "не активен",
        "vac_unavailable":    "недоступен",
        "vac_status_active":  "Активен: {name}",
        "vac_status_inactive":"Роутинг VAC не активен",
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
        "tray_quit":          "Выход",
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
        "undo":               "Отменить",
        "vac_start_fail":     "не удалось запустить",
        "vac_err_mic_gone":   "микрофон не найден (возможно, отключён)",
        "vac_err_open":       "не удалось открыть микрофон",
        "toast_vol_reset":    "🎚 Громкость сброшена: все микрофоны 100%",
        "toast_switch_fail":  "⚠️ Не удалось переключить микрофон: {e}",
        "mics_empty_hint":    "Проверьте подключение микрофона и разрешения Windows (Конфиденциальность → Микрофон).",
        "btn_refresh":        "↻ Обновить список",
        "topmost_chk":        "Окно поверх остальных окон",
        "sec_theme":          "Оформление",
        "theme_auto":         "Авто — как в Discord",
        "theme_dark":         "Discord Dark",
        "theme_light":        "Discord Light",
        "theme_midnight":     "Discord Midnight",
        "theme_src_discord":  "Тема взята из Discord: {name}",
        "theme_src_sampled":  "Тема снята с окна Discord: фон {bg} · панели {panel}",
        "theme_src_manual":   "Тема выбрана вручную",
        "theme_src_none":     "Discord не найден — тёмная тема Dark",
        "theme_name_dark":    "Dark",
        "theme_name_light":   "Light",
        "theme_name_midnight":"Midnight",
    },
    "en": {
        "app_title":          "Mic Switcher",
        "footer":             "Mic Switcher  •  v{ver}",
        "hotkey_badge":       "⌨  {hk}",
        "section_mics":       "Microphones",
        "reset_vol":          "↺ Reset volume",
        "switch_btn":         "Switch mic  ({hk})",
        "btn_settings":       "Settings",
        "btn_quit":           "Exit",
        "hint_main":          "LMB — select  •  wheel — volume  •  toggle — on/off",
        "vac_title":          "Virtual microphone",
        "vac_not_found":      "not found",
        "vac_active":         "active",
        "vac_inactive":       "inactive",
        "vac_unavailable":    "unavailable",
        "vac_status_active":  "Active: {name}",
        "vac_status_inactive":"VAC routing inactive",
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
        "undo":               "Undo",
        "vac_start_fail":     "could not start",
        "vac_err_mic_gone":   "microphone not found (possibly disconnected)",
        "vac_err_open":       "could not open the microphone",
        "toast_vol_reset":    "🎚 Volume reset: all mics at 100%",
        "toast_switch_fail":  "⚠️ Failed to switch mic: {e}",
        "mics_empty_hint":    "Check the mic connection and Windows permissions (Privacy → Microphone).",
        "btn_refresh":        "↻ Refresh list",
        "topmost_chk":        "Window always on top",
        "sec_theme":          "Appearance",
        "theme_auto":         "Auto — follow Discord",
        "theme_dark":         "Discord Dark",
        "theme_light":        "Discord Light",
        "theme_midnight":     "Discord Midnight",
        "theme_src_discord":  "Theme from Discord: {name}",
        "theme_src_sampled":  "Sampled from the Discord window: bg {bg} · panels {panel}",
        "theme_src_manual":   "Theme chosen manually",
        "theme_src_none":     "Discord not found — Dark theme",
        "theme_name_dark":    "Dark",
        "theme_name_light":   "Light",
        "theme_name_midnight":"Midnight",
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


# Кэш кадров «дыхания»: генерация 28 кадров 160×160 дорогая, а набор
# уровней от цвета/размера фиксирован — генерируем один раз на (color,size,levels).
_GLOW_CACHE = {}


def _glow_dot(color, size=20, levels=28):
    key = (color, size, levels)
    if key in _GLOW_CACHE:
        return _GLOW_CACHE[key]
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
        _GLOW_CACHE[key] = out
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


def _patch_pystray_win32():
    """pystray 0.19.5 на части систем падает с PermissionError [WinError 5]
    в ChangeWindowMessageFilterEx (pystray/_win32.py:_create_window) — поток
    иконки умирает молча, иконка в трее НЕ появляется. Этот вызов нужен
    только для перехвата перезапуска explorer, поэтому делаем его
    неопасным: глотаем ошибку и пишем в отладочный лог."""
    try:
        import pystray._util.win32 as _pw
        if getattr(_pw, "_msh_patched", False):
            return
        _orig = getattr(_pw, "ChangeWindowMessageFilterEx", None)
        if _orig is None:
            return

        def _safe(*a, **k):
            try:
                return _orig(*a, **k)
            except Exception as e:
                _dbg("tray: ChangeWindowMessageFilterEx ignored: %r" % e)
                return 0

        _pw.ChangeWindowMessageFilterEx = _safe
        _pw._msh_patched = True
    except Exception as e:
        _dbg("tray: pystray patch failed: %r" % e)


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
    d.ellipse((2, 2, S - 2, S - 2), fill=(88, 101, 242, 255))
    return img


class DiscordSelect(ctk.CTkFrame):
    """Выпадающий список в стиле Discord.

    CTkOptionMenu рисует справа цветной блок-кнопку со стрелкой — в Discord
    селект выглядит иначе: тёмное поле, серый шеврон справа, без акцентного
    прямоугольника. Поэтому поле собираем сами, а список показываем tk.Menu.
    """

    def __init__(self, master, values=None, command=None, height=40, font=None):
        super().__init__(master, fg_color=INPUT_BG, corner_radius=8,
                         height=height, border_width=0)
        self._values = list(values or [])
        self._command = command
        self._current = self._values[0] if self._values else ""
        self._font = font or ctk.CTkFont(family=FONT, size=13)
        self._label = ctk.CTkLabel(self, text=self._current, font=self._font,
                                   text_color=TEXT, anchor="w")
        self._label.pack(side="left", fill="x", expand=True, padx=(12, 0))
        self._arrow = tk.Canvas(self, width=18, height=18, bd=0,
                                highlightthickness=0, bg=INPUT_BG)
        self._arrow.create_line(4, 7, 9, 12, 14, 7, fill=DIM, width=2,
                                capstyle="round", joinstyle="round")
        self._arrow.pack(side="right", padx=(0, 10))
        self.pack_propagate(False)
        for wdg in (self, self._label, self._arrow):
            try:
                wdg.configure(cursor="hand2")
            except Exception:
                pass
            wdg.bind("<Button-1>", self._open)
            wdg.bind("<Enter>", self._on_enter)
            wdg.bind("<Leave>", self._on_leave)
        self._hover = False

    # ── API, совместимый с CTkOptionMenu ──
    def set(self, value):
        self._current = value
        try:
            self._label.configure(text=value)
        except Exception:
            pass

    def get(self):
        return self._current

    def set_values(self, values):
        self._values = list(values or [])
        if self._values and self._current not in self._values:
            self.set(self._values[0])

    def configure_values(self, values):
        self.set_values(values)

    # ── поведение ──
    def _on_enter(self, _e=None):
        if self._hover:
            return
        self._hover = True
        try:
            self.configure(fg_color=SURFACE_2)
            self._arrow.configure(bg=SURFACE_2)
        except Exception:
            pass

    def _on_leave(self, _e=None):
        if not self._hover:
            return
        self._hover = False
        try:
            self.configure(fg_color=INPUT_BG)
            self._arrow.configure(bg=INPUT_BG)
        except Exception:
            pass

    def _open(self, _e=None):
        try:
            menu = tk.Menu(self, tearoff=0, bd=0, relief="flat",
                           activeborderwidth=0, bg=INPUT_BG, fg=TEXT,
                           activebackground=BTN, activeforeground="#FFFFFF",
                           font=(FONT, 11))
            for v in self._values:
                menu.add_command(label=v, command=lambda v=v: self._choose(v))
            menu.tk_popup(self.winfo_rootx(),
                          self.winfo_rooty() + self.winfo_height() + 2)
            menu.grab_release()
        except Exception as e:
            _dbg("select: open failed: %r" % e)

    def _choose(self, value):
        self.set(value)
        if self._command is not None:
            try:
                self._command(value)
            except Exception as e:
                _dbg("select: command failed: %r" % e)



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

        # ── Оформление: тема в стиле Discord ──
        # theme_mode: "auto" (как в Discord) или конкретная тема
        self._ui_cfg = load_ui_cfg()
        self._theme_mode = self._ui_cfg.get("theme_mode") or "auto"
        self._apply_theme_mode(rebuild=False)
        _dbg("theme: start mode=%s source=%s bg=%s"
             % (self._theme_mode, self._theme_source, self._palette.get("bg")))

        # ── Окно ──
        ctk.set_appearance_mode("light" if getattr(self, "_is_light", False) else "dark")
        self.root = ctk.CTk()
        self.root.title(self.t("app_title"))
        self.root.configure(fg_color=BG)
        self.root.geometry("500x748")
        self.root.minsize(470, 680)
        self._topmost = ms.load_topmost()
        self.root.attributes("-topmost", self._topmost)
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
        F_TITLE  = ctk.CTkFont(family=FONT, size=19, weight="bold")
        F_H2     = ctk.CTkFont(family=FONT, size=15, weight="bold")
        F_BODY   = ctk.CTkFont(family=FONT, size=13)
        F_BODY_B = ctk.CTkFont(family=FONT, size=13, weight="bold")
        F_CAP    = ctk.CTkFont(family=FONT, size=12)
        F_CAP_B  = ctk.CTkFont(family=FONT, size=12, weight="bold")
        F_MICRO  = ctk.CTkFont(family=FONT, size=11)
        F_BTN    = ctk.CTkFont(family=FONT, size=14)

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
        self.root.after(120, self._apply_window_frame)

        self._start_tray()
        self.root.after(100, self._poll_hotkey)
        # Слежение за темой Discord (если выбрано «Авто — как в Discord»)
        threading.Thread(target=self._watch_discord_theme, daemon=True,
                         name="MicSwitcherTheme").start()

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

    # ═══════════════════════════ ТЕМА (Discord) ═══════════════════════════
    def _resolve_theme(self):
        """Какая тема нужна сейчас: (ключ, источник, палитра)."""
        mode = getattr(self, "_theme_mode", "auto")
        if mode in THEMES:
            return mode, "manual", dict(THEMES[mode])
        colors = sample_discord_colors()
        if colors:
            bg, panel = colors
            return "auto", "discord-window", palette_from_colors(_hex_to_rgb(bg), _hex_to_rgb(panel))
        detected, _src = detect_discord_theme()
        if detected:
            return detected, "discord-file", dict(THEMES[detected])
        return "dark", "none", dict(THEMES["dark"])

    def _apply_theme_mode(self, rebuild=True):
        """Пересчитать тему из режима и (при rebuild) перерисовать интерфейс."""
        name, source, pal = self._resolve_theme()
        self.theme = name
        self._theme_source = source
        self._palette = pal
        self._is_light = _luminance(_hex_to_rgb(pal["bg"])) > 0.5
        apply_palette_dict(pal)
        if rebuild:
            try:
                ctk.set_appearance_mode("light" if self._is_light else "dark")
            except Exception:
                pass
            try:
                self.root.configure(fg_color=BG)
            except Exception:
                pass
            self._rebuild_screens()
            self.root.after(60, self._apply_window_frame)
        return pal

    def theme_label(self, mode):
        return self.t("theme_auto") if mode == "auto" else self.t("theme_" + mode)

    def theme_menu_values(self):
        return [self.theme_label(m) for m in ("auto",) + THEME_ORDER]

    def theme_source_text(self):
        if self._theme_source == "discord-window":
            pal = getattr(self, "_palette", {})
            return self.t("theme_src_sampled", bg=pal.get("bg", "?"), panel=pal.get("card", "?"))
        if self._theme_source == "discord-file":
            return self.t("theme_src_discord", name=self.t("theme_name_" + self.theme))
        if self._theme_source == "manual":
            return self.t("theme_src_manual")
        return self.t("theme_src_none")

    def _on_theme_choice(self, label):
        mode = None
        for m in ("auto",) + THEME_ORDER:
            if self.theme_label(m) == label:
                mode = m
                break
        if mode is None or mode == self._theme_mode:
            return
        self._theme_mode = mode
        cfg = load_ui_cfg()
        cfg["theme_mode"] = mode
        save_ui_cfg(cfg)
        _dbg("theme: mode=%s" % mode)
        self._apply_theme_mode(rebuild=True)

    def _apply_window_frame(self):
        """Подкрасить заголовок/рамку окна под текущую тему (DWM, Windows 11)."""
        try:
            hwnd = int(self.root.wm_frame(), 16)
            if not hwnd:
                return
            dwm = ctypes.windll.dwmapi

            def _cint(attr, value):
                v = ctypes.c_int(int(value))
                dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))

            def _colorref(hex_color):
                try:
                    h = hex_color.lstrip("#")
                    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                except Exception:
                    return 0
                return r | (g << 8) | (b << 16)

            _cint(20, 0 if getattr(self, "_is_light", False) else 1)  # immersive dark mode
            _cint(35, _colorref(BG))                      # цвет заголовка = фон
            _cint(34, _colorref(BORDER))                  # цвет рамки
            _cint(36, _colorref(TEXT))                    # цвет текста заголовка
        except Exception:
            pass

    def _rebuild_screens(self):
        """Пересоздать оба экрана с новыми цветами (логика и состояние не меняются)."""
        cur = getattr(self, "screen", "main")
        for attr in ("main", "settings"):
            w = getattr(self, attr, None)
            if w is not None:
                try:
                    w.destroy()
                except Exception:
                    pass
        self.mic_rows = []
        try:
            self._build_main()
            self._build_settings()
            self._show_screen(cur if cur in ("main", "settings") else "main")
            self.update_ui()
            self._resync_layout()
        except Exception as e:
            _dbg("theme: rebuild failed: %r" % e)

    def _apply_detected_theme(self):
        try:
            if self._theme_mode != "auto":
                return
            self._apply_theme_mode(rebuild=True)
            _dbg("theme: switched to %s (%s, bg=%s)"
                 % (self.theme, self._theme_source, getattr(self, "_palette", {}).get("bg")))
        except Exception as e:
            _dbg("theme: apply detected failed: %r" % e)

    def _theme_signature(self):
        """Отпечаток темы Discord: цвета окна, а если окно недоступно — данные клиента."""
        if getattr(self, "_theme_mode", "auto") != "auto":
            return None
        colors = sample_discord_colors()
        if colors:
            return ("win",) + colors
        detected, _src = detect_discord_theme()
        return ("file", detected)

    def _watch_discord_theme(self):
        """Фон: сменили тему в Discord — подстраиваемся (только режим «Авто»)."""
        last = self._theme_signature()
        while True:
            time.sleep(4)
            try:
                sig = self._theme_signature()
                if sig is None or sig == last:
                    continue
                # Окно Discord свернули/закрыли: не сбрасываем уже снятые цвета
                if sig[0] == "file" and getattr(self, "_theme_source", "") == "discord-window":
                    last = sig
                    continue
                last = sig
                self.root.after(0, self._apply_detected_theme)
            except Exception as e:
                _dbg("theme watch: %r" % e)

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
        self.hk_pill = ctk.CTkFrame(row1, fg_color=KEYCAP_BG, corner_radius=6,
                                    border_width=1, border_color=KEYCAP_BORDER)
        self.hk_pill.pack(side="right")
        self.hk_badge_lbl = ctk.CTkLabel(self.hk_pill, text=self.t("hotkey_badge", hk=self.display_hotkey()),
                                         font=F_CAP_B, text_color=DIM)
        self.hk_badge_lbl.pack(padx=10, pady=4)

        row2 = ctk.CTkFrame(hdr, fg_color="transparent")
        row2.pack(fill="x", pady=(8, 0))
        self.hdr_dot = ctk.CTkLabel(row2, text="●", font=F_CAP_B, text_color=DIM)
        self.hdr_dot.pack(side="left")
        self.hdr_sub = ctk.CTkLabel(row2, text="", font=F_CAP, text_color=DIM, anchor="w")
        self.hdr_sub.pack(side="left", padx=(8, 0))
        self.vu = ctk.CTkProgressBar(row2, width=104, height=6, corner_radius=3,
                                     fg_color=TRACK, progress_color=ACTIVE)
        self._vu_prev = 0.0
        def vu_set(v):
            # Перерисовываем только при реальном изменении уровня:
            # принудительный _draw() каждый тик — пустой CPU и зависимость
            # от приватного API CTkProgressBar.
            if abs(float(v) - self._vu_prev) > 0.01:
                self._vu_prev = float(v)
                self.vu.set(self._vu_prev)
        self.vu_set = vu_set
        self.vu.pack(side="right")

        # ── Секция «Микрофоны» ──
        sec = ctk.CTkFrame(self.main, fg_color="transparent")
        sec.pack(fill="x", padx=20, pady=(12, 4))
        self._sec_mics_lbl = ctk.CTkLabel(sec, text=self.t("section_mics").upper(),
                                          font=F_CAP_B, text_color=TEXT_3, anchor="w")
        self._sec_mics_lbl.pack(side="left")
        self._reset_vol_btn = ctk.CTkButton(sec, text=self.t("reset_vol"), command=self.reset_volumes,
                      fg_color="transparent", hover_color=SURFACE_2, text_color=TEXT_3,
                      corner_radius=6, height=26, font=F_CAP)
        self._reset_vol_btn.pack(side="right")

        # Список микрофонов (скролл-область фиксированной высоты —
        # размер окна одинаков для обоих экранов)
        self.mic_list = ctk.CTkScrollableFrame(self.main, fg_color="transparent",
                                               height=308, scrollbar_fg_color="transparent",
                                               scrollbar_button_color=TRACK,
                                               scrollbar_button_hover_color=BTN)
        self.mic_list.pack(fill="x", padx=20)

        # ── Карточка виртуального микрофона ──
        self._build_vac_card()

        # ── Основное действие ──
        self.switch_btn = ctk.CTkButton(self.main,
                                        text=self.t("switch_btn", hk=self.display_hotkey()),
                                        command=self.toggle,
                                        fg_color=BTN, hover_color=BTN_HOVER, text_color=ON_ACCENT,
                                        font=F_BTN, height=44, corner_radius=8)
        self.switch_btn.pack(fill="x", padx=20, pady=(10, 10))

        # ── Вторичные действия (симметрично, равной шириной) ──
        row = ctk.CTkFrame(self.main, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 8))
        self._btn_settings = ctk.CTkButton(row, text=self.t("btn_settings"), command=self.open_settings,
                      fg_color=BTN2, hover_color=BTN2_HOVER, text_color=BTN2_TEXT,
                      corner_radius=8, height=36, font=F_BODY)
        self._btn_settings.pack(side="left", fill="x",
                                                                expand=True, padx=(0, 4))
        self._btn_quit = ctk.CTkButton(row, text=self.t("btn_quit"), command=self.quit_app,
                      fg_color=BTN2, hover_color=BTN2_HOVER, text_color=DANGER,
                      corner_radius=8, height=36, font=F_BODY)
        self._btn_quit.pack(side="left", fill="x",
                                                                expand=True, padx=(4, 0))

        # ── Подсказка + версия ──
        self._hint_lbl = ctk.CTkLabel(self.main,
                     text=self.t("hint_main"), wraplength=440,
                     font=F_MICRO, text_color=TEXT_3, anchor="w")
        self._hint_lbl.pack(fill="x", padx=20, pady=(2, 4))
        self._footer_lbl = ctk.CTkLabel(self.main, text=self.t("footer", ver=VERSION),
                     font=F_MICRO, text_color=TEXT_3)
        self._footer_lbl.pack(pady=(0, 12))

    def _build_vac_card(self):
        card = ctk.CTkFrame(self.main, fg_color=CARD, corner_radius=8,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", padx=20, pady=(8, 8))
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 0))
        self._vac_title_lbl = ctk.CTkLabel(top, text=self.t("vac_title"), font=F_BODY_B, text_color=TEXT,
                     anchor="w")
        self._vac_title_lbl.pack(side="left")
        self.vac_status_pill = ctk.CTkFrame(top, fg_color=SURFACE_2, corner_radius=999)
        self.vac_status_pill.pack(side="right")
        self.vac_status_lbl = ctk.CTkLabel(self.vac_status_pill, text="…", font=F_MICRO,
                                           text_color=DIM)
        self.vac_status_lbl.pack(padx=8, pady=3)
        self._vac_name_lbl = ctk.CTkLabel(card, text=(self.vac_name or self.t("vac_not_found")), font=F_CAP, text_color=DIM,
                     anchor="w")
        self._vac_name_lbl.pack(fill="x", padx=14, pady=(2, 6))
        links = ctk.CTkFrame(card, fg_color="transparent")
        links.pack(fill="x", padx=14, pady=(0, 12))
        self._vac_discord_btn = ctk.CTkButton(links, text=self.t("vac_discord"),
                      command=self.open_discord_voice_settings,
                      fg_color=BTN2, hover_color=BTN2_HOVER, text_color=BTN2_TEXT,
                      corner_radius=8, height=32, font=F_BODY)
        self._vac_discord_btn.pack(side="left")
        self._vac_windows_btn = ctk.CTkButton(links, text=self.t("vac_windows"),
                      command=self.open_windows_sound_settings,
                      fg_color=BTN2, hover_color=BTN2_HOVER, text_color=BTN2_TEXT,
                      corner_radius=8, height=32, font=F_BODY)
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
                      fg_color=BTN2, hover_color=BTN2_HOVER, text_color=BTN2_TEXT,
                      corner_radius=8, height=32, font=F_BODY)
        self._btn_back.pack(side="right")

        # ── Виртуальный микрофон ──
        c1 = ctk.CTkFrame(s, fg_color=CARD, corner_radius=10, border_width=1, border_color=BORDER)
        c1.pack(fill="x", padx=20, pady=(12, 10))
        self._settings_vac_title = ctk.CTkLabel(c1, text=self.t("vac_title"), font=F_H2, text_color=TEXT,
                     anchor="w")
        self._settings_vac_title.pack(fill="x", padx=14, pady=(12, 4))
        self.vac_status_row = ctk.CTkLabel(c1, text="", font=F_CAP, text_color=DIM,
                                           anchor="w", justify="left")
        self.vac_status_row.pack(fill="x", padx=14)
        self._settings_test_btn = ctk.CTkButton(c1, text=self.t("vac_test_btn"), command=self.test_virtual_mic,
                      fg_color=BTN, hover_color=BTN_HOVER, text_color=ON_ACCENT,
                      corner_radius=8, height=36, font=F_BTN)
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
        self.mon_out_menu = DiscordSelect(dev_row, values=[], command=lambda v: None,
                                          height=40, font=F_BODY)
        self.mon_out_menu.pack(side="left", fill="x", expand=True, padx=(8, 0))
        try:
            self.mon_out_menu.set("—")
        except Exception:
            pass
        self.mon_btn = ctk.CTkButton(c1, text=self.t("vac_mon_start"), command=self.toggle_monitor,
                                     fg_color=BTN, hover_color=BTN_HOVER, text_color=ON_ACCENT,
                                     corner_radius=8, height=36, font=F_BTN)
        self.mon_btn.pack(fill="x", padx=14, pady=(10, 4))
        self.mon_lbl = ctk.CTkLabel(c1, text="", font=F_CAP, text_color=DIM,
                                    anchor="w", justify="left", height=1)
        self.mon_lbl.pack(fill="x", padx=14, pady=(0, 12))

        # ── Горячая клавиша ──
        c2 = ctk.CTkFrame(s, fg_color=CARD, corner_radius=10, border_width=1, border_color=BORDER)
        c2.pack(fill="x", padx=20, pady=(0, 10))
        self._settings_hk_title = ctk.CTkLabel(c2, text=self.t("sec_hotkey"), font=F_H2, text_color=TEXT,
                     anchor="w")
        self._settings_hk_title.pack(fill="x", padx=14, pady=(12, 4))
        self.hk_field = ctk.CTkButton(c2, text=self.display_hotkey(),
                                      command=self._begin_hotkey_capture,
                                      fg_color=INPUT_BG, hover_color=SURFACE_2,
                                      text_color=TEXT, corner_radius=8, height=40,
                                      border_width=0, font=F_BTN)
        self.hk_field.pack(fill="x", padx=14)
        self._settings_hk_hint = ctk.CTkLabel(c2, text=self.t("hk_hint"),
                     font=F_MICRO, text_color=TEXT_3, anchor="w")
        self._settings_hk_hint.pack(fill="x", padx=14, pady=(8, 12))

        # ── Автозапуск ──
        c3 = ctk.CTkFrame(s, fg_color=CARD, corner_radius=10, border_width=1, border_color=BORDER)
        c3.pack(fill="x", padx=20, pady=(0, 10))
        self._settings_autostart_title = ctk.CTkLabel(c3, text=self.t("sec_autostart"), font=F_H2, text_color=TEXT,
                     anchor="w")
        self._settings_autostart_title.pack(fill="x", padx=14, pady=(12, 4))
        self.auto_var = tk.BooleanVar(value=ms.autostart_enabled())
        self._autostart_chk, self._autostart_lbl = self._switch_row(
            c3, self.t("autostart_chk"), self.auto_var, self._apply_autostart)
        self.topmost_var = tk.BooleanVar(value=self._topmost)
        self._topmost_chk, self._topmost_lbl = self._switch_row(
            c3, self.t("topmost_chk"), self.topmost_var, self._apply_topmost)
        ctk.CTkFrame(c3, fg_color="transparent", height=4).pack(fill="x")

        # ── Язык + Оформление ──
        c4 = ctk.CTkFrame(s, fg_color=CARD, corner_radius=10, border_width=1, border_color=BORDER)
        c4.pack(fill="x", padx=20, pady=(0, 10))
        self._settings_lang_title = ctk.CTkLabel(c4, text=self.t("sec_lang"), font=F_H2, text_color=TEXT,
                     anchor="w")
        self._settings_lang_title.pack(fill="x", padx=14, pady=(12, 4))
        self.lang_menu = DiscordSelect(c4, values=["Русский", "English"],
                                       command=self._on_lang_change,
                                       height=40, font=F_BODY)
        self.lang_menu.set("Русский" if self.lang == "ru" else "English")
        self.lang_menu.pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkFrame(c4, fg_color=BORDER, height=1).pack(fill="x", padx=14, pady=2)

        # Оформление: фирменные темы Discord
        self._settings_theme_title = ctk.CTkLabel(c4, text=self.t("sec_theme"), font=F_H2,
                                                  text_color=TEXT, anchor="w")
        self._settings_theme_title.pack(fill="x", padx=14, pady=(10, 4))
        self.theme_menu = DiscordSelect(c4, values=self.theme_menu_values(),
                                        command=self._on_theme_choice,
                                        height=40, font=F_BODY)
        self.theme_menu.set(self.theme_label(self._theme_mode))
        self.theme_menu.pack(fill="x", padx=14)
        self._settings_theme_hint = ctk.CTkLabel(c4, text=self.theme_source_text(),
                                                 font=F_MICRO, text_color=TEXT_3,
                                                 anchor="w", justify="left")
        self._settings_theme_hint.pack(fill="x", padx=14, pady=(8, 12))

    def _switch_row(self, parent, text, var, command):
        """Строка настройки в стиле Discord: подпись слева, тумблер справа."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 10))
        lbl = ctk.CTkLabel(row, text=text, font=F_BODY, text_color=TEXT, anchor="w")
        lbl.pack(side="left", fill="x", expand=True)
        sw = ctk.CTkSwitch(row, text="", variable=var, command=command,
                           onvalue=True, offvalue=False,
                           progress_color=ACTIVE, fg_color=SWITCH_OFF,
                           button_color="#FFFFFF", button_hover_color="#FFFFFF",
                           switch_width=40, switch_height=22, corner_radius=11,
                           border_width=0, width=44, height=24)
        sw.pack(side="right")
        return sw, lbl

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
                self.mon_out_menu.set_values(names)
                self.mon_out_menu.set(names[self._find_default_index(devices)])
            except Exception:
                pass
        if self.monitor is not None:
            try:
                self.mon_btn.configure(text=self.t("vac_mon_stop"), fg_color=DANGER,
                                       hover_color=DANGER_HOVER)
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
            self._sec_mics_lbl.configure(text=self.t("section_mics").upper())
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
            self._autostart_lbl.configure(text=self.t("autostart_chk"))
            self._topmost_lbl.configure(text=self.t("topmost_chk"))
            self._settings_lang_title.configure(text=self.t("sec_lang"))
            # Оформление (темы Discord)
            try:
                self._settings_theme_title.configure(text=self.t("sec_theme"))
                self.theme_menu.set_values(self.theme_menu_values())
                self.theme_menu.set(self.theme_label(self._theme_mode))
                self._settings_theme_hint.configure(text=self.theme_source_text())
            except Exception:
                pass
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
    def _refresh_now(self):
        """Ручное перечитывание списка устройств (кнопка в пустом состоянии)."""
        try:
            self.refresh()
        except Exception as e:
            _dbg("_refresh_now: %r" % e)
        self._animated_update(flash=False)

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
            ctk.CTkLabel(self.mic_list, text=self.t("mics_empty"), font=F_BODY_B,
                         text_color=TEXT, anchor="w").pack(anchor="w", pady=(8, 2))
            ctk.CTkLabel(self.mic_list, text=self.t("mics_empty_hint"), font=F_MICRO,
                         text_color=DIM, anchor="w", justify="left",
                         wraplength=400).pack(anchor="w", pady=(0, 6))
            ctk.CTkButton(self.mic_list, text=self.t("btn_refresh"), command=self._refresh_now,
                          fg_color=BTN2, hover_color=BTN2_HOVER, text_color=BTN2_TEXT,
                          corner_radius=8, height=32, font=F_BODY).pack(anchor="w", pady=(0, 4))
            self._resync_layout()
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

            card = ctk.CTkFrame(self.mic_list, fg_color=row_bg, corner_radius=8,
                                border_width=1,
                                border_color=BTN if is_active else BORDER)
            card.pack(fill="x", pady=3)

            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=14, pady=(9, 0))
            # Тумблер пакуем ПЕРВЫМ: он сразу бронирует место справа,
            # поэтому его не «съедает» длинное имя + пиллы (раньше на
            # активной карточке тумблер сжимался до нуля и исчезал).
            cb_var = tk.BooleanVar(value=not excluded)  # вкл = участвует в переключении
            # width/height = размер самого тумблера: иначе виджет по умолчанию
            # 100px шириной, а тумблер рисуется в его левом углу (виден отступ справа)
            cb = ctk.CTkSwitch(top, text="", variable=cb_var,
                               command=lambda m=mic: self.toggle_exclude(m),
                               progress_color=ACTIVE,
                               fg_color=SWITCH_OFF,
                               button_color="#FFFFFF", button_hover_color="#FFFFFF",
                               switch_width=40, switch_height=22, corner_radius=11,
                               border_width=0, width=44, height=24)
            cb.pack(side="right", padx=(10, 0))

            accent = ctk.CTkFrame(top, width=3, height=20, corner_radius=2,
                                  fg_color=BTN if is_active else (BORDER if not excluded else SURFACE_2))
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
                                   progress_color=BTN, button_color="#FFFFFF",
                                   button_hover_color="#FFFFFF", fg_color=TRACK,
                                   height=8, button_length=16, corner_radius=4)
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
                        c.configure(fg_color=CARD_HOVER)
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
        """Высота окна = высоте текущего экрана.
        Главный экран компактный, настроек — выше (в них больше карточек)."""
        try:
            self.root.update_idletasks()
            name = screen_name or getattr(self, "screen", "main")
            target = self.main if name == "main" else self.settings
            h = int(target.winfo_reqheight())
            if h <= 100:
                return
            h = max(560, min(960, h))
            self.root.minsize(470, min(680, h))
            # Ручной resize пользователя не должен сбрасываться при каждом свитче:
            # geometry() дёргаем только когда требуемая высота реально изменилась.
            if getattr(self, "_last_win_h", 0) and abs(h - self._last_win_h) <= 2:
                return
            self._last_win_h = h
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
        self.show_notification(self.t("toast_vol_reset"))

    def _flash_active(self):
        """Мягкий пульс рамки: плавное в-и-вы (2 фазы, ~240 мс)."""
        if self.current is None:
            return
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

    def _vac_err_text(self, err):
        """Русские сообщения ядра → локализованные строки (иначе в EN-тостах кириллица)."""
        s = str(err or "").strip()
        if not s:
            return ""
        low = s.lower()
        if "не найден" in low:
            return self.t("vac_err_mic_gone")
        if "не удалось открыть" in low:
            return self.t("vac_err_open")
        return s

    def _switch_to(self, mic):
        _dbg("_switch_to: enter -> %r" % mic.FriendlyName)
        prev = self.current
        # set_default() работает по self.index — синхронизируем индекс с целью,
        # иначе «Отменить» вернёт роутер на prev, а дефолтом Windows останется новый mic.
        if mic in self.active:
            self.index = self.active.index(mic)
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
                    vac_err = self._vac_err_text(r.last_error) or self.t("vac_start_fail")
            except Exception as e:
                vac_ok = False
                vac_err = self._vac_err_text(e)
        self._animated_update(flash=True)
        name = self._clean_mic_name(mic.FriendlyName)
        if self.router is not None and vac_ok:
            act = None
            if prev is not None and prev.id != mic.id and not self.is_excluded(prev):
                act = (self.t("undo"), lambda pv=prev: self._switch_to(pv))
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
        # ВАЖНО: слив очереди и toggle() разнесены. Раньше toggle() стоял
        # внутри того же try сразу после while True, и queue.Empty выходил из
        # try раньше, чем доходило до `if fired:` — хоткей «срабатывал»
        # (on_hotkey писал в очередь), но переключения не было НИКОГДА.
        fired = False
        try:
            while True:
                self._hotkey_q.get_nowait()
                fired = True  # автоповтор при удержании: не больше одного свитча за тик
        except queue.Empty:
            pass
        except Exception as e:
            _dbg("poll: hotkey drain error: %r" % e)
        if fired:
            _dbg("poll: hotkey flag -> toggle()")
            try:
                self.toggle()
            except Exception as e:
                _dbg("poll: toggle failed: %r" % e)
                try:
                    self.show_notification(self.t("toast_switch_fail", e=str(e)))
                except Exception:
                    pass
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
                # у pynput-Listener свойство называется running (is_running его нет)
                _lr = self.listener.listener.running if self.listener else None
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
                                    fg_color=ACTIVE, hover_color=ACTIVE, text_color=ON_ACCENT)
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
        try:
            self._log("cap ev: keysym=%s state=0x%x char=%r" % (event.keysym, event.state, event.char))
        except Exception:
            pass
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

    def _real_mods(self):
        """Физическое состояние модификаторов (GetAsyncKeyState), а не биты event.state.

        В event.state приложению приходит «фантомный» Alt (WM_SYSKEYDOWN / залипание
        после Alt+Tab или проглоченного клавиатурным хуком keyup), и тогда к ЛЮБОЙ
        клавише лепится «alt+». Физически Alt при этом не нажат — GetAsyncKeyState
        это видит, и связка собирается по реально удерживаемым клавишам.
        None — если API недоступен (тогда резерв на биты state)."""
        try:
            import ctypes
            u = ctypes.windll.user32
        except Exception:
            return None
        out = []
        try:
            for name, vks in (("shift", (0x10, 0xA0, 0xA1)),
                              ("ctrl", (0x11, 0xA2, 0xA3)),
                              ("alt", (0x12, 0xA4, 0xA5)),
                              ("cmd", (0x5B, 0x5C))):
                if any(u.GetAsyncKeyState(vk) & 0x8000 for vk in vks):
                    out.append(name)
        except Exception:
            return None
        return out

    def _tk_key_to_spec(self, event):
        keysym = event.keysym
        char = event.char
        if keysym in ms._TK_SPECIAL:
            main = ms._TK_SPECIAL[keysym]
        elif len(keysym) == 1 and keysym.isalnum():
            # Ctrl+буква: Tk даёт keysym='m', а char — управляющий символ (\r и т.п.),
            # поэтому брать надо keysym, иначе связки с Ctrl не проходят валидацию.
            main = keysym.lower()
        elif char and len(char) == 1 and char.isprintable():
            main = char.lower()
        else:
            return None
        mods = self._real_mods()
        if mods is None:  # нет GetAsyncKeyState — резерв на биты Tk event.state
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
        return mods, main

    def _set_cap_text(self, t):
        try:
            self.hk_field.configure(text=t, fg_color=ACTIVE, hover_color=ACTIVE,
                                    text_color=ON_ACCENT)
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
        try:
            self.stop_monitor()  # сквозное прослушивание VAC тоже должно гаснуть при выходе
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
        # Закрытие окна крестиком во время захвата клавиши: иначе глобальный
        # слушатель останется остановленным и хоткей «умрёт» до возврата в настройки.
        if self._hk_capturing:
            self._end_hotkey_capture(restart_old=True)
        self.hidden = True
        # Прятать «в трей» можно, только если иконка там РЕАЛЬНО есть
        # (поток pystray мог упасть). Иначе оставляем кнопку в панели задач.
        tray_ok = False
        try:
            tray_ok = self.tray_icon is not None and bool(self.tray_icon.visible)
        except Exception:
            tray_ok = False
        if tray_ok:
            self.root.withdraw()
        else:
            self.root.iconify()
        _dbg("hide_window: tray_ok=%s -> %s" % (tray_ok, "withdraw" if tray_ok else "iconify"))

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
        # DWM иногда сбрасывает цвета рамки после deiconify — обновляем
        self.root.after(40, self._apply_window_frame)

    def _start_tray(self):
        try:
            _dbg("tray: _start_tray begin")
            import pystray
            _patch_pystray_win32()
            img = get_tray_image()
            show_item = pystray.MenuItem(self.t("tray_show"), self._tray_show, default=True)
            quit_item = pystray.MenuItem(self.t("tray_quit"), self._tray_quit)
            self.tray_icon = pystray.Icon("MicSwitcher", img, self.t("tray_tooltip"),
                                          pystray.Menu(show_item, quit_item))

            def _on_setup(icon):
                # ВАЖНО: при своей setup-функции pystray НЕ показывает иконку
                # сам — нужно явно icon.visible = True (это NIM_ADD).
                try:
                    icon.visible = True
                except Exception as e:
                    _dbg("tray: setup visible failed: %r" % e)
                try:
                    _dbg("tray: icon registered, visible=%s" % icon.visible)
                except Exception:
                    pass

            def _run():
                try:
                    self.tray_icon.run(setup=_on_setup)
                    _dbg("tray: run loop exited")
                except Exception as e:
                    _dbg("tray: run crashed: %r" % e)

            threading.Thread(target=_run, daemon=True, name="MicSwitcherTray").start()
            self.root.after(2500, self._check_tray)
        except Exception as e:
            _dbg("tray error: %r" % e)
            print("tray error:", e)
            self.tray_icon = None

    def _check_tray(self):
        """Через пару секунд после старта: иконка реально в трее?"""
        vis = False
        try:
            vis = bool(self.tray_icon is not None and self.tray_icon.visible)
        except Exception:
            vis = False
        _dbg("tray: check visible=%s" % vis)
        if vis:
            threading.Thread(target=self._promote_tray_icon, daemon=True).start()

    def _promote_tray_icon(self):
        """Windows 11 прячет новые иконки в меню «скрытые значки».
        Помечаем свою иконку как заметную (IsProminent=1) в настройках
        оболочки и перерегистрируем её — иначе пользователь «не видит
        трей» и думает, что приложение пропало. Best effort: при любом
        сбое просто пишем в лог."""
        try:
            import winreg
            exe = (sys.executable or "").lower()
            if not exe:
                return
            key_path = r"Control Panel\NotifyIconSettings"
            time.sleep(1.5)
            target = None
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as rootk:
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(rootk, i)
                    except OSError:
                        break
                    i += 1
                    try:
                        with winreg.OpenKey(rootk, sub) as sk:
                            p, _ = winreg.QueryValueEx(sk, "ExecutablePath")
                    except OSError:
                        continue
                    if str(p).lower() == exe:
                        target = sub
            if target is None:
                _dbg("tray: promote: no NotifyIconSettings entry for %s" % exe)
                return
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path + "\\" + target,
                                0, winreg.KEY_SET_VALUE) as sk:
                winreg.SetValueEx(sk, "IsProminent", 0, winreg.REG_DWORD, 1)
            _dbg("tray: promote: IsProminent=1 (%s)" % target)
            icon = self.tray_icon
            if icon is not None:
                icon.visible = False
                time.sleep(0.5)
                icon.visible = True
                _dbg("tray: promote: re-registered, visible=%s" % icon.visible)
        except Exception as e:
            _dbg("tray: promote failed: %r" % e)

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
                name = self._clean_mic_name(self.current.FriendlyName)
                if len(name) > 34:  # иначе строка наезжает на VU-метр
                    name = name[:33].rstrip(" ,-") + "…"
                self.hdr_dot.configure(text_color=ACTIVE)
                self.hdr_sub.configure(text=self.t("vac_status_active", name=name))
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
            # Без VAC кнопки «Проверить» и «Прослушать» заведомо бесполезны — гасим.
            if self.cable_idx is None and self.monitor is None:
                self._settings_test_btn.configure(state="disabled")
                self.mon_btn.configure(state="disabled")
            else:
                self._settings_test_btn.configure(state="normal")
                self.mon_btn.configure(state="normal")
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
            self.mon_btn.configure(text=self.t("vac_mon_stop"), fg_color=DANGER, hover_color=DANGER_HOVER)
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

    # ---------- окно поверх / автозапуск ----------
    def _apply_topmost(self):
        on = bool(self.topmost_var.get())
        self._topmost = on
        try:
            self.root.attributes("-topmost", on)
        except Exception:
            pass
        try:
            ms.save_config(self.hotkey, self.exclude, self.mic_vol, topmost=on)
        except Exception:
            pass

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
    _dbg("main: start (pid=%s, v=%s)" % (os.getpid(), VERSION))
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\MicSwitcher_SingleInstance")
    # NULL (мьютекс не создан) — продолжаем запуск; старое значение gle не читаем,
    # иначе свежий экземпляр мог бы ложно решит, что «уже запущен».
    _gle = ctypes.windll.kernel32.GetLastError() if _mutex else 0
    _dbg("main: mutex created, gle=%s" % _gle)
    if _gle == 183:  # ERROR_ALREADY_EXISTS
        from tkinter import messagebox
        lang = ms.load_lang()
        d = STRINGS.get(lang, STRINGS["ru"])
        # Вместо только сообщения — поднять окно уже запущенного экземпляра
        # (пользователь кликает exe повторно и ждёт окна, а иконку в трее Windows
        # мог спрятать в «скрытые значки»).
        shown = False
        try:
            u = ctypes.windll.user32
            for ttl in (STRINGS["ru"]["app_title"], STRINGS["en"]["app_title"],
                        "Mic Switcher", "MicSwitcher"):
                hwnd = u.FindWindowW(None, ttl)
                if hwnd:
                    if u.IsIconic(hwnd):
                        u.ShowWindow(hwnd, 9)  # SW_RESTORE
                    elif not u.IsWindowVisible(hwnd):
                        # Окно скрыто (withdraw), а не свёрнуто: без
                        # ShowWindow SwitchToThisWindow молча не делает ничего.
                        u.ShowWindow(hwnd, 1)  # SW_SHOWNORMAL
                    u.BringWindowToTop(hwnd)
                    u.SwitchToThisWindow(hwnd, True)
                    u.SetForegroundWindow(hwnd)
                    shown = True
                    break
        except Exception as e:
            _dbg("main: foreground existing failed: %r" % e)
        _dbg("main: already running, foreground=%s" % shown)
        if not shown:
            messagebox.showinfo(
                d.get("app_title", "Mic Switcher"),
                d.get("msg_already_run", "Already running"),
            )
        return

    app = App()
    _dbg("main: App() ok, hotkey=%r" % app.hotkey)
    # Битый спецификатор хоткея в конфиге не должен ронять запуск: откат на f9.
    try:
        app.listener = ms.Hotkey(app.hotkey, app.on_hotkey)
    except Exception as e:
        _dbg("main: bad hotkey spec %r: %r -> fallback f9" % (app.hotkey, e))
        app.hotkey = "f9"
        try:
            app.listener = ms.Hotkey(app.hotkey, app.on_hotkey)
        except Exception as e2:
            _dbg("main: fallback hotkey failed: %r" % e2)
            app.listener = None
    _dbg("main: Hotkey created")
    if app.listener is not None:
        app.listener.start()
    try:
        _running = app.listener.listener.running
    except Exception:
        _running = "?"
    _dbg("main: listener.start() done, is_running=%s" % _running)
    print("Горячая клавиша: %s" % app.display_hotkey())
    app.root.mainloop()


if __name__ == "__main__":
    main()
