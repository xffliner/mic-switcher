# -*- coding: utf-8 -*-
"""Установщик MicSwitcher.

Собирается PyInstaller'ом в один exe, внутри лежат:
  app/  — файлы приложения (MicSwitcher.exe + _internal)
  vac/  — архив VAC Lite (setup64.exe для виртуального микрофона)

Делает: копирование приложения в папку установки, установку VAC Lite
по желанию, ярлыки на Рабочем столе и в меню «Пуск», запись в
«Программы и компоненты» + uninstall.bat.

Флаги для автотеста/тихой установки:
  --silent --dest "<папка>" [--no-vac] [--no-shortcut] [--no-launch]
"""
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk

APP_NAME = "MicSwitcher"
APP_TITLE = "Переключатель микрофонов"
APP_VERSION = "1.4.0"
PUBLISHER = "xffliner"
APP_EXE = "MicSwitcher.exe"
REG_UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\MicSwitcher"


def base_dir():
    """Папка с ресурсами (в onefile — распакованный _MEIPASS)."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def default_target():
    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(local, "Programs", APP_NAME)


def desktop_dir():
    try:
        return os.path.join(os.path.expanduser("~"), "Desktop")
    except Exception:
        return ""


def start_menu_dir():
    appdata = os.environ.get("APPDATA") or ""
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs")


def log(msg, sink=None):
    print(msg)
    if sink is not None:
        try:
            sink(msg)
        except Exception:
            pass


def kill_running():
    try:
        subprocess.run(["taskkill", "/IM", APP_EXE, "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    except Exception:
        pass


def copy_app(target, sink=None):
    src = os.path.join(base_dir(), "app")
    if not os.path.isdir(src):
        raise RuntimeError("Архив установщика повреждён: нет папки app")
    os.makedirs(target, exist_ok=True)
    # свой конфиг пользователя не затираем
    keep = {"mic_switcher.json", "micswitcher_ui.json", "micswitcher_debug.log",
            "mic_switcher_err.log"}
    total = 0
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        dst_root = target if rel == "." else os.path.join(target, rel)
        os.makedirs(dst_root, exist_ok=True)
        for name in files:
            if rel == "." and name in keep and os.path.exists(os.path.join(dst_root, name)):
                continue
            shutil.copy2(os.path.join(root, name), os.path.join(dst_root, name))
            total += 1
    log("Скопировано файлов: %d" % total, sink)
    return total


def create_shortcut(link_path, target_exe, workdir, icon=None):
    """Создать .lnk через WScript.Shell (без сторонних библиотек)."""
    script = (
        "$ws = New-Object -ComObject WScript.Shell;"
        "$s = $ws.CreateShortcut('%s');"
        "$s.TargetPath = '%s';"
        "$s.WorkingDirectory = '%s';"
        "$s.IconLocation = '%s';"
        "$s.Description = '%s';"
        "$s.Save()"
    ) % (link_path.replace("'", "''"), target_exe, workdir,
         (icon or target_exe) + ",0", APP_TITLE)
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)


def make_shortcuts(target, sink=None):
    exe = os.path.join(target, APP_EXE)
    made = []
    desk = desktop_dir()
    if desk:
        link = os.path.join(desk, APP_NAME + ".lnk")
        create_shortcut(link, exe, target)
        made.append(link)
    sm = start_menu_dir()
    if sm:
        link = os.path.join(sm, APP_NAME + ".lnk")
        create_shortcut(link, exe, target)
        made.append(link)
    log("Ярлыки: %d" % len(made), sink)
    return made


def write_uninstaller(target):
    bat = os.path.join(target, "uninstall.bat")
    content = "\r\n".join([
        "@echo off",
        'taskkill /IM %s /F >nul 2>&1' % APP_EXE,
        "timeout /t 1 >nul",
        'del "%%USERPROFILE%%\\Desktop\\%s.lnk" >nul 2>&1' % APP_NAME,
        'del "%%APPDATA%%\\Microsoft\\Windows\\Start Menu\\Programs\\%s.lnk" >nul 2>&1' % APP_NAME,
        'reg delete "HKCU\\%s" /f >nul 2>&1' % REG_UNINSTALL,
        'start "" cmd /c "timeout /t 2 >nul & cd /d "%%LOCALAPPDATA%%\\Programs" & rmdir /s /q "%s""' % APP_NAME,
        "",
    ])
    with open(bat, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    return bat


def register_uninstall(target):
    try:
        import winreg
        exe = os.path.join(target, APP_EXE)
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_UNINSTALL, 0,
                                winreg.KEY_WRITE) as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_TITLE)
            winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
            winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
            winreg.SetValueEx(k, "DisplayIcon", 0, winreg.REG_SZ, exe)
            winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, target)
            winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ,
                              '"%s"' % os.path.join(target, "uninstall.bat"))
            winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
        return True
    except Exception as e:
        print("registry:", e)
        return False


def install_vac(sink=None):
    """Распаковать и запустить установщик VAC Lite (с правами администратора)."""
    vac_zip = os.path.join(base_dir(), "vac", "vac471lite.zip")
    if not os.path.isfile(vac_zip):
        log("VAC Lite не найден в установщике — пропускаю", sink)
        return False
    tmp = os.path.join(tempfile.gettempdir(), "MicSwitcherVAC")
    if os.path.isdir(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    import zipfile
    with zipfile.ZipFile(vac_zip) as z:
        z.extractall(tmp)
    setup = os.path.join(tmp, "setup64.exe")
    if not os.path.isfile(setup):
        log("В архиве VAC нет setup64.exe", sink)
        return False
    log("Запускаю установщик VAC Lite…", sink)
    try:
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", setup, None, tmp, 1)
        if r <= 32:
            log("Не удалось запустить VAC (код %s)" % r, sink)
            return False
        return True
    except Exception as e:
        log("VAC: %s" % e, sink)
        return False


def run_install(target, with_vac=True, with_shortcuts=True, with_launch=True, sink=None):
    kill_running()
    log("Папка установки: %s" % target, sink)
    copy_app(target, sink)
    if with_shortcuts:
        make_shortcuts(target, sink)
    write_uninstaller(target)
    register_uninstall(target)
    log("Приложение установлено", sink)
    if with_vac:
        install_vac(sink)
    if with_launch:
        exe = os.path.join(target, APP_EXE)
        if os.path.isfile(exe):
            log("Запускаю приложение…", sink)
            try:
                subprocess.Popen([exe], cwd=target, close_fds=True)
            except Exception as e:
                log("Запуск не удался: %s" % e, sink)
    return target


class InstallerUI(tk.Tk):
    def __init__(self, silent=False, target=None, with_vac=True,
                 with_shortcuts=True, with_launch=True):
        super().__init__()
        self.title("Установка %s %s" % (APP_TITLE, APP_VERSION))
        self.geometry("560x420")
        self.resizable(False, False)
        self.configure(bg="#313338")
        self.vac_var = tk.BooleanVar(value=with_vac)
        self.lnk_var = tk.BooleanVar(value=with_shortcuts)
        self.run_var = tk.BooleanVar(value=with_launch)
        self.path_var = tk.StringVar(value=target or default_target())
        self._build()
        self._silent = silent

    def _build(self):
        bg, fg, dim = "#313338", "#F2F3F5", "#B5BAC1"
        pad = {"padx": 18}
        tk.Label(self, text=APP_TITLE, bg=bg, fg=fg,
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(16, 2), **pad)
        tk.Label(self, text="Версия %s · установка приложения и виртуального микрофона" % APP_VERSION,
                 bg=bg, fg=dim, font=("Segoe UI", 9)).pack(anchor="w", **pad)

        box = tk.Frame(self, bg=bg)
        box.pack(fill="x", pady=(14, 0), **pad)
        tk.Label(box, text="Папка установки:", bg=bg, fg=fg,
                 font=("Segoe UI", 10)).pack(anchor="w")
        row = tk.Frame(box, bg=bg)
        row.pack(fill="x", pady=(4, 0))
        self.entry = tk.Entry(row, textvariable=self.path_var, bg="#1E1F22", fg=fg,
                              insertbackground=fg, relief="flat", font=("Segoe UI", 10))
        self.entry.pack(side="left", fill="x", expand=True, ipady=6)
        tk.Button(row, text="Обзор…", command=self._browse, bg="#4E5058", fg="#FFFFFF",
                  relief="flat", font=("Segoe UI", 9), padx=10).pack(side="left", padx=(8, 0))

        opts = tk.Frame(self, bg=bg)
        opts.pack(fill="x", pady=(14, 0), **pad)
        for text, var in (
                ("Установить VAC Lite (виртуальный микрофон для Discord)", self.vac_var),
                ("Создать ярлык на Рабочем столе", self.lnk_var),
                ("Запустить приложение после установки", self.run_var)):
            tk.Checkbutton(opts, text=text, variable=var, bg=bg, fg=fg, selectcolor="#1E1F22",
                           activebackground=bg, activeforeground=fg,
                           font=("Segoe UI", 10)).pack(anchor="w")

        btns = tk.Frame(self, bg=bg)
        btns.pack(fill="x", pady=(16, 0), **pad)
        self.go = tk.Button(btns, text="Установить", command=self._start, bg="#5865F2",
                            fg="#FFFFFF", activebackground="#4752C4", activeforeground="#FFFFFF",
                            relief="flat", font=("Segoe UI", 11, "bold"), padx=24, pady=6)
        self.go.pack(side="left")
        tk.Button(btns, text="Закрыть", command=self.destroy, bg="#4E5058", fg="#FFFFFF",
                  activebackground="#3F4147", activeforeground="#FFFFFF",
                  relief="flat", font=("Segoe UI", 10), padx=18, pady=6).pack(side="left", padx=(10, 0))

        self.log_view = tk.Text(self, height=9, bg="#1E1F22", fg="#B5BAC1",
                                relief="flat", font=("Consolas", 9), wrap="word")
        self.log_view.pack(fill="both", expand=True, pady=(14, 14), **pad)
        self.log_view.configure(state="disabled")

    def _browse(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(initialdir=os.path.dirname(self.path_var.get()) or "C:\\")
        if path:
            self.path_var.set(os.path.join(path, APP_NAME))

    def _sink(self, msg):
        self.log_view.configure(state="normal")
        self.log_view.insert("end", msg + "\n")
        self.log_view.see("end")
        self.log_view.configure(state="disabled")
        self.update_idletasks()

    def _start(self):
        self.go.configure(state="disabled", text="Установка…")
        target = self.path_var.get().strip() or default_target()

        def work():
            try:
                run_install(target, self.vac_var.get(), self.lnk_var.get(),
                            self.run_var.get(), sink=self._sink)
                self._sink("Готово. Можно закрыть установщик.")
            except Exception as e:
                self._sink("Ошибка: %s" % e)
            finally:
                try:
                    self.go.configure(state="normal", text="Установить")
                except Exception:
                    pass

        threading.Thread(target=work, daemon=True).start()


def parse_args(argv):
    opts = {"silent": False, "dest": None, "vac": True, "shortcuts": True, "launch": True}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--silent":
            opts["silent"] = True
        elif a == "--dest" and i + 1 < len(argv):
            i += 1
            opts["dest"] = argv[i]
        elif a == "--no-vac":
            opts["vac"] = False
        elif a == "--no-shortcut":
            opts["shortcuts"] = False
        elif a == "--no-launch":
            opts["launch"] = False
        i += 1
    return opts


def main():
    opts = parse_args(sys.argv[1:])
    if opts["silent"]:
        run_install(opts["dest"] or default_target(), opts["vac"],
                    opts["shortcuts"], opts["launch"], sink=print)
        return
    app = InstallerUI(target=opts["dest"], with_vac=opts["vac"],
                      with_shortcuts=opts["shortcuts"], with_launch=opts["launch"])
    app.mainloop()


if __name__ == "__main__":
    main()
