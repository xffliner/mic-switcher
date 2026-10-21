# -*- coding: utf-8 -*-
"""
Заряд беспроводных устройств (Bluetooth-наушники, Logitech G и т.п.).

Источники (все — только чтение, без сторонних зависимостей):

  1) PnP-свойство {104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2 — уровень заряда
     Bluetooth-устройства. То же самое, что показывает
     «Параметры → Bluetooth» (читается через WMI Win32_PnPEntity).
     Свойство 1 этого же набора — статус (0 разряд, 1 зарядка, 2 полностью).
  2) Локальная база G HUB: %LOCALAPPDATA%\\LGHUB\\settings.db
     (таблица data → JSON, ключи battery/<устройство>/percentage).
     Работает для G435 / G733 / PRO X и т.д., если G HUB установлен
     (данные живут в БД после опроса ~каждые 2 мин).
  3) WMI Win32_Battery — классический запасной путь.

Публичный API:
    BatteryInfo          — данные о заряде одного устройства
    collect_all()        — список BatteryInfo по всем источникам
    match_battery(name)  — подобрать заряд по имени аудиоустройства
    BatteryMonitor       — фоновый поток, обновляет кэш каждые N секунд
"""
import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass

BATTERY_SET = "{104EA319-6EE2-4701-BD47-8DDBF425BBE5}"

# Ключи устройств G HUB → читаемые имена (включая G435)
GHUB_NAMES = {
    "g435": "G435",
    "g733": "G733",
    "g633": "G633",
    "g535": "G535",
    "g68s": "G68",
    "g635": "G635",
    "proxwirelessheadset": "PRO X Wireless",
    "proxturbowirelessheadset": "PRO X Turbo Wireless",
    "prowirelessmouse": "PRO Wireless Mouse",
    "prowirelessgppmouse": "PRO X Superlight",
    "g502lightspeed": "G502 LIGHTSPEED",
    "g705hse": "G705",
    "g715": "G715",
    "g915": "G915",
    "g815": "G815",
    "g305": "G305",
    "g304": "G304",
}

# Ключевые слова, по которым аудиоустройство считаем «беспроводным»
WIRELESS_HINTS = (
    "bluetooth", "a2dp", "wireless", "2.4g", "lightspeed", "light speed",
    "g435", "g733", "g633", "g535", "prox wireless", "pro x",
)


@dataclass
class BatteryInfo:
    device_name: str      # имя устройства (как его знает источник)
    percent: int          # 0..100
    charging: bool = False
    source: str = ""      # "bluetooth" | "ghub" | "wmi"
    ts: float = 0.0       # время чтения


def _ps_output(cmd, timeout=60):
    """Запустить PowerShell, вернуть stdout (str) или None."""
    kwargs = dict(capture_output=True, text=True, timeout=timeout)
    if os.name == "nt":
        # Не создавать видимое окно консоли (CREATE_NO_WINDOW)
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            **kwargs)
        return out.stdout
    except Exception:
        return None


# ─────────────────────────── 1. Bluetooth (PnP) ───────────────────────────
def scan_bt_batteries():
    """Уровни заряда Bluetooth-устройств через PnP-свойство (WMI)."""
    cmd = (
        "Get-CimInstance Win32_PnPEntity -Filter \"Status='OK'\" | ForEach-Object { "
        "$d = $_; "
        "$lvl = $null; $st = $null; "
        "try { $v = $d.Get_DevicePropertySet([Guid]'" + BATTERY_SET + "', 2); "
        "if ($v) { $lvl = [int]$v } } catch {}; "
        "try { $v = $d.Get_DevicePropertySet([Guid]'" + BATTERY_SET + "', 1); "
        "if ($v) { $st = [int]$v } } catch {}; "
        "if ($null -ne $lvl) { "
        "  ($d.Name + [char]9 + $d.InstanceId + [char]9 + $lvl + [char]9 + $st) "
        "} }"
    )
    out = _ps_output(cmd, timeout=90)
    res = []
    if not out:
        return res
    now = time.time()
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        try:
            pct = int(str(parts[2]).strip())
        except ValueError:
            continue
        if not (0 <= pct <= 100):
            continue
        try:
            status = int(str(parts[3]).strip()) if len(parts) > 3 and str(parts[3]).strip() else -1
        except ValueError:
            status = -1
        res.append(BatteryInfo(
            device_name=parts[0].strip(),
            percent=pct,
            charging=(status == 1),
            source="bluetooth",
            ts=now,
        ))
    return res


# ─────────────────────────── 2. G HUB (SQLite) ────────────────────────────
def _ghub_db_path():
    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(local, "LGHUB", "settings.db")


