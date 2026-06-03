import sys
from datetime import datetime

from .app import App
from .brain import Brain
from .config import Config, default_config_path, load_config, save_config
from .llm import build_provider
from .scheduler import TICK_INTERVAL_MS, Scheduler
from .store import ReminderStore


def needs_setup(config: Config) -> bool:
    return not config.is_configured


def _run_setup_dialog(config: Config) -> bool:
    """Prompt for base_url / model / api_key. Apply to `config` ONLY if the
    user confirms (clicks 保存). Returns True if the config was updated."""
    from PySide6.QtWidgets import (
        QDialog, QFormLayout, QLineEdit, QPushButton,
    )

    dialog = QDialog()
    dialog.setWindowTitle("desk-buddy 设置")
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
    ok = QPushButton("保存")
    ok.clicked.connect(dialog.accept)
    form.addRow(ok)

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False  # 关闭/取消 -> 不改动现有配置

    config.base_url = base.text().strip()
    config.model = model.text().strip()
    config.api_key = key.text().strip()
    return True


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from .pet_widget import PetWidget

    app = QApplication(sys.argv)

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

    controller = App(config, store, brain, pet, notify)

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
    pet.set_roaming(config.roam_enabled)

    scheduler = Scheduler(store, controller.handle_reminder_due)
    scheduler.tick(datetime.now())  # startup catch-up for missed reminders

    timer = QTimer()
    timer.timeout.connect(lambda: scheduler.tick(datetime.now()))
    timer.start(TICK_INTERVAL_MS)

    pet.show()
    if needs_setup(config):
        pet.say("我还没连上大脑，点我设置一下吧～")
    else:
        pet.say("我在啦～ 点我说要提醒啥～")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
