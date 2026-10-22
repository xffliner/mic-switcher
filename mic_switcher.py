# -*- coding: utf-8 -*-
"""
Переключатель микрофонов по горячей клавише (Windows).
Каждый нажим клавиши переключает микрофон "по умолчанию" И ведёт его звук
в виртуальный микрофон VAC (Virtual Audio Cable) — его выбирают в Discord.
"""
import base64
import ctypes
import json
import os
import queue
import re
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk

import comtypes
import numpy as np
import pynput.keyboard as pkb
import sounddevice as sd
from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
from pycaw.api.policyconfig import IPolicyConfig
from pycaw.constants import (
    CLSID_CPolicyConfigClient,
    CLSID_MMDeviceEnumerator,
    DEVICE_STATE,
    EDataFlow,
    ERole,
)
from pycaw.utils import AudioUtilities

HOTKEY = "f9"  # Горячая клавиша: "f9", "f10", "<ctrl>+m", "<alt>+f1" и т.д.

# ─────────────────────────────────────────────────────────────
# Дизайн-система: палитра, типографика, отступы
# Концепция — «аудио-консоль»: глубокие слои тёмных поверхностей,
# один выверенный акцент, чёткая иерархия, осмысленные состояния.
# ─────────────────────────────────────────────────────────────
# Поверхности (elevation: чем выше — тем светлее)
BG        = "#111a2e"   # фон приложения (глубина)
CARD      = "#1b2740"   # карточки / поверхности
SURFACE_2 = "#243250"   # подъём / hover-поверхность
BORDER    = "#31415f"   # разделители / тонкие границы
# Текст (семантическая шкала)
TEXT      = "#eef2fb"   # основной
DIM       = "#9fabc7"   # вторичный
TEXT_3    = "#68769a"   # приглушённый
# Акцент и состояния
BTN       = "#4c8dff"   # акцент (основное действие)
BTN_HOVER = "#3d7bf0"   # акцент hover
ACTIVE    = "#34d399"   # успех / активный (зелёный)
ACCENT_SOFT = "#1a355e" # мягкая акцентная заливка (выделенный элемент)
DANGER    = "#ff7a85"   # опасно / исключён
WARNING   = "#f6b64b"   # внимание (янтарный)

# Типографика (Segoe UI — нативный шрифт Windows)
FONT   = "Segoe UI"
F_H1   = (FONT, 17, "bold")   # заголовок приложения
F_H2   = (FONT, 12, "bold")   # заголовок секции
F_BODY = (FONT, 11)           # основной текст
F_BODY_B = (FONT, 11, "bold") # основной текст, жирный
F_CAP  = (FONT, 10)           # подпись
F_CAP_B= (FONT, 10, "bold")   # подпись, жирная
F_MICRO= (FONT, 9)            # мелкий текст
F_BTN  = (FONT, 12, "bold")   # крупные кнопки

# Отступы (8-пунктовая сетка)
PAD = 20   # основной отступ контента
GAP = 8


def pill_button(parent, text, command, fg=BTN, bg=SURFACE_2,
                hover_bg=BTN, hover_fg="white"):
    """Компактная «пилюля»-кнопка с состоянием hover (Enter/Leave)."""
    b = tk.Button(parent, text=text, fg=fg, bg=bg,
                  activebackground=hover_bg, activeforeground=hover_fg,
                  relief="flat", bd=0, highlightthickness=0,
                  font=F_CAP_B, cursor="hand2", padx=12, pady=6, command=command)
    b.bind("<Enter>", lambda e: b.config(bg=hover_bg, fg=hover_fg))
    b.bind("<Leave>", lambda e: b.config(bg=bg, fg=fg))
    return b


def settings_header(w, text):
    """Заголовок секции настроек."""
    tk.Label(w, text=text, bg=BG, fg=TEXT, font=F_H2, anchor="w") \
        .pack(anchor="w", padx=PAD, pady=(16, 2))


def settings_divider(w):
    """Тонкий разделитель между секциями настроек."""
    tk.Frame(w, bg=BORDER, height=1).pack(fill="x", padx=PAD, pady=14)


def settings_button(w, text, command, primary=False):
    """Кнопка настроек: primary — акцентная, иначе — вторичная."""
    if primary:
        b = tk.Button(w, text=text, bg=BTN, fg="white",
                      activebackground=BTN_HOVER, activeforeground="white",
                      relief="flat", bd=0, highlightthickness=0,
                      font=F_BODY_B, cursor="hand2", padx=14, pady=8, command=command)
        b.bind("<Enter>", lambda e: b.config(bg=BTN_HOVER))
        b.bind("<Leave>", lambda e: b.config(bg=BTN))
        return b
    return pill_button(w, text, command, fg=TEXT, bg=CARD, hover_bg=SURFACE_2, hover_fg=TEXT)

# Соответствие клавиш Tk-событий спецификациям горячей клавиши (pynput-стиль)
_TK_MOD_KEYS = {"Control_L", "Control_R", "Shift_L", "Shift_R",
                "Alt_L", "Alt_R", "Meta_L", "Meta_R"}
_TK_SPECIAL = {
    "space": "space", "Return": "enter", "Escape": "esc", "Tab": "tab",
    "BackSpace": "backspace", "Delete": "delete", "Insert": "insert",
    "Home": "home", "End": "end", "Prior": "page_up", "Next": "page_down",
    "Up": "up", "Down": "down", "Left": "left", "Right": "right",
    "Pause": "pause", "Print": "print_screen", "Scroll_Lock": "scroll_lock",
    "Num_Lock": "num_lock", "Caps_Lock": "caps_lock",
    "F1": "f1", "F2": "f2", "F3": "f3", "F4": "f4", "F5": "f5", "F6": "f6",
    "F7": "f7", "F8": "f8", "F9": "f9", "F10": "f10", "F11": "f11", "F12": "f12",
}
# Иконка (base64). Заполняется автоматически при сборке exe.
ICON_B64 = ""


def get_icon_path():
    """Иконка рядом с exe/скриптом, иначе распаковываем встроенную."""
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(app_dir, "mic.ico")
    if os.path.exists(p):
        return p
    if ICON_B64:
        p = os.path.join(tempfile.gettempdir(), "mic_switcher_ico.ico")
        if not os.path.exists(p):
            with open(p, "wb") as f:
                f.write(base64.b64decode(ICON_B64))
        return p
    return None


def _hostapi_names():
    """Словарь {индекс hostapi: имя}."""
    try:
        return {i: h["name"] for i, h in enumerate(sd.query_hostapis())}
    except Exception:
        return {}


def _wasapi_hostapi():
    """Индекс host API 'Windows WASAPI', или None.

    Индекс host API = позиция в списке query_hostapis().
    """
    try:
        for i, h in enumerate(sd.query_hostapis()):
            if "wasapi" in h["name"].lower():
                return i
    except Exception:
        pass
    return None


def find_cable_input():
    """Индекс выходного устройства VAC (куда пишем звук), или None.

    Важно: выбирать именно WASAPI-устройство — именно его читает Discord.
    PortAudio видит один и тот же кабель под несколькими host API (MME,
    DirectSound, WASAPI, WDM-KS); писать нужно в WASAPI-копию.
    """
    wasapi = _wasapi_hostapi()
    fallback = None
    try:
        for d in sd.query_devices():
            if d["max_output_channels"] > 0 and "virtual audio cable" in d["name"].lower():
                if wasapi is not None and d["hostapi"] == wasapi:
                    return d["index"]
                if fallback is None:
                    fallback = d["index"]
        return fallback
    except Exception:
        pass
    return None


def find_cable_input_name():
    """Имя входного устройства VAC (для подсказки: что выбрать в Discord), или None."""
    try:
        for d in sd.query_devices():
            if d["max_input_channels"] > 0 and "virtual audio cable" in d["name"].lower():
                return d["name"]
    except Exception:
        pass
    return None


def find_input_device(mic_name):
    """Индекс входного устройства по имени (предпочитаем WASAPI), или None.

    WASAPI важнее, потому что именно так приложения (Discord и др.)
    читают устройство; MME/DS-копии того же микрофона могут работать
    иначе.
    """
    wasapi = _wasapi_hostapi()
    exact_fallback = None
    low = mic_name.lower()
    try:
        for d in sd.query_devices():
            if d["max_input_channels"] > 0 and d["name"].lower() == low:
                if wasapi is not None and d["hostapi"] == wasapi:
                    return d["index"]
                if exact_fallback is None:
                    exact_fallback = d["index"]
        if exact_fallback is not None:
            return exact_fallback
        # точное имя не нашлось — ищем по подстроке (тоже предпочитая WASAPI)
        sub_fallback = None
        for d in sd.query_devices():
            if d["max_input_channels"] > 0 and (low in d["name"].lower() or d["name"].lower() in low):
                if wasapi is not None and d["hostapi"] == wasapi:
                    return d["index"]
                if sub_fallback is None:
                    sub_fallback = d["index"]
        return sub_fallback
    except Exception:
        pass
    return None


