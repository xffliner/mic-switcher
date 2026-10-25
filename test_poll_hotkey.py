# -*- coding: utf-8 -*-
"""Проверка _poll_hotkey без запуска UI: флаг из очереди обязан дойти до toggle()."""
import os
import queue
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mic_switcher_modern as m  # noqa: E402


class StubRoot:
    def after(self, ms, fn):
        return None


class Stub:
    def __init__(self):
        self._hotkey_q = queue.Queue()
        self._tray_q = queue.Queue()
        self._poll_n = 0
        self.listener = None
        self.root = StubRoot()
        self.toggled = 0

    def t(self, key, **kw):
        return key

    def toggle(self):
        self.toggled += 1

    def _update_level(self):
        pass

    def show_notification(self, *a, **k):
        pass


s = Stub()

# 1) пустая очередь — toggle не должен вызываться
m.App._poll_hotkey(s)
assert s.toggled == 0, "toggle() вызван на пустой очереди!"
assert s._poll_n == 1

# 2) флаг в очереди — toggle обязан сработать ровно один раз
s._hotkey_q.put(1)
m.App._poll_hotkey(s)
assert s.toggled == 1, "toggle() НЕ вызван (%d)" % s.toggled

# 3) автоповтор: три флага за тик -> один свитч
s._hotkey_q.put(1)
s._hotkey_q.put(1)
s._hotkey_q.put(1)
m.App._poll_hotkey(s)
assert s.toggled == 2, "автоповтор дал %d свитчей" % (s.toggled - 1)

# 4) ошибка внутри toggle не ломает цикл (следующий тик проходит)
count_before = s._poll_n
inner = s.toggle


def boom():
    raise RuntimeError("test")


s.toggle = boom
s._hotkey_q.put(1)
m.App._poll_hotkey(s)
s.toggle = inner
assert s._poll_n == count_before + 1
m.App._poll_hotkey(s)  # цикл жив
assert s._poll_n == count_before + 2

print("POLL TEST OK: toggled=%d poll_n=%d" % (s.toggled, s._poll_n))
