# ForgeEXE — PyInstaller GUI Builder

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](#)
[![PyQt6](https://img.shields.io/badge/PyQt-6-41b883)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Графический конструктор сборок на PyInstaller:

- выбираешь проект и входной файл;
- настраиваешь имя, иконку, режимы (`onefile`/`onedir`, окно/консоль);
- добавляешь ресурсы (`--add-data`), hidden imports, collect-all, хуки;
- жмёшь **Собрать EXE** — и получаешь готовый билд.

## Возможности

- Реальный Python (не самозапуск GUI): нахождение `py -3` / `python3` / `python`.
- Авто-проверка и установка PyInstaller при первом запуске сборки.
- Запрет «самосборки» (защита от выбора текущего GUI как цели).
- Лог сборки в реальном времени и кнопка **Остановить**.
- Иконка самого приложения берётся из `icon.ico` рядом с `main.py` (шапка + таскбар).
- Поддержка: `--onefile/onedir`, `--windowed`, `--noconfirm`, `--clean`, `--hidden-import`,
  `--collect-all`, `--additional-hooks-dir`, `--add-data`, `--upx-dir`, `--version-file`.

## Установка и запуск

```bash
pip install PyQt6
python main.py
```

> 💡 PyInstaller ставить вручную не обязательно — программа предложит установить его при первой сборке.

## Сборка целевого проекта

1. Укажи папку проекта и входной `.py`.
2. (Опционально) задай имя и иконку целевого exe.
3. Добавь ресурсы через **Добавить файл/папку…** (путь назначения — `.` или папка вроде `assets`).
4. Нажми **Собрать EXE**. Готовый файл появится в `dist/`.

## Полезно знать

- Таскбар Windows берёт иконку из **самого exe** → указывай `--icon`.
- Для ресурсов, читаемых из файлов, используй `--add-data`.
- Если менял иконку exe, открепи/закрепи ярлык в таскбаре заново (Windows кеширует).

## CI: сборка GUI под Windows

```yaml
# .github/workflows/windows-build.yml
name: Windows Build (ForgeEXE)

on:
  push:
    tags:
      - "v*"
  workflow_dispatch:

jobs:
  build:
    runs-on: windows-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install pyinstaller PyQt6

      - name: Build EXE
        run: |
          mkdir dist
          pyinstaller --noconfirm --onefile --windowed main.py ^
            -n ForgeEXE ^
            --icon icon.ico ^
            --add-data "icon.ico;."

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: ForgeEXE
          path: dist/ForgeEXE.exe
```

## Лицензия

MIT — см. `LICENSE`.