class Ring:
    """Кольцевой буфер стерео-аудио (float32). Потокобезопасный."""

    def __init__(self, n=16384, ch=2):
        self.n = n
        self.buf = np.zeros((n, ch), dtype="float32")
        self.r = 0
        self.w = 0
        self.lock = threading.Lock()

    def put(self, x):
        with self.lock:
            c = x.shape[0]
            if c >= self.n:
                c = self.n - 1
                x = x[-c:]
            i = self.w
            if i + c <= self.n:
                self.buf[i:i + c] = x
            else:
                a = self.n - i
                self.buf[i:] = x[:a]
                self.buf[:c - a] = x[a:]
            self.w = (i + c) % self.n

    def get(self, c):
        with self.lock:
            out = np.zeros((c, self.buf.shape[1]), dtype="float32")
            avail = (self.w - self.r) % self.n
            take = min(c, avail)
            if take <= 0:
                return out
            i = self.r
            if i + take <= self.n:
                out[:take] = self.buf[i:i + take]
            else:
                a = self.n - i
                out[:a] = self.buf[i:]
                out[a:take] = self.buf[:take - a]
            self.r = (i + take) % self.n
            return out


def _probe_open(device_idx, sr, is_input):
    """True, если устройство device_idx открывает поток на частоте sr."""
    s = None
    try:
        if is_input:
            s = sd.InputStream(samplerate=sr, device=device_idx, dtype="float32",
                               callback=lambda *a, **k: None)
        else:
            s = sd.OutputStream(samplerate=sr, device=device_idx, dtype="float32",
                               callback=lambda *a, **k: None)
        s.start()
        s.stop()
        s.close()
        return True
    except Exception:
        if s is not None:
            try:
                s.stop()
                s.close()
            except Exception:
                pass
        return False


def _find_device_copy_at_rate(pref_idx, sr, is_input):
    """Индекс копии устройства (по имени pref_idx), которая откроется на частоте sr.

    Порядок: pref_idx, затем остальные копии того же имени (WASAPI-предпочтение).
    None, если не нашлось.
    """
    if pref_idx is None:
        return None
    try:
        pref_name = sd.query_devices(pref_idx)["name"]
    except Exception:
        return None
    wasapi = _wasapi_hostapi()
    candidates = []
    try:
        for d in sd.query_devices():
            if d["name"] != pref_name:
                continue
            if is_input:
                if d["max_input_channels"] > 0:
                    candidates.append(d)
            else:
                if d["max_output_channels"] > 0:
                    candidates.append(d)
    except Exception:
        candidates = []

    def _key(d):
        pref_rank = 0 if d["index"] == pref_idx else 1
        api_rank = 0 if (wasapi is not None and d["hostapi"] == wasapi) else 1
        return (pref_rank, api_rank, d["index"])

    candidates.sort(key=_key)
    for d in candidates:
        if _probe_open(d["index"], sr, is_input):
            return d["index"]
    return None


class CableRouter:
    """Физический микрофон -> VAC (виртуальный микрофон).

    Два раздельных потока: вход = выбранный микрофон, выход = WASAPI-устройство
    VAC (его читает Discord). Связаны кольцевым буфером. Оба потока работают
    на частоте VAC; вход берётся через ту копию микрофона (WASAPI/MME/...),
    которая реально открывается на этой частоте. Работает и тогда, когда
    WASAPI-микрофон заперт на нестандартной частоте (например, 192000 Гц).
    """

    def __init__(self, cable_input_idx):
        self.cable_input_idx = cable_input_idx
        self.in_stream = None
        self.out_stream = None
        self.ring = None
        self.sr = 48000
        self.gain = 1.0
        self.last_error = None
        self.level = 0.0  # живой уровень сигнала (0.0–1.0) для VU-метра

    def set_gain(self, g):
        """Программный усиливатель: 1.0 = 100%, 2.5 = 250% (буст)."""
        try:
            self.gain = max(0.0, min(2.5, float(g)))
        except Exception:
            self.gain = 1.0

    def _target_sr(self):
        try:
            return int(sd.query_devices(self.cable_input_idx)["default_samplerate"])
        except Exception:
            return 48000

    def start(self, mic_name):
        """Переподключает вход на указанный микрофон. True при успехе."""
        self.stop()
        self.last_error = None
        sr = self._target_sr()
        pref = find_input_device(mic_name)
        if pref is None:
            self.last_error = "микрофон не найден"
            return False
        in_dev = _find_device_copy_at_rate(pref, sr, is_input=True)
        if in_dev is None:
            self.last_error = "не удалось открыть микрофон на %d Гц" % sr
            return False
        self.sr = sr
        self.ring = Ring(16384, 2)
        try:
            self.in_stream = sd.InputStream(
                samplerate=sr, device=in_dev, dtype="float32", callback=self._incb)
            self.out_stream = sd.OutputStream(
                samplerate=sr, device=self.cable_input_idx, dtype="float32",
                callback=self._outcb)
            self.in_stream.start()
            self.out_stream.start()
        except Exception as e:
            self.stop()
            self.last_error = "%s: %s" % (type(e).__name__, e)
            return False
        return True

    def _incb(self, indata, frames, time_info, status):
        try:
            if indata.ndim == 1:
                indata = indata.reshape(-1, 1)
            g = self.gain
            if g > 1.0001:
                # Буст выше 100%: усиливаем и мягко ограничиваем пики (без резкого клиппинга).
                y = indata * g
                ay = np.abs(y)
                y = np.where(ay <= 0.9, y, np.sign(y) * (0.9 + (ay - 0.9) ** 1.5))
                y = np.clip(y, -1.0, 1.0)
            else:
                y = indata
            if y.shape[1] >= 2:
                x = y[:, :2].astype("float32", copy=False)
            else:
                x = np.stack([y[:, 0], y[:, 0]], axis=1)
            try:
                self.level = min(1.0, float(np.max(np.abs(y)))) if y.size else 0.0
            except Exception:
                self.level = 0.0
            self.ring.put(x)
        except Exception:
            pass

    def _outcb(self, outdata, frames, time_info, status):
        try:
            data = self.ring.get(frames)
            oc = outdata.shape[1]
            for c in range(oc):
                if c < data.shape[1]:
                    outdata[:, c] = data[:, c]
                else:
                    outdata[:, c] = 0
        except Exception:
            pass

    def stop(self):
        for s in (self.in_stream, self.out_stream):
            try:
                if s is not None:
                    s.stop()
                    s.close()
            except Exception:
                pass
        self.in_stream = None
        self.out_stream = None
        self.ring = None


def list_output_devices():
    """Реальные устройства воспроизведения (без VAC), по одному на имя, приоритет WASAPI."""
    wasapi = _wasapi_hostapi()
    best = {}
    try:
        for d in sd.query_devices():
            if d["max_output_channels"] <= 0:
                continue
            if "virtual audio cable" in d["name"].lower():
                continue
            nm = d["name"]
            cur = best.get(nm)
            if cur is None:
                best[nm] = d
            elif wasapi is not None and d["hostapi"] == wasapi and cur["hostapi"] != wasapi:
                best[nm] = d
    except Exception:
        pass
    items = list(best.values())
    # WASAPI-устройства первыми (они совместимы с WASAPI-входом VAC), затем по индексу
    def _key(d):
        api_rank = 0 if (wasapi is not None and d["hostapi"] == wasapi) else 1
        return (api_rank, d["index"])
    items.sort(key=_key)
    return items


