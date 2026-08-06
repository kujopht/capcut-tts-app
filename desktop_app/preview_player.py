"""
Trinh phat audio nghe thu - toi gian, CHI phuc vu nut "Nghe thu".

Rang buoc:
- Moi luc CHI phat mot giong. Phat giong moi thi giong cu dung ngay.
- Dung duoc bat cu luc nao.
- Khong playlist, khong waveform, khong chinh sua audio.

Dung QtMultimedia de dung/phat that su. Neu moi truong khong co QtMultimedia
(vi du ban dong goi thieu module), lop nay tu dong lui ve che do "khong phat
duoc" thay vi lam sap ung dung.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QUrl, Signal

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    MULTIMEDIA_AVAILABLE = True
except ImportError:  # pragma: no cover - moi truong thieu QtMultimedia
    QAudioOutput = None
    QMediaPlayer = None
    MULTIMEDIA_AVAILABLE = False


class PreviewPlayer(QObject):
    """Phat mot file audio tai mot thoi diem, co the dung."""

    #: (voice_id) - bat dau phat
    started = Signal(str)
    #: (voice_id) - da dung hoac phat xong
    stopped = Signal(str)
    #: (voice_id, thong_bao) - khong phat duoc
    failed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_id: Optional[str] = None
        self._player = None
        self._audio = None

    def _ensure_player(self):
        """
        Tao QMediaPlayer LAZY - chi khi thuc su can phat.

        Khoi tao san trong __init__ khien moi cua so deu dung mot backend audio;
        tren may khong co thiet bi am thanh (moi truong test offscreen, may ao)
        backend co the quay vong lam treo va ngon CPU. Tao muon tranh han viec do.
        """
        if self._player is not None:
            return self._player
        if not MULTIMEDIA_AVAILABLE:
            return None
        try:
            self._audio = QAudioOutput(self)
            self._player = QMediaPlayer(self)
            self._player.setAudioOutput(self._audio)
            self._player.playbackStateChanged.connect(self._on_state_changed)
            self._player.errorOccurred.connect(self._on_error)
        except Exception:
            self._player = None
            self._audio = None
        return self._player

    # -- truy van -------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Co the phat duoc khong (khong tao backend chi de tra loi cau hoi nay)."""
        return MULTIMEDIA_AVAILABLE

    @property
    def current_voice_id(self) -> Optional[str]:
        return self._current_id

    def is_playing(self, voice_id: Optional[str] = None) -> bool:
        if self._current_id is None:
            return False
        if voice_id is not None and voice_id != self._current_id:
            return False
        return True

    # -- dieu khien -----------------------------------------------------------

    def play(self, voice_id: str, path: str | Path) -> bool:
        """Phat mot file. Tu dong dung ban dang phat truoc do."""
        path = Path(path)
        if not path.is_file():
            self.failed.emit(voice_id, "Không tìm thấy file nghe thử.")
            return False

        # Chi mot giong tai mot thoi diem
        self.stop()

        if self._ensure_player() is None:
            self.failed.emit(
                voice_id,
                "Bản dựng này thiếu QtMultimedia nên không phát được trong ứng dụng.",
            )
            return False

        self._current_id = voice_id
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()
        self.started.emit(voice_id)
        return True

    def stop(self) -> None:
        """Dung phat ngay lap tuc."""
        previous = self._current_id
        self._current_id = None
        if self._player is not None:
            try:
                self._player.stop()
                self._player.setSource(QUrl())
            except Exception:
                pass
        if previous:
            self.stopped.emit(previous)

    # -- tin hieu tu QMediaPlayer --------------------------------------------

    def _on_state_changed(self, state) -> None:  # pragma: no cover - can Qt that
        if self._player is None or QMediaPlayer is None:
            return
        if state == QMediaPlayer.PlaybackState.StoppedState and self._current_id:
            finished = self._current_id
            self._current_id = None
            self.stopped.emit(finished)

    def _on_error(self, error, message: str = "") -> None:  # pragma: no cover
        voice_id = self._current_id or ""
        self._current_id = None
        self.failed.emit(voice_id, message or "Không phát được file nghe thử.")
