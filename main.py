# main.py
import sys
import json
import tempfile
import shutil
import platform
import subprocess
from pathlib import Path

from PyQt6.QtCore import QProcess
from PyQt6.QtWidgets import (
    QApplication, QWidget, QFileDialog, QLineEdit, QPushButton, QLabel,
    QCheckBox, QComboBox, QTextEdit, QGridLayout, QGroupBox, QHBoxLayout,
    QVBoxLayout, QMessageBox, QListWidget, QInputDialog
)
from PyQt6.QtGui import QIcon

APP_TITLE = "ForgeEXE — PyInstaller GUI Builder"

# ---------- Utils ----------

def is_windows() -> bool:
    return platform.system().lower().startswith("win")

def sep_for_adddata() -> str:
    # PyInstaller: Windows -> ';'  | POSIX -> ':'
    return ';' if is_windows() else ':'

def quote(s: str) -> str:
    if not s:
        return s
    p = str(s)
    if any(c in p for c in ' ()[]{}&^%$#@!+=,;'):
        return f'"{p}"'
    return p

def base_dir() -> Path:
    """
    Папка ресурсов приложения:
    - dev: рядом с этим файлом
    - frozen: sys._MEIPASS (onefile) или рядом с .exe
    """
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

def app_icon_path() -> Path | None:
    p = base_dir() / "icon.ico"
    return p if p.exists() else None

def set_windows_appusermodel_id(app_id: str):
    """Иконка/группировка в таскбаре Windows."""
    if not is_windows():
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

def make_version_file(tmpdir: Path, product_name: str, file_desc: str, company: str, version: str) -> Path:
    def to_4tuple(ver: str):
        parts = [int(x) if x.isdigit() else 0 for x in ver.replace(',', '.').split('.')]
        parts = (parts + [0, 0, 0, 0])[:4]
        return parts
    vmaj, vmin, vpatch, vbuild = to_4tuple(version or "1.0.0.0")
    vf = tmpdir / "version_info.txt"
    content = f"""
# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({vmaj},{vmin},{vpatch},{vbuild}),
    prodvers=({vmaj},{vmin},{vpatch},{vbuild}),
    mask=0x3f,
    flags=0x0,
    OS=0x4,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', '{company or ""}'),
        StringStruct('FileDescription', '{file_desc or product_name or ""}'),
        StringStruct('FileVersion', '{version or "1.0.0.0"}'),
        StringStruct('InternalName', '{product_name or ""}'),
        StringStruct('LegalCopyright', ''),
        StringStruct('OriginalFilename', '{(product_name or "app")}.exe'),
        StringStruct('ProductName', '{product_name or ""}'),
        StringStruct('ProductVersion', '{version or "1.0.0.0"}')])
      ]), 
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""".strip()
    vf.write_text(content, encoding="utf-8")
    return vf

def find_python_interpreter() -> list[str]:
    """
    Находим реальный Python для запуска PyInstaller:
    - Windows: 'py -3' -> 'python' -> 'python3'
    - POSIX: 'python3' -> 'python'
    Возвращаем список команды, например ['py', '-3'] или ['python3'].
    """
    import shutil as _sh
    if is_windows():
        if _sh.which("py"):
            return ["py", "-3"]
        if _sh.which("python"):
            return ["python"]
        if _sh.which("python3"):
            return ["python3"]
    else:
        if _sh.which("python3"):
            return ["python3"]
        if _sh.which("python"):
            return ["python"]
    return []

def ensure_pyinstaller_available(py_cmd: list[str]) -> bool:
    """
    Проверяем наличие PyInstaller в выбранном Python.
    При отсутствии — предлагаем поставить и пытаемся установить.
    """
    try:
        res = subprocess.run(
            py_cmd + ["-c", "import PyInstaller, sys; print(PyInstaller.__version__); sys.exit(0)"],
            capture_output=True, text=True
        )
        if res.returncode == 0:
            return True
    except Exception:
        pass

    ret = QMessageBox.question(
        None, "PyInstaller не найден",
        "В выбранном Python отсутствует PyInstaller. Установить сейчас?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes
    )
    if ret != QMessageBox.StandardButton.Yes:
        return False

    proc = subprocess.run(py_cmd + ["-m", "pip", "install", "--upgrade", "pip", "pyinstaller"])
    return proc.returncode == 0


# ---------- UI ----------

class BuilderUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(980, 720)

        # Проект
        self.project_dir_edit = QLineEdit()
        self.project_browse_btn = QPushButton("Выбрать папку проекта…")
        self.entry_edit = QLineEdit()
        self.entry_browse_btn = QPushButton("Входной файл (main.py)…")
        self.dist_dir_edit = QLineEdit()
        self.dist_browse_btn = QPushButton("Папка вывода (dist)…")

        self.project_browse_btn.clicked.connect(self.select_project_dir)
        self.entry_browse_btn.clicked.connect(self.select_entry_file)
        self.dist_browse_btn.clicked.connect(self.select_dist_dir)

        # Основные настройки ЦЕЛЕВОГО exe
        self.name_edit = QLineEdit()

        self.icon_edit = QLineEdit()  # иконка для целевого exe
        self.icon_browse_btn = QPushButton("Иконка целевого EXE…")
        self.icon_browse_btn.clicked.connect(self.select_icon_for_build)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["onefile (один exe)", "onedir (папка)"])

        self.gui_checkbox = QCheckBox("GUI (без консоли)  --windowed")
        self.confirm_checkbox = QCheckBox("Без подтверждения  --noconfirm")
        self.clean_checkbox = QCheckBox("Очистить кеш сборки  --clean")

        # Версия/метаданные (Windows)
        self.product_edit = QLineEdit()
        self.company_edit = QLineEdit()
        self.version_edit = QLineEdit()
        self.desc_edit = QLineEdit()

        # Дополнительно
        self.hidden_edit = QLineEdit()
        self.adddata_list = QListWidget()
        self.adddata_add_btn = QPushButton("Добавить файл/папку…")
        self.adddata_del_btn = QPushButton("Удалить выбранное")
        self.adddata_add_btn.clicked.connect(self.add_adddata)
        self.adddata_del_btn.clicked.connect(self.remove_adddata)

        self.addmods_edit = QLineEdit()
        self.addhooks_edit = QLineEdit()
        self.upx_checkbox = QCheckBox("Использовать UPX (если установлен)")
        self.spec_checkbox = QCheckBox("Генерировать .spec рядом с проектом")
        self.extra_args_edit = QLineEdit()

        # Управление
        self.save_profile_btn = QPushButton("Сохранить профиль…")
        self.load_profile_btn = QPushButton("Загрузить профиль…")
        self.build_btn = QPushButton("Собрать EXE")
        self.stop_btn = QPushButton("Остановить")
        self.stop_btn.setEnabled(False)

        self.save_profile_btn.clicked.connect(self.save_profile)
        self.load_profile_btn.clicked.connect(self.load_profile)
        self.build_btn.clicked.connect(self.start_build)
        self.stop_btn.clicked.connect(self.stop_build)

        # Лог
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        # Разметка
        layout = QVBoxLayout(self)
        layout.addWidget(self._group_project())
        layout.addWidget(self._group_basic())
        layout.addWidget(self._group_version())
        layout.addWidget(self._group_extras())
        layout.addLayout(self._group_actions())
        layout.addWidget(self._group_log())

        # Процесс сборки
        self.proc: QProcess | None = None

        # Дефолты
        self.confirm_checkbox.setChecked(True)
        self.gui_checkbox.setChecked(True)
        self.mode_combo.setCurrentIndex(0)
        self.spec_checkbox.setChecked(False)

    # ---- UI groups ----
    def _group_project(self):
        g = QGroupBox("Проект")
        grid = QGridLayout(g)
        grid.addWidget(QLabel("Папка проекта:"), 0, 0)
        grid.addWidget(self.project_dir_edit, 0, 1)
        grid.addWidget(self.project_browse_btn, 0, 2)

        grid.addWidget(QLabel("Входной файл (.py):"), 1, 0)
        grid.addWidget(self.entry_edit, 1, 1)
        grid.addWidget(self.entry_browse_btn, 1, 2)

        grid.addWidget(QLabel("Папка вывода (dist):"), 2, 0)
        grid.addWidget(self.dist_dir_edit, 2, 1)
        grid.addWidget(self.dist_browse_btn, 2, 2)
        return g

    def _group_basic(self):
        g = QGroupBox("Основные настройки сборки (целевой EXE)")
        grid = QGridLayout(g)
        grid.addWidget(QLabel("Имя приложения (-n):"), 0, 0)
        grid.addWidget(self.name_edit, 0, 1)

        grid.addWidget(QLabel("Иконка (--icon):"), 1, 0)
        grid.addWidget(self.icon_edit, 1, 1)
        grid.addWidget(self.icon_browse_btn, 1, 2)

        grid.addWidget(QLabel("Режим:"), 2, 0)
        grid.addWidget(self.mode_combo, 2, 1)

        grid.addWidget(self.gui_checkbox, 3, 0, 1, 2)
        grid.addWidget(self.confirm_checkbox, 4, 0, 1, 2)
        grid.addWidget(self.clean_checkbox, 5, 0, 1, 2)
        return g

    def _group_version(self):
        g = QGroupBox("Версия и метаданные (Windows ресурсы)")
        grid = QGridLayout(g)
        grid.addWidget(QLabel("Название продукта:"), 0, 0)
        grid.addWidget(self.product_edit, 0, 1)
        grid.addWidget(QLabel("Компания:"), 1, 0)
        grid.addWidget(self.company_edit, 1, 1)
        grid.addWidget(QLabel("Версия (a.b.c.d):"), 2, 0)
        grid.addWidget(self.version_edit, 2, 1)
        grid.addWidget(QLabel("Описание файла:"), 3, 0)
        grid.addWidget(self.desc_edit, 3, 1)
        return g

    def _group_extras(self):
        g = QGroupBox("Дополнительно")
        grid = QGridLayout(g)
        grid.addWidget(QLabel("Hidden imports (через запятую):"), 0, 0)
        grid.addWidget(self.hidden_edit, 0, 1)

        grid.addWidget(QLabel("Доп. модули (--collect-all, через запятую):"), 1, 0)
        grid.addWidget(self.addmods_edit, 1, 1)

        grid.addWidget(QLabel("Доп. хуки (--additional-hooks-dir, через запятую):"), 2, 0)
        grid.addWidget(self.addhooks_edit, 2, 1)

        grid.addWidget(QLabel("Добавить файлы/папки (--add-data):"), 3, 0)
        grid.addWidget(self.adddata_list, 3, 1, 3, 1)
        v = QVBoxLayout()
        v.addWidget(self.adddata_add_btn)
        v.addWidget(self.adddata_del_btn)
        v.addStretch(1)
        grid.addLayout(v, 3, 2, 3, 1)

        grid.addWidget(self.upx_checkbox, 6, 0, 1, 2)
        grid.addWidget(self.spec_checkbox, 7, 0, 1, 2)

        grid.addWidget(QLabel("Доп. аргументы PyInstaller:"), 8, 0)
        grid.addWidget(self.extra_args_edit, 8, 1)
        return g

    def _group_actions(self):
        h = QHBoxLayout()
        h.addWidget(self.save_profile_btn)
        h.addWidget(self.load_profile_btn)
        h.addStretch(1)
        h.addWidget(self.stop_btn)
        h.addWidget(self.build_btn)
        return h

    def _group_log(self):
        g = QGroupBox("Лог сборки")
        v = QVBoxLayout(g)
        v.addWidget(self.log)
        return g

    # ---- Actions ----
    def select_project_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Выберите папку проекта")
        if d:
            self.project_dir_edit.setText(d)
            self.dist_dir_edit.setText(str(Path(d) / "dist"))

    def select_entry_file(self):
        start = self.project_dir_edit.text() or ""
        fn, _ = QFileDialog.getOpenFileName(self, "Выберите входной .py", start, "Python (*.py)")
        if fn:
            self.entry_edit.setText(fn)
            if not self.name_edit.text():
                self.name_edit.setText(Path(fn).stem)

    def select_icon_for_build(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Иконка для целевого EXE", "", "Иконки (*.ico *.icns *.png);;Все файлы (*.*)")
        if fn:
            self.icon_edit.setText(str(Path(fn).resolve()))

    def select_dist_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Выберите папку вывода (dist)")
        if d:
            self.dist_dir_edit.setText(d)

    def add_adddata(self):
        choice, ok = QInputDialog.getItem(self, "Добавить как…", "Тип:", ["Файл", "Папка"], 0, False)
        if not ok:
            return
        if choice == "Файл":
            fn, _ = QFileDialog.getOpenFileName(self, "Выберите файл", "", "Все файлы (*.*)")
            if not fn:
                return
            dest, ok2 = QInputDialog.getText(self, "Путь назначения", "Относительный путь внутри сборки:")
            if not ok2:
                return
            self.adddata_list.addItem(f"{fn}{sep_for_adddata()}{dest or '.'}")
        else:
            dn = QFileDialog.getExistingDirectory(self, "Выберите папку")
            if not dn:
                return
            dest, ok2 = QInputDialog.getText(self, "Путь назначения", "Относительный путь внутри сборки:")
            if not ok2:
                return
            self.adddata_list.addItem(f"{dn}{sep_for_adddata()}{dest or '.'}")

    def remove_adddata(self):
        for it in self.adddata_list.selectedItems():
            self.adddata_list.takeItem(self.adddata_list.row(it))

    def save_profile(self):
        prof = self.collect_profile()
        fn, _ = QFileDialog.getSaveFileName(self, "Сохранить профиль", "build_profile.json", "JSON (*.json)")
        if not fn:
            return
        Path(fn).write_text(json.dumps(prof, ensure_ascii=False, indent=2), encoding="utf-8")
        QMessageBox.information(self, "Готово", "Профиль сохранён.")

    def load_profile(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Загрузить профиль", "", "JSON (*.json)")
        if not fn:
            return
        prof = json.loads(Path(fn).read_text(encoding="utf-8"))
        self.apply_profile(prof)
        QMessageBox.information(self, "Готово", "Профиль загружен.")

    def collect_profile(self):
        return {
            "project_dir": self.project_dir_edit.text(),
            "entry": self.entry_edit.text(),
            "dist_dir": self.dist_dir_edit.text(),
            "name": self.name_edit.text(),
            "icon": self.icon_edit.text(),
            "mode": self.mode_combo.currentText(),
            "gui": self.gui_checkbox.isChecked(),
            "noconfirm": self.confirm_checkbox.isChecked(),
            "clean": self.clean_checkbox.isChecked(),
            "product": self.product_edit.text(),
            "company": self.company_edit.text(),
            "version": self.version_edit.text(),
            "description": self.desc_edit.text(),
            "hidden_imports": self.hidden_edit.text(),
            "collect_all": self.addmods_edit.text(),
            "hooks_dirs": self.addhooks_edit.text(),
            "add_data": [self.adddata_list.item(i).text() for i in range(self.adddata_list.count())],
            "upx": self.upx_checkbox.isChecked(),
            "gen_spec": self.spec_checkbox.isChecked(),
            "extra_args": self.extra_args_edit.text(),
        }

    def apply_profile(self, p: dict):
        self.project_dir_edit.setText(p.get("project_dir", ""))
        self.entry_edit.setText(p.get("entry", ""))
        self.dist_dir_edit.setText(p.get("dist_dir", ""))
        self.name_edit.setText(p.get("name", ""))
        self.icon_edit.setText(p.get("icon", ""))
        mode = p.get("mode", "onefile (один exe)")
        idx = self.mode_combo.findText(mode)
        self.mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.gui_checkbox.setChecked(p.get("gui", True))
        self.confirm_checkbox.setChecked(p.get("noconfirm", True))
        self.clean_checkbox.setChecked(p.get("clean", False))
        self.product_edit.setText(p.get("product", ""))
        self.company_edit.setText(p.get("company", ""))
        self.version_edit.setText(p.get("version", "1.0.0.0"))
        self.desc_edit.setText(p.get("description", ""))
        self.adddata_list.clear()
        for item in p.get("add_data", []):
            self.adddata_list.addItem(item)
        self.upx_checkbox.setChecked(p.get("upx", False))
        self.spec_checkbox.setChecked(p.get("gen_spec", False))
        self.extra_args_edit.setText(p.get("extra_args", ""))

    # ---- Build ----
    def start_build(self):
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.warning(self, "Идёт сборка", "Сборка уже запущена.")
            return

        entry = self.entry_edit.text().strip()
        if not entry or not Path(entry).exists():
            QMessageBox.critical(self, "Ошибка", "Укажите корректный входной .py файл.")
            return

        # Защита от попытки собрать сам билдёр
        try:
            current_script = Path(sys.argv[0]).resolve()
            if Path(entry).resolve() == current_script:
                QMessageBox.critical(self, "Нельзя собрать саму программу",
                                     "Выбран входной файл текущего билдёра. Выберите другой проект.")
                return
        except Exception:
            pass

        project_dir = self.project_dir_edit.text().strip() or str(Path(entry).parent)
        dist_dir = self.dist_dir_edit.text().strip()

        # Ищем реальный Python
        py_cmd = find_python_interpreter()
        if not py_cmd:
            QMessageBox.critical(self, "Python не найден",
                                 "Не удалось найти установленный Python (py/python/python3 в PATH). "
                                 "Установите Python 3 и попробуйте снова.")
            return

        # Проверяем/ставим PyInstaller
        if not ensure_pyinstaller_available(py_cmd):
            QMessageBox.critical(self, "PyInstaller недоступен",
                                 "PyInstaller не установлен (или установка отменена/ошибочна).")
            return

        # Формируем команду PyInstaller
        cmd = py_cmd + ["-m", "PyInstaller"]
        if self.confirm_checkbox.isChecked():
            cmd.append("--noconfirm")
        if self.clean_checkbox.isChecked():
            cmd.append("--clean")
        if "onefile" in self.mode_combo.currentText():
            cmd.append("--onefile")
        if self.gui_checkbox.isChecked():
            cmd.append("--windowed")

        appname = self.name_edit.text().strip()
        if appname:
            cmd += ["-n", appname]

        icon = self.icon_edit.text().strip()
        if icon:
            cmd += ["--icon", icon]

        if dist_dir:
            cmd += ["--distpath", dist_dir]
            build_dir = str(Path(dist_dir).parent / "build")
            cmd += ["--workpath", build_dir]

        # add-data
        for i in range(self.adddata_list.count()):
            item = self.adddata_list.item(i).text()
            if item:
                cmd += ["--add-data", item]

        # hidden imports
        hidden = [x.strip() for x in self.hidden_edit.text().split(",") if x.strip()]
        for h in hidden:
            cmd += ["--hidden-import", h]

        # collect-all modules
        collect_all = [x.strip() for x in self.addmods_edit.text().split(",") if x.strip()]
        for m in collect_all:
            cmd += ["--collect-all", m]

        # hooks dirs
        hooks_dirs = [x.strip() for x in self.addhooks_edit.text().split(",") if x.strip()]
        for d in hooks_dirs:
            cmd += ["--additional-hooks-dir", d]

        # UPX (если установлен)
        if self.upx_checkbox.isChecked():
            cmd.append("--upx-dir=upx")

        # Version file (Windows)
        tmpdir = Path(tempfile.mkdtemp(prefix="forgeexe_tmp_"))
        if is_windows():
            product = self.product_edit.text().strip() or appname or "App"
            desc = self.desc_edit.text().strip() or appname or "App"
            company = self.company_edit.text().strip()
            version = self.version_edit.text().strip() or "1.0.0.0"
            version_file = make_version_file(tmpdir, product, desc, company, version)
            cmd += ["--version-file", str(version_file)]

        # Extra args
        extra = self.extra_args_edit.text().strip()
        if extra:
            cmd += extra.split()

        # Entry в самом конце
        cmd.append(entry)

        # Лог и запуск
        self.log.clear()
        self.append_log(f"Рабочая папка: {project_dir}")
        self.append_log("Команда:\n" + " ".join(quote(c) for c in cmd))
        self.build_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        self.proc = QProcess(self)
        self.proc.setProgram(cmd[0])
        self.proc.setArguments(cmd[1:])
        self.proc.setWorkingDirectory(project_dir)
        self.proc.readyReadStandardOutput.connect(lambda: self.read_stream(self.proc.readAllStandardOutput()))
        self.proc.readyReadStandardError.connect(lambda: self.read_stream(self.proc.readAllStandardError()))
        self.proc.finished.connect(lambda code, status: self.on_finished(code, status, tmpdir))

        try:
            self.proc.start()
        except Exception as e:
            self.append_log(f"\nОшибка запуска: {e}")
            self.build_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass

    def stop_build(self):
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            self.proc.kill()
            self.append_log("\nСборка остановлена пользователем.")
        self.build_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def on_finished(self, code, status, tmpdir: Path):
        self.append_log(f"\nГотово. Код выхода: {code}")
        self.append_log("✅ Сборка прошла успешно." if code == 0 else "❌ Ошибка сборки. Проверьте лог.")
        self.build_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    def read_stream(self, data):
        try:
            text = bytes(data).decode(errors="ignore")
        except Exception:
            text = str(data)
        self.append_log(text)

    def append_log(self, text: str):
        self.log.moveCursor(self.log.textCursor().MoveOperation.End)
        self.log.insertPlainText(text if text.endswith("\n") else text + "\n")
        self.log.moveCursor(self.log.textCursor().MoveOperation.End)


# ---------- Entry ----------

def main():
    # Иконка САМОГО приложения (шапка и таскбар)
    if is_windows():
        set_windows_appusermodel_id("ForgeEXE.PyInstaller.GUI")

    app = QApplication(sys.argv)

    ic = app_icon_path()
    if ic:
        icon_obj = QIcon(str(ic.resolve()))
        app.setWindowIcon(icon_obj)

    w = BuilderUI()
    if ic:
        w.setWindowIcon(QIcon(str(ic.resolve())))
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