class CableMonitor:
    """Виртуальный микрофон (записывающий конец VAC) -> выбранный реальный выход.

    Позволяет СЛЫШАТЬ виртуальный микрофон на наушниках/колонках: вход = VAC capture,
    выход = устройство вывода. Два раздельных потока на частоте VAC, связаны
    кольцевым буфером; выход берётся через копию устройства, которая реально
    открывается на этой частоте.
    """

    def __init__(self, cap_idx, out_idx):
        self.cap_idx = cap_idx
        self.out_idx = out_idx
        self.in_stream = None
        self.out_stream = None
        self.ring = None
        self.sr = 48000
        self.last_error = None

    def _target_sr(self):
        try:
            return int(sd.query_devices(self.cap_idx)["default_samplerate"])
        except Exception:
            return 48000

    def start(self):
        self.stop()
        self.last_error = None
        sr = self._target_sr()
        out_dev = _find_device_copy_at_rate(self.out_idx, sr, is_input=False)
        if out_dev is None:
            self.last_error = "не удалось открыть устройство вывода на %d Гц" % sr
            return False
        self.sr = sr
        self.ring = Ring(16384, 2)
        try:
            self.in_stream = sd.InputStream(
                samplerate=sr, device=self.cap_idx, dtype="float32", callback=self._incb)
            self.out_stream = sd.OutputStream(
                samplerate=sr, device=out_dev, dtype="float32", callback=self._outcb)
            self.in_stream.start()
            self.out_stream.start()
        except Exception as e:
            self.stop()
            self.last_error = "%s: %s" % (type(e).__name__, e)
            return False
        return True

    def _incb(self, indata, frames, time_info, status):
        try:
            if indata.ndim == 1:
                indata = indata.reshape(-1, 1)
            if indata.shape[1] >= 2:
                x = indata[:, :2].astype("float32", copy=False)
            else:
                x = np.stack([indata[:, 0], indata[:, 0]], axis=1)
            self.ring.put(x)
        except Exception:
            pass

    def _outcb(self, outdata, frames, time_info, status):
        try:
            data = self.ring.get(frames)
            oc = outdata.shape[1]
            for c in range(oc):
                if c < data.shape[1]:
                    outdata[:, c] = data[:, c]
                else:
                    outdata[:, c] = 0
        except Exception:
            pass

    def stop(self):
        for s in (self.in_stream, self.out_stream):
            try:
                if s is not None:
                    s.stop()
                    s.close()
            except Exception:
                pass
        self.in_stream = None
        self.out_stream = None
        self.ring = None


def app_dir():
    """Папка, где лежит exe (или скрипт)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def config_path():
    return os.path.join(app_dir(), "mic_switcher.json")


def load_config():
    """Возвращает (hotkey, set(exclude), dict{mic.id: громкость 0-250})."""
    try:
        with open(config_path(), encoding="utf-8") as f:
            data = json.load(f)
        hotkey = str(data.get("hotkey") or HOTKEY).lower()
        exclude = set(str(x).lower() for x in data.get("exclude", []))
        volumes = {}
        for k, v in (data.get("volumes") or {}).items():
            try:
                volumes[str(k)] = int(v)
            except Exception:
                pass
        return hotkey, exclude, volumes
    except Exception:
        return HOTKEY, set(), {}


def save_config(hotkey, exclude, volumes=None):
    # Если громкости не переданы — читаем уже сохранённые, чтобы не затереть их.
    if volumes is None:
        try:
            with open(config_path(), encoding="utf-8") as f:
                volumes = {str(k): int(v) for k, v in (json.load(f).get("volumes") or {}).items()}
        except Exception:
            volumes = {}
    # Сохраняем язык, если он уже задан
    lang = load_lang()
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump({"hotkey": hotkey, "exclude": sorted(exclude),
                       "volumes": volumes, "lang": lang},
                      f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _detect_system_lang():
    """Определить язык интерфейса по языку Windows.
    Русский Windows → "ru", всё остальное → "en"."""
    try:
        import ctypes
        lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        lang_id = lcid & 0xFFFF
        if lang_id == 0x0419:  # Russian
            return "ru"
        return "en"
    except Exception:
        pass
    try:
        import locale
        loc = locale.getdefaultlocale()
        if loc and loc[0] and loc[0].lower().startswith("ru"):
            return "ru"
    except Exception:
        pass
    return "en"


def load_lang():
    """Возвращает сохранённый язык ("ru"/"en").
    Если в конфиге ещё нет — определяет по языку Windows и сохраняет."""
    try:
        with open(config_path(), encoding="utf-8") as f:
            data = json.load(f)
        lang = data.get("lang")
        if lang in ("ru", "en"):
            return lang
    except Exception:
        pass
    # Первый запуск (или конфиг повреждён) — определяем по системе
    detected = _detect_system_lang()
    save_lang(detected)
    return detected


def save_lang(lang):
    """Сохранить язык в конфиг."""
    if lang not in ("ru", "en"):
        lang = "ru"
    try:
        with open(config_path(), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    data["lang"] = lang
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _autostart_cmd():
    if getattr(sys, "frozen", False):
        return '"%s"' % sys.executable
    return '"%s" "%s"' % (sys.executable, os.path.abspath(__file__))


def autostart_enabled():
    """Включён ли автозапуск в реестре (HKCU Run)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            winreg.QueryValueEx(k, "MicSwitcher")
            return True
    except Exception:
        return False


def set_autostart(enable):
    """Включить/выключить автозапуск приложения при входе в Windows."""
    try:
        import winreg
        path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as k:
            if enable:
                winreg.SetValueEx(k, "MicSwitcher", 0, winreg.REG_SZ, _autostart_cmd())
            else:
                try:
                    winreg.DeleteValue(k, "MicSwitcher")
                except FileNotFoundError:
                    pass
    except Exception:
        pass


