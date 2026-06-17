import sys
from datetime import datetime

from . import __version__, cc_signals
from .app import App
from .brain import Brain
from .config import Config, default_config_path, load_config, save_config
from .llm import build_provider
from .qt_runner import QtRunner
from .scheduler import TICK_INTERVAL_MS, Scheduler
from .store import ReminderStore


def needs_setup(config: Config) -> bool:
    return not config.is_configured


def _apply_app_icon(app) -> None:
    """设置窗口/任务栏图标为青蛙。通过 pythonw 启动时，任务栏默认显示 Python 图标——
    在 Windows 上还需设一个独立的 AppUserModelID，任务栏才用我们的图标而非宿主的。
    所有异常吞掉：没图标也不该挡住启动。"""
    from pathlib import Path

    from PySide6.QtGui import QIcon

    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("desk-buddy")
    except Exception:
        pass
    icon_path = Path(__file__).parent / "assets" / "icon.png"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))


def _run_setup_dialog(config: Config) -> bool:
    """Prompt for base_url / model / api_key / 提醒声音. Apply to `config` ONLY
    if the user confirms (clicks 保存). Returns True if the config was updated."""
    from PySide6.QtWidgets import (
        QCheckBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
        QLineEdit, QPushButton, QWidget,
    )

    dialog = QDialog()
    dialog.setWindowTitle(f"desk-buddy 设置 v{__version__}")
    form = QFormLayout(dialog)
    base = QLineEdit(config.base_url)
    base.setPlaceholderText("https://api.openai.com/v1")
    model = QLineEdit(config.model)
    model.setPlaceholderText("gpt-4o-mini")
    key = QLineEdit(config.api_key)
    key.setEchoMode(QLineEdit.EchoMode.Password)
    form.addRow("Base URL", base)
    form.addRow("Model", model)
    form.addRow("API Key", key)

    sound_on = QCheckBox("提醒时播放声音")
    sound_on.setChecked(config.sound_enabled)
    form.addRow(sound_on)

    sound_file = QLineEdit(config.sound_file)
    sound_file.setPlaceholderText("mp3/wav 路径，留空用默认叮声")
    browse = QPushButton("浏览…")

    def _pick_sound() -> None:
        path, _ = QFileDialog.getOpenFileName(
            dialog, "选择提示音", "", "音频 (*.mp3 *.wav);;所有文件 (*)")
        if path:
            sound_file.setText(path)

    browse.clicked.connect(_pick_sound)
    sound_row = QWidget()
    sound_layout = QHBoxLayout(sound_row)
    sound_layout.setContentsMargins(0, 0, 0, 0)
    sound_layout.addWidget(sound_file)
    sound_layout.addWidget(browse)
    form.addRow("提示音", sound_row)

    ok = QPushButton("保存")
    ok.clicked.connect(dialog.accept)
    form.addRow(ok)

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False  # 关闭/取消 -> 不改动现有配置

    config.base_url = base.text().strip()
    config.model = model.text().strip()
    config.api_key = key.text().strip()
    config.sound_enabled = sound_on.isChecked()
    config.sound_file = sound_file.text().strip()
    return True


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from .pet_widget import PetWidget

    app = QApplication(sys.argv)
    # The pet is the anchor window; closing the input bar or a dialog must not
    # quit the app. Only the right-click 退出 menu quits explicitly.
    app.setQuitOnLastWindowClosed(False)
    _apply_app_icon(app)

    config_path = default_config_path()
    config = load_config(config_path)
    # Pet-first startup opens the DB before any config save, so ensure the
    # data dir exists (on a fresh machine it would not yet).
    config_path.parent.mkdir(parents=True, exist_ok=True)

    db_path = str(config_path.parent / "reminders.db")
    store = ReminderStore(db_path)
    brain = Brain(build_provider(config))
    pet = PetWidget()
    from . import notify

    controller = App(config, store, brain, pet, notify, runner=QtRunner())

    def open_settings() -> None:
        if not _run_setup_dialog(config):
            return
        save_config(config, config_path)
        if config.is_configured:
            controller.brain = Brain(build_provider(config))
            pet.say("大脑接上啦～现在可以跟我说要提醒啥啦！")

    def on_pet_clicked() -> None:
        if config.is_configured:
            pet.prompt_input()
        else:
            open_settings()

    pet.user_said.connect(controller.handle_user_text)
    pet.clicked.connect(on_pet_clicked)
    pet.settings_requested.connect(open_settings)
    pet.quit_requested.connect(app.quit)
    pet.alert_dismissed.connect(controller.on_alert_dismissed)
    pet.alert_nag.connect(controller.on_alert_nag)
    pet.set_roaming(False)  # roaming temporarily disabled for the frog

    scheduler = Scheduler(store, controller.handle_reminder_due)
    scheduler.tick(datetime.now())  # startup catch-up for missed reminders

    timer = QTimer()
    timer.timeout.connect(lambda: scheduler.tick(datetime.now()))
    timer.start(TICK_INTERVAL_MS)

    # Claude Code「等你确认」轮询：每秒先清掉陈旧孤儿信号，再扫一次。
    # 每轮都 prune，长时间运行也能清掉没触发 clear hook 的残留（不只启动清一次）。
    cc_timer = QTimer()
    cc_timer.timeout.connect(
        lambda: controller.update_cc_pending(cc_signals.poll_pending())
    )
    cc_timer.start(1000)

    # 拉起 Claude 驾驶舱。开机自启 + 右键菜单都用它。
    # 设环境变量 CLAUDE_COCKPIT_PY 指向 cockpit venv 的 python 即可;没设则提示。
    def launch_cockpit(show_hint: bool = False) -> None:
        import os
        cockpit_py = os.environ.get("CLAUDE_COCKPIT_PY")
        if not cockpit_py or not os.path.exists(cockpit_py):
            if show_hint:
                pet.say("还没配驾驶舱:设环境变量 CLAUDE_COCKPIT_PY 指向它的 pythonw 就行～")
            return
        try:
            import subprocess
            # 用 pythonw.exe 无窗运行:否则会留一个控制台黑框,关掉它会连带杀死 cockpit。
            pyw = cockpit_py.replace("python.exe", "pythonw.exe")
            exe = pyw if os.path.exists(pyw) else cockpit_py
            subprocess.Popen([exe, "-m", "claude_cockpit.main"])
            if show_hint:
                pet.say("驾驶舱来啦～")
        except Exception:
            pass

    pet.cockpit_requested.connect(lambda: launch_cockpit(show_hint=True))
    launch_cockpit()                 # 开机自启(没配则静默跳过)

    pet.show()
    if needs_setup(config):
        pet.say("我还没连上大脑，点我设置一下吧～")
    else:
        pet.say("我在啦～ 点我说要提醒啥～")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
