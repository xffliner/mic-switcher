# MicSwitcher — переключатель микрофонов

[Русский](#переключатель-микрофонов) · [English](#micswitcher-mic-switcher)

![Скриншот](screenshot.png)

Портативное приложение — папка `MicSwitcher` с `MicSwitcher.exe` внутри, —
которое мгновенно переключает микрофон «по умолчанию»
по горячей клавише. Работает и с виртуальным микрофоном (Virtual Audio
Cable) — удобно, когда в Discord/Zoom уже настроен виртуальный вход.

## Возможности

- ⌨️ **Переключение по горячей клавише** — дефолтный микрофон меняется одним нажатием
- 🎧 **Виртуальный микрофон для Discord** — звук автоматически роутится в VAC, вход в Discord не перенастраивается
- 🔊 **Громкость каждого микрофона** (0–250%, колесо мыши) + сброс в один клик
- ✖ **Исключение микрофонов** из переключения (правый клик)
- 🚀 **Автозапуск** при входе в Windows (в настройках)
- 🌐 **Два языка**: русский и английский (автоопределение по языку Windows)
- 🔔 **Уведомления** о каждом переключении
- 🧯 **Один экземпляр**: повторный запуск не создаёт второй процесс и двойные горячие клавиши
- 📄 **Отладочный лог**: `%TEMP%\micswitcher_debug.log`

## Установка

1. Скачайте архив с папкой **`MicSwitcher`** со страницы [Releases](https://github.com/xffliner/mic-switcher/releases) (актуальная версия — **v1.0.2**) и распакуйте её
2. Положите папку, например, на рабочий стол и запустите `MicSwitcher.exe` внутри неё. **Python не нужен**. Все файлы папки — единый комплект, их нельзя разрывать (приложение не распакуется в `%TEMP%` и не требует прав администратора)

Программа не устанавливается в систему: весь конфиг лежит в файле
`mic_switcher.json` рядом с exe.

## Виртуальный микрофон (для Discord)

Чтобы звук с переключаемого микрофона шёл в Discord через виртуальный
вход, нужен драйвер **Virtual Audio Cable**:

1. Скачайте **`vac471lite.zip`** с той же страницы [Releases](https://github.com/xffliner/mic-switcher/releases)
   (или полную версию VAC с [vb-audio.com](https://vb-audio.com/Cable/))
2. Распакуйте и запустите `setup64.exe`, подтвердите установку драйвера
3. В окне программы появится строка **«✅ Виртуальный микрофон: активен»**
4. В Discord → Настройки → Голос и видео → Устройство ввода:
   **Line 1 (Virtual Audio Cable)**

Схема: `физический микрофон → MicSwitcher (роутер) → VAC → Discord`

Без VAC программа работает как есть — просто переключает системный
микрофон «по умолчанию».

## Как пользоваться

| Действие | Что делает |
|---|---|
| Горячая клавиша (по умолчанию **F9**, у вас может быть **Scroll Lock**) | Переключить дефолтный микрофон |
| ЛКМ по микрофону в списке | Выбрать его сразу |
| Колесо мыши | Громкость выбранного микрофона (0–250%) |
| Тумблер на карточке | Вкл/выкл микрофона |
| **Правый клик** по микрофону | Исключить из переключения (пометка ✖) и обратно |
| Кнопка **«Сменить микрофон»** | То же, что горячая клавиша |
| Кнопка **«Настройки»** | Горячая клавиша, автозапуск, язык |
| Кнопка **«Завершить сеанс программы»** | Выйти |

## Горячая клавиша

Сменить: **Настройки → Горячая клавиша → «Сменить…» → нажать клавишу**
(Esc — отмена). Форматы: `f10`, `f12`, `ctrl+m`, `alt+f1`,
`shift+f5`, `scroll lock`, `caps lock`, `num lock`, `pg up`, `home`,
`insert`, `delete`, `print screen` и т.п.

## Файл настроек

`mic_switcher.json` рядом с exe:

```json
{
  "hotkey": "scroll_lock",
  "exclude": ["<GUID исключённых миков>"],
  "volumes": {"<GUID>": 100},
  "lang": "ru",
  "topmost": true
}
```

Удалите файл, чтобы сбросить настройки к значениям по умолчанию.

## Отладка

Все события (запуск, захват лока, каждое переключение, ошибки) пишутся
в `%TEMP%\micswitcher_debug.log` — удобно при разборе «почему не
переключилось».

## Сборка из исходников

Нужен Python 3.10+ (Windows):

```bash
pip install -r requirements.txt
python build_exe.py        # PyInstaller (onedir), результат: dist/MicSwitcher/
```

Структура:

- `mic_switcher.py` — аудио-логика: устройства, дефолт, роутинг VAC,
  горячая клавиша, конфиг
- `mic_switcher_modern.py` — UI (CustomTkinter) + точка входа
- `build_exe.py` — сборка портативной папки `MicSwitcher\` (onedir: работает
  без распаковки в `%TEMP%`; иконка вшивается в код)

## Лицензия

[MIT](LICENSE)

---

# MicSwitcher — Mic Switcher

A portable app — the `MicSwitcher` folder with `MicSwitcher.exe` inside —
that instantly switches the system default microphone
with a hotkey. Also routes audio into a Virtual Audio Cable (VAC), so
your Discord/Zoom virtual-mic input keeps working.

## Features

- ⌨️ **Hotkey switching** — one press changes the default mic
- 🎧 **Virtual mic for Discord** — audio is routed into VAC automatically
- 🔊 **Per-mic volume** (0–250%, mouse wheel) + one-click reset
- ✖ **Exclude mics** from rotation (right-click)
- 🚀 **Autostart** with Windows (in Settings)
- 🌐 **Two languages**: English and Russian (auto-detected from the OS)
- 🔔 **Toasts** on every switch
- 🧯 **Single instance**: relaunching never creates a second process
- 📄 **Debug log**: `%TEMP%\micswitcher_debug.log`

## Installation

1. Download and extract the **`MicSwitcher`** folder from [Releases](https://github.com/xffliner/mic-switcher/releases) (current: **v1.0.2**)
2. Put the folder anywhere (e.g. your desktop) and run `MicSwitcher.exe` inside it. **No Python required**. The folder is one unit — keep all its files together (the app never unpacks itself into `%TEMP%` and needs no admin rights)

All settings are stored in `mic_switcher.json` next to the exe.

## Virtual mic (for Discord)

For the Discord routing you need the **Virtual Audio Cable** driver:

1. Download **`vac471lite.zip`** from the same [Releases](https://github.com/xffliner/mic-switcher/releases) page
   (or full VAC from [vb-audio.com](https://vb-audio.com/Cable/))
2. Unzip and run `setup64.exe`, confirm the driver install
3. The app will show **«✅ Виртуальный микрофон: активен» / VAC: active**
4. In Discord → Settings → Voice & Video → Input Device:
   **Line 1 (Virtual Audio Cable)**

Pipeline: `physical mic → MicSwitcher (router) → VAC → Discord`

Without VAC the app simply switches the system default mic.

## Usage

| Action | Effect |
|---|---|
| Hotkey (default **F9**) | Switch default mic |
| LMB on a mic in the list | Select it immediately |
| Mouse wheel | Volume of the selected mic (0–250%) |
| Toggle on the card | Enable/disable the mic |
| **Right-click** on a mic | Exclude from rotation (✖) / restore |
| **«Сменить микрофон»** button | Same as the hotkey |
| **«Настройки»** button | Hotkey, autostart, language |

## Building from source

Python 3.10+ (Windows):

```bash
pip install -r requirements.txt
python build_exe.py        # PyInstaller → dist/MicSwitcher.exe
```

## License

[MIT](LICENSE)