def _find_discord_hwnd():
    """HWND окна Discord (по заголовку), или None."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        result = {"hwnd": None}
        CB = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return 1
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return 1
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if "discord" in buf.value.lower():
                result["hwnd"] = hwnd
                return 0
            return 1
        user32.EnumWindows(CB(cb), 0)
        return result["hwnd"]
    except Exception:
        return None


class MicSwitcher:
    def __init__(self):
        self.hidden = False
        self.popup = None
        self.index = 0
        self.hotkey, self.exclude, self.mic_vol = load_config()
        self.listener = None
        self.settings_win = None
        self.tray_icon = None
        self._tray_q = queue.Queue()
        self._hk_capturing = False
        self._hotkey_q = queue.Queue()

        self.root = tk.Tk()
        self.root.title("Переключатель микрофонов")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        self.root.minsize(320, 0)
        # Крестик в заголовке прячет окно в трей (приложение продолжает работать),
        # а не закрывает его. Полностью закрыть — кнопкой «Выйти» или из трея.
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        icon = get_icon_path()
        if icon:
            try:
                self.root.iconbitmap(icon)
            except Exception:
                pass

        # ── Сначала данные и логика (состояние), потом интерфейс ──
        self.refresh()

        # Виртуальный микрофон (VAC)
        self.cable_idx = find_cable_input()
        self.vac_name = find_cable_input_name() or "Line 1 (Virtual Audio Cable)"
        self.router = None
        self.monitor = None
        if self.cable_idx is not None and self.current is not None:
            try:
                r = CableRouter(self.cable_idx)
                if r.start(self.current.FriendlyName):
                    r.set_gain(self._gain_for(self.current.id))
                    self.router = r
                else:
                    self.router = None
                    self.root.after(0, lambda e=r.last_error: self.show_notification(
                        "⚠️ Виртуальный микрофон: " + (e or "не удалось запустить")))
            except Exception as e:
                self.router = None
                self.root.after(0, lambda e=e: self.show_notification(
                    "⚠️ Виртуальный микрофон: " + str(e)))

        # ── Заголовок приложения + живой статус + VU-метр + горячая клавиша ──
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill="x", padx=PAD, pady=(16, 2))
        tk.Label(hdr, text="Переключатель микрофонов", bg=BG, fg=TEXT,
                 font=F_H1, anchor="w").pack(side="left", pady=(2, 0))
        self.hdr_dot = tk.Label(hdr, text="●", bg=BG, fg=DIM, font=(FONT, 13), anchor="e")
        self.hdr_dot.pack(side="right", padx=(6, 0))
        # VU-метр уровня активного микрофона (обновляется в _update_level)
        self._lvl = 0.0
        self.vu_canvas = tk.Canvas(hdr, width=112, height=16, bg=CARD,
                                   highlightthickness=0, bd=0)
        self.vu_canvas.pack(side="right", padx=(0, 6))
        self.vu_canvas.create_rectangle(1, 2, 111, 14, fill=BORDER, width=0)
        self.vu_rect = self.vu_canvas.create_rectangle(1, 2, 1, 14, fill=DIM, width=0)
        # Горячая клавиша в заголовке (компактный бейдж)
        self.hk_label = tk.Label(hdr, text="Клавиша: " + self.display_hotkey(),
                                 bg=BG, fg=DIM, font=F_CAP_B, anchor="e")
        self.hk_label.pack(side="right", padx=(0, 10))
        self.hdr_sub = tk.Label(self.root, text="", bg=BG, fg=DIM, font=F_CAP, anchor="w")
        self.hdr_sub.pack(fill="x", padx=PAD, pady=(0, 10))

        # ── Список микрофонов (карточки) ──
        mic_hdr = tk.Frame(self.root, bg=BG)
        mic_hdr.pack(fill="x", padx=PAD, pady=(0, 4))
        tk.Label(mic_hdr, text="Микрофоны", bg=BG, fg=TEXT, font=F_H2, anchor="w").pack(side="left")
        reset_btn = pill_button(mic_hdr, "Сброс громкости", self.reset_volumes,
                                fg=DIM, bg=SURFACE_2, hover_bg=BTN, hover_fg="white")
        reset_btn.pack(side="right")
        self.mic_area = tk.Frame(self.root, bg=BG)
        self.mic_area.pack(fill="x", padx=PAD, pady=(0, 8))
        self.mic_area.grid_columnconfigure(0, weight=1)

        # ── Виртуальный микрофон (карточка со статусом и быстрыми ссылками) ──
        self._build_vac_card()

        # ── Действия ──
        self._build_actions()

        # ── Подсказка ──
        tk.Label(self.root, text="ЛКМ — выбрать   •   колесо — громкость (0–250%)   •   чекбокс — исключить",
                 bg=BG, fg=TEXT_3, font=F_MICRO).pack(anchor="w", padx=PAD, pady=(2, 12))

        self.update_ui()
        # Единый размер окна: одинаковый для основного экрана и настроек.
        # Измеряем оба экрана и фиксируем окно в большем из размеров, чтобы
        # при переключении «основной экран <-> настройки» окно не меняло размер.
        self._win_size = self._compute_win_size()
        try:
            tw, th = self._win_size
            self.root.geometry("%dx%d" % (tw, th))
            self.root.minsize(tw, th)
        except Exception:
            pass
        self._start_tray()
        self.root.after(100, self._poll_hotkey)

    # ---------- интерфейс: вспомогательные построители ----------
    def _update_header_status(self):
        """Живой статус в заголовке (точка + подпись) на основе состояния."""
        try:
            if self.router is not None and self.current is not None:
                self.hdr_dot.config(fg=ACTIVE)
                self.hdr_sub.config(text="Активен: " + self._clean_mic_name(self.current.FriendlyName)
                                    + "  →  Виртуальный микрофон")
            elif getattr(self, "cable_idx", None) is not None:
                self.hdr_dot.config(fg=WARNING)
                self.hdr_sub.config(text="Виртуальный микрофон: роутинг не активен")
            else:
                self.hdr_dot.config(fg=DANGER)
                self.hdr_sub.config(text="VAC не установлен — виртуальный микрофон недоступен")
        except Exception:
            pass

    def _build_vac_card(self):
        """Карточка виртуального микрофона: статус + быстрые ссылки."""
        card = tk.Frame(self.root, bg=CARD)
        card.pack(fill="x", padx=PAD, pady=(2, 8))
        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(top, text="Виртуальный микрофон", bg=CARD, fg=TEXT,
                 font=F_H2, anchor="w").pack(side="left")
        if self.cable_idx is not None and self.router is not None:
            st_txt, st_fg = "●  активен", ACTIVE
        elif self.cable_idx is not None:
            st_txt, st_fg = "●  не активен", WARNING
        else:
            st_txt, st_fg = "●  недоступен", DANGER
        tk.Label(top, text=st_txt, bg=CARD, fg=st_fg, font=F_CAP_B, anchor="e").pack(side="right")
        tk.Label(card, text=(self.vac_name or "не найден"), bg=CARD, fg=DIM,
                 font=F_CAP, anchor="w").pack(fill="x", padx=14, pady=(0, 8))
        links = tk.Frame(card, bg=CARD)
        links.pack(fill="x", padx=14, pady=(0, 12))
        self.discord_link = pill_button(links, "Discord: настроить звук",
                                        self.open_discord_voice_settings)
        self.discord_link.pack(side="left")
        self.win_sound_link = pill_button(links, "Windows: настройки звука",
                                          self.open_windows_sound_settings)
        self.win_sound_link.pack(side="left", padx=(8, 0))

    def _build_actions(self):
        """Блок действий: основная CTA + вторичные кнопки."""
        self.switch_btn = tk.Button(
            self.root, text="Сменить микрофон   (" + self.display_hotkey() + ")",
            bg=BTN, fg="white", activebackground=BTN_HOVER, activeforeground="white",
            relief="flat", bd=0, highlightthickness=0,
            font=F_BTN, cursor="hand2", padx=16, pady=11, command=self.toggle)
        self.switch_btn.pack(fill="x", padx=PAD, pady=(2, 8))
        self.switch_btn.bind("<Enter>", lambda e: self.switch_btn.config(bg=BTN_HOVER))
        self.switch_btn.bind("<Leave>", lambda e: self.switch_btn.config(bg=BTN))

        row = tk.Frame(self.root, bg=BG)
        row.pack(fill="x", padx=PAD, pady=(0, 4))
        self.settings_btn = pill_button(row, "Настройки", self.open_settings,
                                        fg=TEXT, bg=CARD, hover_bg=SURFACE_2, hover_fg=TEXT)
        self.settings_btn.pack(side="left")
        self.quit_btn = pill_button(row, "Завершить сеанс программы", self.quit_app,
                                    fg=DANGER, bg=CARD, hover_bg="#3a2030", hover_fg=DANGER)
        self.quit_btn.pack(side="left", padx=(8, 0))

    # ---------- логика ----------
    def open_discord_voice_settings(self):
        """Открыть настройки голоса в Discord и вывести его окно на передний план."""
        try:
            os.startfile("discord://-/settings/voice")
        except Exception:
            pass
        threading.Thread(target=self._raise_discord, daemon=True).start()

    def open_windows_sound_settings(self):
        """Открыть настройки звука Windows (Параметры → Система → Звук)."""
        for uri in ("ms-settings:sound", "control mmsys.cpl"):
            try:
                os.startfile(uri)
                return
            except Exception:
                continue

    def _raise_discord(self):
        """Найти окно Discord и поднять его поверх остальных."""
        import ctypes, time
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = None
        for _ in range(30):
            hwnd = _find_discord_hwnd()
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

    def get_enumerator(self):
        return comtypes.CoCreateInstance(
            CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER
        )

    def is_excluded(self, mic):
        name = mic.FriendlyName.lower()
        # Виртуальные кабели никогда не являются физическими микрофонами
        if "virtual audio cable" in name or "virtual cable" in name:
            return True
        return any(e in name for e in self.exclude)

    def refresh(self):
        """Свежий список микрофонов, активные (не исключённые) и текущий дефолт."""
        enum = self.get_enumerator()
        coll = enum.EnumAudioEndpoints(EDataFlow.eCapture.value, DEVICE_STATE.ACTIVE.value)
        self.mics = []
        for i in range(coll.GetCount()):
            self.mics.append(AudioUtilities.CreateDevice(coll.Item(i)))
        self.active = [m for m in self.mics if not self.is_excluded(m)]
        self.current = None
        if self.mics:
            try:
                cur = enum.GetDefaultAudioEndpoint(EDataFlow.eCapture.value, ERole.eConsole.value)
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

    def set_default(self):
        cfg = comtypes.CoCreateInstance(
            CLSID_CPolicyConfigClient, IPolicyConfig, comtypes.CLSCTX_INPROC_SERVER
        )
        cfg.SetDefaultEndpoint(self.active[self.index].id, ERole.eConsole.value)

    def _switch_to(self, mic):
        prev = self.current
        self.set_default()
        self.current = mic
        vac_ok = True
        vac_err = None
        if self.router is not None:
            try:
                if not self.router.start(mic.FriendlyName):
                    vac_ok = False
                    vac_err = self.router.last_error or "не удалось запустить"
                else:
                    self.router.set_gain(self._gain_for(mic.id))
            except Exception as e:
                vac_ok = False
                vac_err = str(e)
        self.update_ui()
        self._flash_active()
        name = self._clean_mic_name(mic.FriendlyName)
        if self.router is not None and vac_ok:
            act = None
            if prev is not None and prev.id != mic.id and not self.is_excluded(prev):
                act = ("Отменить", lambda pv=prev: self._switch_to(pv))
            self.show_notification("🎤 Микрофон: " + name + "  →  Виртуальный микрофон", action=act)
        elif self.router is not None and not vac_ok:
            self.show_notification("🎤 Микрофон: " + name + "   ⚠️ VAC: " + (vac_err or "сбой"))
        else:
            self.show_notification("🎤 Микрофон: " + name)

    def toggle(self):
        self.refresh()
        if not self.active:
            return
        self.index = (self.index + 1) % len(self.active)
        self._switch_to(self.active[self.index])

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
        """Правый клик — исключить микрофон из переключения (или вернуть)."""
        name = mic.FriendlyName.lower()
        if name in self.exclude:
            self.exclude.discard(name)
        else:
            self.exclude.add(name)
        save_config(self.hotkey, self.exclude)
        self.refresh()
        self._build_mic_rows()
        if self.is_excluded(mic):
            self.show_notification("🎤 Исключён: " + mic.FriendlyName)
        else:
            self.show_notification("🎤 Возвращён: " + mic.FriendlyName)

    # ---------- горячая клавиша ----------
    def on_hotkey(self):
        """Колбэк из потока слушателя: просто кладём заявку в очередь.
        Выполнение toggle() — в главном потоке (там есть COM и tkinter)."""
        self._hotkey_q.put(1)

    def _poll_hotkey(self):
        try:
            while True:
                self._hotkey_q.get_nowait()
                self.toggle()
        except queue.Empty:
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
        try:
            self._update_level()
        except Exception:
            pass
        self.root.after(100, self._poll_hotkey)

    def display_hotkey(self):
        """Спека pynput → человекочитаемый вид: "ctrl+f10" → "Ctrl+F10"."""
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

    def change_hotkey(self):
        """Диалог выбора новой горячей клавиши."""
        from tkinter import messagebox, simpledialog
        new = simpledialog.askstring(
            "Горячая клавиша",
            "Новая горячая клавиша (например: f10, f12, ctrl+m, alt+f1):",
            initialvalue=self.hotkey, parent=self.root,
        )
        if new is None:
            return
        new = new.strip().lower()
        if not new or new == self.hotkey:
            return
        try:
            Hotkey(new, lambda: None)  # проверка синтаксиса
        except Exception as e:
            messagebox.showerror(
                "Неверная клавиша", str(e), parent=self.root
            )
            return
        self.hotkey = new
        save_config(self.hotkey, self.exclude)
        if self.listener is not None:
            try:
                self.listener.stop()
            except Exception:
                pass
        self.listener = Hotkey(new, self.on_hotkey)
        self.listener.start()
        self.hk_label.config(text="Клавиша: " + self.display_hotkey())
        self.switch_btn.config(text="Сменить   (" + self.display_hotkey() + ")")
        self.show_notification("🔑 Горячая клавиша: " + self.display_hotkey())

    def _clean_mic_name(self, name):
        """'Микрофон (IO Mike SE)' -> 'IO Mike SE' (убираем шаблонный префикс Windows)."""
        s = str(name).strip()
        m = re.match(r'^[^\s(]+\s*\((.+)\)$', s)
        if m:
            return m.group(1).strip()
        m = re.match(r'^[^\s(]+\s*\((.+)$', s)  # обрезанное имя без закрывающей скобки
        if m:
            return m.group(1).strip()
        return s

    def show_notification(self, text, action=None):
        """Уведомление в правом верхнем углу экрана (дизайн-система).

        action — опциональный кортеж (label, callback) для кнопки действия (напр. «Отменить»).
        """
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None
        p = tk.Toplevel(self.root)
        p.overrideredirect(True)
        p.configure(bg=SURFACE_2)
        p.attributes("-topmost", True)
        warn = ("⚠" in text) or ("⚠️" in text)
        bar = WARNING if warn else BTN
        box = tk.Frame(p, bg=CARD)
        box.pack()
        tk.Frame(box, bg=bar, width=4).pack(side="left", fill="y")
        inner = tk.Frame(box, bg=CARD)
        inner.pack(side="left", padx=14, pady=12)
        tk.Label(inner, text=text, bg=CARD, fg=TEXT, font=F_BODY_B, anchor="w") \
            .pack(fill="x", anchor="w")
        if action is not None:
            lbl, cb = action

            def _do(c=cb):
                if self.popup is p:
                    p.destroy()
                if c is not None:
                    c()

            b = tk.Button(inner, text=lbl, bg=BTN, fg="white", relief="flat", bd=0,
                          font=F_CAP_B, cursor="hand2", padx=10, pady=3, command=_do)
            b.bind("<Enter>", lambda e: b.config(bg=BTN_HOVER))
            b.bind("<Leave>", lambda e: b.config(bg=BTN))
            b.pack(anchor="w", pady=(10, 0))
        p.update_idletasks()
        w = p.winfo_reqwidth()
        h = p.winfo_reqheight()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(sw - w - 24, 0)
        y = max(min(24, sh - h - 24), 0)
        p.geometry(f"+{x}+{y}")
        p.withdraw()
        p.deiconify()
        p.after(4200 if action else 2600, lambda: p.destroy() if self.popup is p else None)
        self.popup = p

    # ---------- окно ----------
    def quit_app(self):
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        if self.listener is not None:
            self.listener.stop()
        if self.router is not None:
            self.router.stop()
        self.root.destroy()

    def hide_window(self):
        self.hidden = True
        if self.tray_icon is not None:
            self.root.withdraw()
        else:
            # трей недоступен — сворачиваем в панель задач, чтобы окно не пропало
            self.root.iconify()

    def restore(self):
        self.hidden = False
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None
        self.root.deiconify()

    # ---------- настройки ----------
    def open_settings(self):
        # Настройки — Frame ВНУТРИ основного окна (не отдельное системное окно).
        # Окно уже имеет единый размер под оба экрана, поэтому здесь размер
        # НЕ меняется — накрываем контент через place().
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.lift()
            try:
                self.root.focus_force()
            except Exception:
                pass
            return
        w = tk.Frame(self.root, bg=BG)
        self.settings_win = w
        self._build_settings_content(w)
        try:
            if getattr(self, "_win_size", None):
                tw, th = self._win_size
                self.root.geometry("%dx%d" % (tw, th))
        except Exception:
            pass
        w.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        try:
            w.lift()
            self.root.focus_force()
        except Exception:
            pass

    def _build_settings_content(self, w):
        """Задает содержимое настроек во фрейм w (без изменения размера окна)."""
        # --- Виртуальный микрофон ---
        settings_header(w, "Виртуальный микрофон")
        routing = "активен" if (self.cable_idx is not None and self.router is not None) else "не активен"
        tk.Label(w, text="VAC: " + (self.vac_name or "не найден") + "    ·    Роутинг: " + routing,
                 bg=BG, fg=DIM, font=F_BODY, anchor="w").pack(fill="x", padx=PAD, pady=(0, 8))
        settings_button(w, "Проверить виртуальный микрофон", self.test_virtual_mic, primary=True) \
            .pack(anchor="w", padx=PAD)
        self.vac_test_label = tk.Label(w, text="", bg=BG, fg=DIM,
                                       font=F_BODY, justify="left", anchor="w", wraplength=430)
        self.vac_test_label.pack(fill="x", padx=PAD, pady=(8, 0))

        settings_divider(w)

        # --- Прослушать виртуальный микрофон ---
        settings_header(w, "Прослушать виртуальный микрофон")
        tk.Label(w, text="Ведёт звук вирт. микрофона на устройство вывода, чтобы его услышать",
                 bg=BG, fg=DIM, font=F_CAP, wraplength=430, justify="left") \
            .pack(anchor="w", padx=PAD, pady=(0, 8))
        mon_row = tk.Frame(w, bg=BG)
        mon_row.pack(fill="x", padx=PAD)
        tk.Label(mon_row, text="Устройство вывода:", bg=BG, fg=TEXT, font=F_BODY).pack(side="left")
        self.mon_out_combo = ttk.Combobox(mon_row, state="readonly", font=F_BODY)
        self.mon_out_combo.pack(side="left", fill="x", expand=True, padx=(8, 0))
        _cap = self._find_vac_capture()
        _cap_api = _cap["hostapi"] if _cap else None
        self._mon_devices = list_output_devices()
        if _cap_api is not None:
            _compat = [d for d in self._mon_devices if d["hostapi"] == _cap_api]
            if _compat:
                self._mon_devices = _compat
        self._mon_by_name = {d["name"]: d for d in self._mon_devices}
        self.mon_out_combo["values"] = [d["name"] for d in self._mon_devices]
        if self._mon_devices:
            # По умолчанию — устройство вывода, выбранное по умолчанию в Windows.
            # Имена PortAudio обрезаются по-разному на разных backend'ах (MME/WASAPI),
            # поэтому ищем точное совпадение, затем лучшее совпадение по префиксу.
            self.mon_out_combo.current(self._find_default_index(self._mon_devices))
        self.mon_btn = settings_button(w, "Прослушать", self.toggle_monitor, primary=True)
        self.mon_btn.pack(anchor="w", padx=PAD, pady=(10, 4))
        self.mon_label = tk.Label(w, text="", bg=BG, fg=DIM,
                                  font=F_BODY, justify="left", anchor="w", wraplength=430)
        self.mon_label.pack(fill="x", padx=PAD, pady=(0, 0))

        settings_divider(w)

        # --- Горячая клавиша ---
        settings_header(w, "Горячая клавиша")
        hk_row = tk.Frame(w, bg=BG)
        hk_row.pack(fill="x", padx=PAD)
        # Поле горячей клавиши — это Button с command: клик гарантированно
        # запускает обработчик (в отличие от Label + bind, который не срабатывал).
        self.hk_field = tk.Button(
            hk_row, text=self.display_hotkey(), bg=CARD, fg=TEXT,
            font=F_BODY_B, padx=16, pady=6, cursor="hand2",
            relief="flat", bd=0, activebackground=CARD,
            command=self._begin_hotkey_capture,
        )
        self.hk_field.pack(side="left")
        self.hk_field.bind("<Enter>",
                           lambda e: None if self._hk_capturing else self.hk_field.config(fg=BTN))
        self.hk_field.bind("<Leave>",
                           lambda e: None if self._hk_capturing else self.hk_field.config(fg=TEXT))
        tk.Label(w, text="Кликните по полю и нажмите нужную клавишу (Esc — отмена)",
                 bg=BG, fg=DIM, font=F_CAP, wraplength=430, justify="left") \
            .pack(anchor="w", padx=PAD, pady=(8, 0))

        settings_divider(w)

        # --- Автозапуск ---
        settings_header(w, "Автозапуск")
        self.auto_var = tk.BooleanVar(value=autostart_enabled())
        tk.Checkbutton(
            w, text="Запускать при входе в Windows",
            variable=self.auto_var, bg=BG, fg=TEXT, activebackground=BG,
            activeforeground=TEXT, selectcolor=CARD, font=F_BODY, anchor="w",
            command=self._apply_autostart,
        ).pack(fill="x", padx=PAD, pady=(2, 0))

        # --- Назад ---
        back = tk.Button(w, text="←  Назад", bg=CARD, fg=TEXT, activebackground=SURFACE_2,
                         activeforeground=TEXT, relief="flat", bd=0, font=F_BODY_B,
                         cursor="hand2", padx=16, pady=8, command=self._close_settings)
        back.bind("<Enter>", lambda e: back.config(bg=SURFACE_2))
        back.bind("<Leave>", lambda e: back.config(bg=CARD))
        back.pack(pady=(20, 16))

    def _compute_win_size(self):
        """Единый размер окна, в который влезает и основной экран, и настройки."""
        try:
            self.root.update_idletasks()
            main_w = max(460, self.root.winfo_reqwidth())
            main_h = max(220, self.root.winfo_reqheight())
        except Exception:
            main_w, main_h = 460, 520
        sw, sh = 460, 520
        tmp = tk.Frame(self.root, bg=BG)
        try:
            self._build_settings_content(tmp)
            tmp.update_idletasks()
            sw = max(460, tmp.winfo_reqwidth())
            sh = max(220, tmp.winfo_reqheight())
        except Exception:
            pass
        finally:
            tmp.destroy()
        return (max(main_w, sw), max(main_h, sh))

    def _close_settings(self):
        if self._hk_capturing:
            self._end_hotkey_capture()
        try:
            self.stop_monitor()
        except Exception:
            pass
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.destroy()
        self.settings_win = None
        # Единый размер окна — при возврате на основной экран размер не меняем
        try:
            if getattr(self, "_win_size", None):
                tw, th = self._win_size
                self.root.geometry("%dx%d" % (tw, th))
        except Exception:
            pass
        try:
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def _apply_autostart(self):
        on = bool(self.auto_var.get())
        set_autostart(on)
        self.show_notification("🚀 Автозапуск: " + ("включён" if on else "выключен"))

    # ---------- горячая клавиша (захват нажатием — нативный Tk, без pynput) ----------
    def _begin_hotkey_capture(self):
        self._log("begin capture called")
        if self._hk_capturing:
            self._log("early return: already capturing")
            return
        w = self.settings_win
        if w is None or not w.winfo_exists():
            self._log("early return: no settings window")
            return
        self._hk_capturing = True
        self._cap_mods = set()
        self._log("begin capture")
        self.hk_field.config(text="Нажмите клавишу…  (Esc — отмена)",
                             fg="white", bg=ACTIVE)
        # Временно остановить глобальный слушатель, чтобы старая клавиша
        # не переключила микрофон прямо во время ввода.
        self._cap_old_listener = self.listener
        if self._cap_old_listener is not None:
            try:
                self._cap_old_listener.stop()
            except Exception:
                pass
        # Захват клавиши через Tk. Настройки теперь Frame внутри основного окна,
        # поэтому биндим <Key> на корневое окно (toplevel) — так клавиша
        # гарантированно дойдёт до обработчика независимо от фокуса.
        try:
            self.root.update_idletasks()
            self.root.lift()
            self.root.focus_force()
            self.root.bind("<Key>", self._cap_on_key)
            self._log("tk capture bound")
        except Exception as e:
            self._end_hotkey_capture(restart_old=True)
            self._log("bind failed: %s" % e)
            from tkinter import messagebox
            messagebox.showerror("Ошибка", "Не удалось начать ввод: %s" % e,
                                 parent=self.root)

    def _cap_on_key(self, event):
        if not self._hk_capturing:
            return
        if event.keysym == "Escape":
            self._log("capture cancelled")
            self._end_hotkey_capture(restart_old=True)
            return "break"
        if event.keysym in _TK_MOD_KEYS:
            self._set_cap_text("Добавьте основную клавишу…")
            return "break"
        res = self._tk_key_to_spec(event)
        if res is None:
            self._cap_fail("Эту клавишу нельзя назначить")
            return "break"
        mods, main = res
        full = "+".join(sorted(mods) + [main])
        try:
            Hotkey(full, lambda: None)  # валидация
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
        if keysym in _TK_SPECIAL:
            main = _TK_SPECIAL[keysym]
        elif char and len(char) == 1:
            main = char.lower()
        else:
            return None
        return mods, main

    def _set_cap_text(self, t):
        if self.hk_field is not None and self.hk_field.winfo_exists():
            self.hk_field.config(text=t, fg="white", bg=ACTIVE)

    def _cap_fail(self, msg):
        self._end_hotkey_capture(restart_old=True)
        from tkinter import messagebox
        messagebox.showerror("Неверная клавиша", msg, parent=self.settings_win)

    def _cap_apply(self, full):
        self._hk_capturing = False
        self._cap_mods = set()
        try:
            self.root.unbind("<Key>")
        except Exception:
            pass
        self._cap_old_listener = None
        self._apply_hotkey(full)

    def _end_hotkey_capture(self, restart_old=True):
        self._hk_capturing = False
        self._cap_mods = set()
        try:
            self.root.unbind("<Key>")
        except Exception:
            pass
        old = getattr(self, "_cap_old_listener", None)
        self._cap_old_listener = None
        if restart_old and old is not None:
            try:
                old.start()
            except Exception:
                pass
        if self.hk_field is not None and self.hk_field.winfo_exists():
            self.hk_field.config(text=self.display_hotkey(), fg=TEXT, bg=CARD)

    def _log(self, msg):
        try:
            base = os.path.dirname(sys.executable if getattr(sys, "frozen", False)
                                   else os.path.abspath(__file__))
            with open(os.path.join(base, "mic_switcher_err.log"), "a", encoding="utf-8") as f:
                f.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
        except Exception:
            pass

    def _apply_hotkey(self, spec):
        self.hotkey = spec
        save_config(self.hotkey, self.exclude)
        if self.listener is not None:
            try:
                self.listener.stop()
            except Exception:
                pass
        self.listener = Hotkey(spec, self.on_hotkey)
        self.listener.start()
        self.hk_label.config(text="Клавиша: " + self.display_hotkey())
        self.switch_btn.config(text="Сменить   (" + self.display_hotkey() + ")")
        if getattr(self, "hk_field", None) is not None and self.hk_field.winfo_exists():
            self.hk_field.config(text=self.display_hotkey(), fg=TEXT, bg=CARD)
        self.show_notification("🔑 Горячая клавиша: " + self.display_hotkey())

    def _find_vac_capture(self):
        """Устройство захвата VAC (предпочитаем WASAPI), или None."""
        w = _wasapi_hostapi()
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

    def test_virtual_mic(self):
        self.vac_test_label.config(text="⏳ Проверяю виртуальный микрофон…", fg=DIM)
        threading.Thread(target=self._run_vac_test, daemon=True).start()

    def _run_vac_test(self):
        """Round-trip: пишем тон в выход VAC и считываем с входа. Громко => работает."""
        import numpy as np
        import time
        render = find_cable_input()
        cap = self._find_vac_capture()
        if render is None or cap is None:
            self.root.after(0, lambda: self.vac_test_label.config(
                text="❌ VAC не найден — установите Virtual Audio Cable", fg="#f59e0b"))
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
            self.root.after(0, lambda: self.vac_test_label.config(
                text="⚠️ Ошибка при проверке: " + str(e), fg="#f59e0b"))
            return
        arr = np.concatenate(collected) if collected else np.zeros((1, nch), "float32")
        rms = float(np.sqrt(np.mean(arr ** 2)))
        if rms > 5e-3:
            msg = "✅ Виртуальный микрофон работает (уровень %.3f). В Discord/Windows будет слышно." % rms
            self.root.after(0, lambda: self.vac_test_label.config(text=msg, fg=ACTIVE))
        else:
            msg = ("⚠️ Сигнал слабый (уровень %.6f). Убедитесь, что в Discord выбран "
                   "микрофон «%s»") % (rms, self.vac_name)
            self.root.after(0, lambda: self.vac_test_label.config(text=msg, fg="#f59e0b"))

    # ---------- прослушка виртуального микрофона ----------
    def _find_default_index(self, devices):
        """Индекс в `devices` устройства вывода, выбранного по умолчанию в Windows.

        Имена устройств PortAudio могут обрезаться по-разному на разных
        backend'ах (MME/WASAPI), поэтому сначала ищем точное совпадение,
        затем лучшее совпадение по префиксу. Если ничего не найдено — 0.
        """
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

    def _mon_set(self, text, fg=DIM):
        try:
            self.mon_label.config(text=text, fg=fg)
        except Exception:
            pass

    def toggle_monitor(self):
        if self.monitor is not None:
            self.stop_monitor()
            return
        self.start_monitor()

    def start_monitor(self):
        cap = self._find_vac_capture()
        if cap is None:
            self._mon_set("❌ VAC не найден — установите Virtual Audio Cable", "#f59e0b")
            return
        name = self.mon_out_combo.get().strip()
        out = self._mon_by_name.get(name)
        if out is None:
            self._mon_set("❌ Выберите устройство вывода", "#f59e0b")
            return
        # выход должен быть того же host API, что и захват VAC (WASAPI), иначе PortAudio откажет
        if out["hostapi"] != cap["hostapi"]:
            compat = [d for d in self._mon_devices if d["hostapi"] == cap["hostapi"]]
            if compat:
                out = compat[0]
        try:
            m = CableMonitor(cap["index"], out["index"])
            if not m.start():
                self._mon_set("⚠️ Не удалось начать прослушку: " + (m.last_error or ""), "#f59e0b")
                return
        except Exception as e:
            self._mon_set("⚠️ Не удалось начать прослушку: " + str(e), "#f59e0b")
            return
        self.monitor = m
        try:
            self.mon_btn.config(text="⏹  Остановить прослушку")
        except Exception:
            pass
        self._mon_set("🎧 Слушайте: вирт. микрофон → «" + out["name"] + "»", ACTIVE)

    def stop_monitor(self):
        if self.monitor is not None:
            try:
                self.monitor.stop()
            except Exception:
                pass
            self.monitor = None
        try:
            self.mon_btn.config(text="🎧  Прослушать")
        except Exception:
            pass
        self._mon_set("Прослушка остановлена", DIM)

    # ---------- трей ----------
    def _start_tray(self):
        try:
            import pystray
            from PIL import Image
            img = None
            p = get_icon_path()
            if p:
                try:
                    img = Image.open(p).convert("RGBA")
                except Exception:
                    img = None
            if img is None:
                img = Image.new("RGBA", (64, 64), (59, 130, 246, 255))
            show_item = pystray.MenuItem("Показать окно", self._tray_show, default=True)
            quit_item = pystray.MenuItem("Выход", self._tray_quit)
            self.tray_icon = pystray.Icon("MicSwitcher", img, "Переключатель микрофонов",
                                          pystray.Menu(show_item, quit_item))
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as e:
            print("tray error:", e)
            self.tray_icon = None

    def _tray_show(self, icon, item):
        self._tray_q.put("show")

    def _tray_quit(self, icon, item):
        self._tray_q.put("quit")

    def update_ui(self):
        self._build_mic_rows()
        self._update_header_status()

    def get_mic_volume(self, mic):
        """Громкость микрофона (0.0–1.0), или None."""
        try:
            return float(mic.EndpointVolume.GetMasterVolumeLevelScalar())
        except Exception:
            return None

    def set_mic_volume(self, mic, frac):
        """Системный уровень микрофона в Windows (0.0–1.0 = 0–100%). Буст >100% — через gain."""
        try:
            mic.EndpointVolume.SetMasterVolumeLevelScalar(max(0.0, min(1.0, float(frac))), None)
        except Exception:
            pass

    def _gain_for(self, mic_id):
        """Программный буст по сохранённой громкости: >100% → gain, иначе 1.0."""
        v = self.mic_vol.get(mic_id, 100)
        try:
            v = float(v)
        except Exception:
            return 1.0
        return (v / 100.0) if v > 100.0 else 1.0

    def _on_volume_change(self, mic, value):
        try:
            val = float(value)
        except Exception:
            return
        val = max(0.0, min(250.0, val))
        self.mic_vol[mic.id] = int(round(val))
        # Живое обновление подписи громкости в карточке микрофона.
        for row in self.mic_rows:
            if row["mic"].id == mic.id and "val" in row:
                try:
                    row["val"].config(text=str(int(round(val))) + "%")
                except Exception:
                    pass
                break
        if val <= 100.0:
            # Обычный диапазон: ставим системный уровень Windows (0–100%).
            self.set_mic_volume(mic, val / 100.0)
        else:
            # Буст выше 100%: Windows на максимуме, остальное — программный gain в роутере.
            self.set_mic_volume(mic, 1.0)
        gain = self._gain_for(mic.id)
        if self.current is not None and mic.id == self.current.id and self.router is not None:
            self.router.set_gain(gain)
        save_config(self.hotkey, self.exclude, self.mic_vol)

    def _build_mic_rows(self):
        """Список микрофонов (карточки). Активный — сверху, исключённые — вниз.

        ЛКМ — выбрать, колесо — громкость, чекбокс / ПКМ — исключить.
        """
        for w in self.mic_area.winfo_children():
            w.destroy()
        self.mic_rows = []
        # VAC (виртуальный кабель) не показываем в списке: это приёмник звука,
        # а не источник — переключаться на него бессмысленно.
        mics = [m for m in self.mics
                if "virtual audio cable" not in (m.FriendlyName or "").lower()]
        if not mics:
            tk.Label(self.mic_area, text="Микрофоны не найдены", bg=BG, fg=DIM,
                     font=F_CAP, anchor="w").grid(row=0, column=0, sticky="w", pady=4)
            return

        def _rank(mic):
            excluded = self.is_excluded(mic)
            is_active = (not excluded) and (self.current is not None and mic.id == self.current.id)
            return 0 if is_active else (2 if excluded else 1)
        ordered = sorted(mics, key=lambda m: (_rank(m), mics.index(m)))

        r = 0
        divider_done = False
        for mic in ordered:
            excluded = self.is_excluded(mic)
            is_active = (not excluded) and (self.current is not None and mic.id == self.current.id)

            # тонкий разделитель перед первой исключённой строкой
            if excluded and not divider_done:
                tk.Frame(self.mic_area, bg=BORDER, height=1).grid(row=r, column=0, sticky="we", pady=6)
                r += 1
                divider_done = True

            row_bg = ACCENT_SOFT if is_active else CARD
            bar_fg = BTN if is_active else CARD
            if excluded:
                name_fg, name_font, tag, tag_fg = TEXT_3, F_CAP, "исключён", DANGER
            elif is_active:
                name_fg, name_font, tag, tag_fg = TEXT, F_BODY_B, "активен", ACTIVE
            else:
                name_fg, name_font, tag, tag_fg = TEXT, F_BODY, "", TEXT_3

            card = tk.Frame(self.mic_area, bg=row_bg)
            card.grid(row=r, column=0, sticky="we", pady=2)
            card.grid_columnconfigure(2, weight=1)
            r += 1

            # левый акцент-бар (выделение активного)
            tk.Frame(card, bg=bar_fg, width=3).grid(row=0, column=0, sticky="ns")
            # чекбокс «исключён»
            cb_var = tk.BooleanVar(value=excluded)
            cb = tk.Checkbutton(card, text="исключён", variable=cb_var, bg=row_bg, fg=name_fg,
                                activebackground=row_bg, activeforeground=TEXT,
                                selectcolor=CARD, font=F_CAP, anchor="w",
                                command=lambda m=mic: self.toggle_exclude(m))
            cb.grid(row=0, column=1, sticky="w", padx=(10, 4))
            # имя микрофона
            name_lbl = tk.Label(card, text=mic.FriendlyName, bg=row_bg, fg=name_fg,
                                font=name_font, anchor="w")
            name_lbl.grid(row=0, column=2, sticky="we")
            # тег (активен / исключён)
            tag_lbl = tk.Label(card, text=("  ·  " + tag) if tag else "", bg=row_bg,
                               fg=tag_fg, font=F_MICRO, anchor="w")
            tag_lbl.grid(row=0, column=3, sticky="w")
            # значение громкости
            vol = self.get_mic_volume(mic)
            stored = self.mic_vol.get(mic.id)
            if stored is not None:
                val = int(stored)
            else:
                val = 100 if vol is None else int(round(vol * 100))
            val_lbl = tk.Label(card, text=str(val) + "%", bg=row_bg, fg=DIM,
                               font=F_CAP, anchor="e", width=5)
            val_lbl.grid(row=0, column=4, sticky="e", padx=(10, 4))
            # ползунок громкости (0–250%)
            scale = tk.Scale(card, from_=0, to=250, orient="horizontal",
                             length=116, width=12, showvalue=False,
                             bg=row_bg, fg=DIM, troughcolor=BORDER,
                             highlightthickness=0, sliderrelief="flat",
                             activebackground=BTN,
                             command=lambda v, m=mic: self._on_volume_change(m, v))
            scale.set(val)
            if vol is None and stored is None:
                scale.config(state="disabled")
            scale.grid(row=0, column=5, sticky="e", padx=(0, 4))

            # взаимодействия: ЛКМ — выбрать, колесо — громкость (чекбокс и ползунок — свои действия)
            for wdg in (card, name_lbl, tag_lbl, val_lbl):
                wdg.bind("<Button-1>", lambda e, m=mic: self.activate_mic(m))
                wdg.bind("<Double-Button-1>", lambda e, m=mic: self.activate_mic(m))
                wdg.bind("<Button-3>", lambda e, m=mic: self.toggle_exclude(m))
                wdg.bind("<MouseWheel>", lambda e, m=mic, s=scale: self._wheel_volume(e, m, s))
            self.mic_rows.append({"mic": mic, "row": card, "card": card, "label": name_lbl,
                                  "scale": scale, "val": val_lbl, "cb": cb})

    def _wheel_volume(self, event, mic, scale):
        """Колесо мыши над карточкой — подкрутить громкость этого микрофона."""
        try:
            cur = int(scale.get())
        except Exception:
            cur = self.mic_vol.get(mic.id, 100)
        step = 5 if event.delta > 0 else -5
        nv = max(0, min(250, cur + step))
        try:
            scale.set(nv)
        except Exception:
            pass
        self._on_volume_change(mic, nv)

    def _update_level(self):
        """Обновить VU-метр уровня активного микрофона (вызывается из _poll_hotkey)."""
        try:
            target = 0.0
            if self.router is not None and self.current is not None:
                target = max(0.0, min(1.0, float(self.router.level)))
            if target > self._lvl:
                self._lvl = 0.6 * target + 0.4 * self._lvl
            else:
                self._lvl = 0.25 * target + 0.75 * self._lvl
            frac = max(0.0, min(1.0, self._lvl))
            w = max(2, int(2 + 108 * frac))
            self.vu_canvas.coords(self.vu_rect, 1, 2, w, 14)
            if frac > 0.97:
                col = DANGER
            elif frac > 0.8:
                col = WARNING
            else:
                col = ACTIVE
            self.vu_canvas.itemconfig(self.vu_rect, fill=col)
        except Exception:
            pass

    def _flash_active(self):
        """Короткая подсветка активной карточки после смены микрофона."""
        card = None
        for r in self.mic_rows:
            if r["mic"].id == self.current.id:
                card = r.get("card")
                break
        if card is None:
            return
        try:
            card.config(bg=BTN)
        except Exception:
            return

        def _restore(c=card):
            try:
                c.config(bg=ACCENT_SOFT)
            except Exception:
                pass

        self.root.after(380, _restore)

    def reset_volumes(self):
        """Сбросить громкость всех микрофонов к 100%."""
        for mic in self.mics:
            self.mic_vol[mic.id] = 100
            self.set_mic_volume(mic, 1.0)
        if self.current is not None and self.router is not None:
            try:
                self.router.set_gain(1.0)
            except Exception:
                pass
        save_config(self.hotkey, self.exclude, self.mic_vol)
        self._build_mic_rows()
        self.show_notification("🎚 Громкость сброшена: все микрофоны 100%")


class Hotkey:
    """Горячая клавиша: "f9", "f12", "<ctrl>+m", "<alt>+f1" и т.д."""

    MODS = (pkb.Key.ctrl, pkb.Key.shift, pkb.Key.alt, pkb.Key.cmd)

    # Псевдонимы для клавиш, где введённое имя != имени атрибута pynput
    ALIASES = {
        "scrolllock": "scroll_lock",
        "capslock": "caps_lock",
        "numlock": "num_lock",
        "prtsc": "print_screen",
        "printscreen": "print_screen",
        "pgup": "page_up",
        "pgdn": "page_down",
    }

    @staticmethod
    def _norm_mod(key):
        if key in (pkb.Key.ctrl_l, pkb.Key.ctrl_r):
            return pkb.Key.ctrl
        if key in (pkb.Key.shift_l, pkb.Key.shift_r):
            return pkb.Key.shift
        if key in (pkb.Key.alt_l, pkb.Key.alt_r):
            return pkb.Key.alt
        if key == pkb.Key.cmd:
            return pkb.Key.cmd
        return None

    @staticmethod
    def _resolve(p):
        p = p.replace(" ", "_")
        if p in Hotkey.ALIASES:
            p = Hotkey.ALIASES[p]
        if p in ("ctrl", "control"):
            return pkb.Key.ctrl
        if p == "shift":
            return pkb.Key.shift
        if p == "alt":
            return pkb.Key.alt
        if p in ("cmd", "command"):
            return pkb.Key.cmd
        if hasattr(pkb.Key, p):
            return getattr(pkb.Key, p)
        if len(p) == 1:
            return p
        raise ValueError(f"Не поддерживается в горячей клавише: {p}")

    def __init__(self, spec, callback):
        parts = [p.strip().lower() for p in spec.replace("<", " ").replace(">", " ").split("+") if p.strip()]
        mods, key = set(), None
        for p in parts:
            r = self._resolve(p)
            if r in self.MODS:
                mods.add(r)
            else:
                key = r
        if key is None:
            raise ValueError(f"Некорректная горячая клавиша: {spec}")
        self.mods = mods
        self.key = key
        self.pressed = set()
        self.callback = callback

    def on_press(self, key):
        m = self._norm_mod(key)
        if m is not None:
            self.pressed.add(m)
            return
        if key == self.key and self.pressed == self.mods:
            self.callback()

    def on_release(self, key):
        m = self._norm_mod(key)
        if m is not None:
            self.pressed.discard(m)

    def start(self):
        self.listener = pkb.Listener(on_press=self.on_press, on_release=self.on_release)
        self.listener.start()

    def stop(self):
        try:
            self.listener.stop()
        except Exception:
            pass


_mutex = None


def main():
    global _mutex
    # Защита от запуска второго экземпляра (иначе горячая клавиша сработает дважды)
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\MicSwitcher_SingleInstance")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        from tkinter import messagebox
        messagebox.showinfo(
            "Переключатель микрофонов",
            "Программа уже запущена — ищи её окно в трее или на рабочем столе.",
        )
        return

    app = MicSwitcher()
    app.listener = Hotkey(app.hotkey, app.on_hotkey)
    app.listener.start()
    print(f"Горячая клавиша: {app.display_hotkey()}")
    app.root.mainloop()


if __name__ == "__main__":
    main()
