"""提醒声音播放。所有异常都吞掉，绝不让 UI 崩。

play_sound(sound_file): 若 sound_file 指向存在的音频文件（mp3/wav/…），用
QtMultimedia 播放；否则回退到 Windows 默认「叮」声。不再弹系统横幅通知。
"""

from pathlib import Path

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
        else:
            _beep()
    except Exception:
        pass
