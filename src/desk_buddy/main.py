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


def _run_setup_dialog(config: Config) -> Config:
    """Prompt for base_url / model / api_key on first run. Returns updated config."""
    from PySide6.QtWidgets import (
        QDialog, QFormLayout, QLineEdit, QPushButton,
    )

    dialog = QDialog()
    dialog.setWindowTitle("desk-buddy 首次设置")
    form = QFormLayout(dialog)
    base = QLineEdit(config.base_url or "https://api.openai.com/v1")
    model = QLineEdit(config.model or "gpt-4o-mini")
    key = QLineEdit(config.api_key)
    key.setEchoMode(QLineEdit.Password)
    form.addRow("Base URL", base)
    form.addRow("Model", model)
    form.addRow("API Key", key)
    ok = QPushButton("保存")
    ok.clicked.connect(dialog.accept)
    form.addRow(ok)
    dialog.exec()

    config.base_url = base.text().strip()
    config.model = model.text().strip()
    config.api_key = key.text().strip()
    return config


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from .pet_widget import PetWidget

    app = QApplication(sys.argv)

    config_path = default_config_path()
    config = load_config(config_path)
    if needs_setup(config):
        config = _run_setup_dialog(config)
        save_config(config, config_path)

    db_path = str(config_path.parent / "reminders.db")
    store = ReminderStore(db_path)
    brain = Brain(build_provider(config))
    pet = PetWidget()
    from . import notify

    controller = App(config, store, brain, pet, notify)
    pet.user_said.connect(controller.handle_user_text)
    pet.set_roaming(config.roam_enabled)

    scheduler = Scheduler(store, controller.handle_reminder_due)
    scheduler.tick(datetime.now())  # startup catch-up for missed reminders

    timer = QTimer()
    timer.timeout.connect(lambda: scheduler.tick(datetime.now()))
    timer.start(TICK_INTERVAL_MS)

    pet.show()
    pet.say("我在啦～ 点我跟我说要提醒啥～")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
