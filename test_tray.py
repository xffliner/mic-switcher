# -*- coding: utf-8 -*-
"""Мини-тест: реально ли pystray создаёт иконку в трее Windows.
Без патча на этой машине падает: PermissionError [WinError 5] в
ChangeWindowMessageFilterEx. С патчем (тот же код, что в приложении)
иконка должна появиться: SETUP, visible = True."""
import threading, time, sys, traceback

def patch_pystray():
    import pystray._util.win32 as _pw
    _orig = getattr(_pw, "ChangeWindowMessageFilterEx", None)
    if _orig is None:
        return
    def _safe(*a, **k):
        try:
            return _orig(*a, **k)
        except Exception as e:
            print("PATCHED: ChangeWindowMessageFilterEx ignored: %r" % e, flush=True)
            return 0
    _pw.ChangeWindowMessageFilterEx = _safe

def main():
    import pystray
    patch_pystray()
    from PIL import Image, ImageDraw
    S = 64
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, S - 2, S - 2), fill=(76, 141, 255, 255))

    def on_setup(icon):
        icon.visible = True  # при своей setup pystray НЕ показывает иконку сам
        print("SETUP, visible =", icon.visible, flush=True)

    icon = pystray.Icon("MicSwitcherTest", img, "test tooltip",
                        pystray.Menu(pystray.MenuItem("Show", lambda i, x: None, default=True)))
    t = threading.Thread(target=lambda: icon.run(setup=on_setup), daemon=True)
    t.start()
    time.sleep(3)
    print("after 3s: visible =", icon.visible, flush=True)
    icon.stop()
    time.sleep(0.5)
    print("done", flush=True)

try:
    main()
except Exception:
    traceback.print_exc()
    sys.exit(1)
