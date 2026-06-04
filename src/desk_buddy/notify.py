"""提醒声音播放。所有异常都吞掉，绝不让 UI 崩。

play_sound(sound_file) 的优先级：
1. 传入的 sound_file 指向存在的音频（mp3/wav/…）→ 播放它；
2. 否则用内置默认音 assets/guagua.mp3（随包发布，谁装都有）；
3. 再不行回退 Windows 默认「叮」声。
不再弹系统横幅通知。
"""

from pathlib import Path

# 内置默认提示音，随包发布（打包见 desk_buddy.spec 的 datas）。
_DEFAULT_SOUND = Path(__file__).parent / "assets" / "guagua.mp3"

# QMediaPlayer 与其音频输出需在播放期间保持引用，否则会被 GC、声音被截断。
_player = None
_audio_output = None


def _beep() -> None:
    import winsound
    winsound.MessageBeep()


def _play_file(path: str) -> None:
    global _player, _audio_output
    from PySide6.QtCore import QUrl
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    if _player is None:
        _player = QMediaPlayer()
        _audio_output = QAudioOutput()
        _player.setAudioOutput(_audio_output)
    _player.setSource(QUrl.fromLocalFile(path))
    _player.play()


def play_sound(sound_file: str = "") -> None:
    try:
        if sound_file and Path(sound_file).is_file():
            _play_file(sound_file)
        elif _DEFAULT_SOUND.is_file():
            _play_file(str(_DEFAULT_SOUND))
        else:
            _beep()
    except Exception:
        pass