def scan_ghub_batteries():
    """Заряд Logitech G-устройств из локальной базы G HUB (read-only)."""
    import sqlite3
    db = _ghub_db_path()
    if not os.path.exists(db):
        return []
    res = []
    now = time.time()
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=2)
        try:
            rows = con.execute("SELECT file FROM data").fetchall()
        finally:
            con.close()
    except Exception:
        return res
    for row in rows:
        blob = row[0] if row and row[0] is not None else None
        if not blob:
            continue
        try:
            data = json.loads(blob.decode("utf-8", "replace"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for key, val in data.items():
            if not (key.startswith("battery/") and key.endswith("/percentage")):
                continue
            if not isinstance(val, dict):
                continue
            pct = val.get("percentage")
            if not isinstance(pct, (int, float)) or not (0 <= pct <= 100):
                continue
            dev_key = key.split("/")[1] if len(key.split("/")) > 1 else ""
            name = GHUB_NAMES.get(dev_key, dev_key or key)
            res.append(BatteryInfo(
                device_name=name,
                percent=int(round(pct)),
                charging=bool(val.get("isCharging", False)),
                source="ghub",
                ts=now,
            ))
    return res


# ─────────────────────────── 3. WMI Win32_Battery ─────────────────────────
def scan_wmi_batteries():
    """Запасной путь: WMI Win32_Battery."""
    cmd = ("Get-CimInstance Win32_Battery | ForEach-Object { "
           "$_.Name + [char]9 + $_.BatteryStatus + [char]9 + $_.EstimatedChargeRemaining }")
    out = _ps_output(cmd, timeout=60)
    res = []
    if not out:
        return res
    now = time.time()
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        try:
            pct = int(str(parts[2]).strip())
        except ValueError:
            continue
        if not (0 <= pct <= 100):
            continue
        try:
            status = int(str(parts[1]).strip())
        except ValueError:
            status = -1
        res.append(BatteryInfo(
            device_name=parts[0].strip(),
            percent=pct,
            charging=(status == 2),  # Win32_Battery: 2 = Charging
            source="wmi",
            ts=now,
        ))
    return res


def collect_all():
    """Все источники сразу (без исключений)."""
    out = []
    for fn in (scan_bt_batteries, scan_ghub_batteries, scan_wmi_batteries):
        try:
            out.extend(fn())
        except Exception:
            pass
    return out


# ─────────────────────────── сопоставление ────────────────────────────────
def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def match_battery(mic_name, batteries=None):
    """Подобрать BatteryInfo по имени аудиоустройства (например, 'G435').

    Правила: точное вхождение имени в любую сторону сильнее, чем
    пересечение слов; среди одинаковых — свежее.
    """
    if batteries is None:
        batteries = collect_all()
    mn = _norm(mic_name)
    if not mn or not batteries:
        return None
    mtokens = set(mn.split())
    best, best_score = None, 0
    for b in batteries:
        bn = _norm(b.device_name)
        if not bn:
            continue
        score = 0
        if mn in bn or bn in mn:
            score = max(len(mn), len(bn)) + 100
        score += 2 * len(mtokens & set(bn.split()))
        if score > best_score:
            best, best_score = b, score
    return best if best_score >= 100 else None


def is_wireless_name(name):
    """Похоже ли имя аудиоустройства на беспроводное."""
    n = (name or "").lower()
    return any(h in n for h in WIRELESS_HINTS)


# ─────────────────────────── фоновый мониторинг ───────────────────────────
class BatteryMonitor(threading.Thread):
    """Фоновый поток: раз в `interval` секунд перечитывает все источники."""

    def __init__(self, interval=30):
        super().__init__(daemon=True, name="BatteryMonitor")
        self.interval = max(10, int(interval))
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._cache = []
        self.last_scan = 0.0

    def run(self):
        while not self._stop.is_set():
            try:
                data = collect_all()
            except Exception:
                data = []
            with self._lock:
                self._cache = data
            self.last_scan = time.time()
            self._stop.wait(self.interval)

    def snapshot(self):
        with self._lock:
            return list(self._cache)

    def stop(self):
        self._stop.set()


# ─────────────────────────── CLI-тест ─────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Сканирование источников заряда...")
    items = collect_all()
    if not items:
        print("  (ничего не найдено — нет BT-устройств и/или G HUB)")
    for b in items:
        print(f"  {b.device_name!r:40} {b.percent:3}%  "
              f"{'⚡зарядка' if b.charging else 'разряд'}  [{b.source}]")
    for test_name in ("G435", "Logitech G435 (USB)", "DOQAUS CARE 1", "Realtek Mic"):
        m = match_battery(test_name, items)
        print(f"  match({test_name!r}) ->",
              (m.device_name, m.percent, m.source) if m else None)
