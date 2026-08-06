"""
Quan ly model Piper local (tuong thich bo nghimestudio/nghitts).

Vi tri luu model:
    %LOCALAPPDATA%\\FanficAudioStudio\\models\\piper

TUYET DOI khong luu model hay du lieu runtime trong Program Files.

Moi model can DUNG mot cap file:
    <ten>.onnx        - trong so model
    <ten>.onnx.json   - cau hinh (sample_rate, phoneme map...)

Module nay khong import PySide6 va khong tu dong goi mang, nen test duoc offline.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

APP_DIR_NAME = "FanficAudioStudio"

#: Bien moi truong de test tro thu muc model sang noi khac (khong dung
#: thu muc that cua nguoi dung).
MODELS_DIR_ENV = "FAS_PIPER_MODELS_DIR"

ONNX_SUFFIX = ".onnx"
CONFIG_SUFFIX = ".onnx.json"

#: Kich thuoc toi thieu de coi la file model that (model Piper deu > 1 MB).
MIN_ONNX_BYTES = 1024 * 1024


def user_data_dir() -> Path:
    """%LOCALAPPDATA%\\FanficAudioStudio - khong bao gio la Program Files."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_DIR_NAME
    return Path.home() / f".{APP_DIR_NAME.lower()}"


def piper_models_dir() -> Path:
    """Thu muc chua model Piper. Ton trong bien moi truong de test."""
    override = os.environ.get(MODELS_DIR_ENV)
    if override:
        return Path(override)
    return user_data_dir() / "models" / "piper"


def ensure_models_dir() -> Path:
    target = piper_models_dir()
    target.mkdir(parents=True, exist_ok=True)
    return target


# -----------------------------------------------------------------------------
# Mo ta mot model
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class PiperModel:
    """Mot model Piper da (hoac chua) co tren dia."""

    name: str
    onnx_path: Optional[Path] = None
    config_path: Optional[Path] = None
    error: str = ""

    @property
    def installed(self) -> bool:
        """Chi coi la da cai khi CO DU ca hai file va khong co loi."""
        return bool(
            not self.error
            and self.onnx_path
            and self.config_path
            and self.onnx_path.is_file()
            and self.config_path.is_file()
        )

    @property
    def status_reason(self) -> str:
        if self.error:
            return self.error
        if self.installed:
            return ""
        if self.onnx_path and self.onnx_path.is_file() and not (
            self.config_path and self.config_path.is_file()
        ):
            return f"Thiếu file cấu hình {self.name}{CONFIG_SUFFIX}"
        if self.config_path and self.config_path.is_file() and not (
            self.onnx_path and self.onnx_path.is_file()
        ):
            return f"Thiếu file model {self.name}{ONNX_SUFFIX}"
        return "Chưa tải model"


def pair_stems_match(onnx_path: Path, config_path: Path) -> Tuple[bool, str]:
    """
    Kiem tra hai file co PHAI cua cung mot model khong.

    Quy uoc Piper: `<ten>.onnx` di voi `<ten>.onnx.json`. Neu nguoi dung lo chon
    file cau hinh cua model khac thi phai bao loi, khong duoc lang le ghep bua.

    KHONG doan ten file tu ten hien thi cua giong - chi doi chieu hai file
    nguoi dung da chon voi nhau.
    """
    onnx_path = Path(onnx_path)
    config_path = Path(config_path)

    onnx_stem = onnx_path.name
    if onnx_stem.lower().endswith(ONNX_SUFFIX):
        onnx_stem = onnx_stem[: -len(ONNX_SUFFIX)]

    config_stem = config_path.name
    if config_stem.lower().endswith(CONFIG_SUFFIX):
        config_stem = config_stem[: -len(CONFIG_SUFFIX)]

    if onnx_stem != config_stem:
        return False, (
            f"Hai file không cùng một model: '{onnx_path.name}' đi với "
            f"'{onnx_stem}{CONFIG_SUFFIX}', không phải '{config_path.name}'."
        )
    return True, ""


def validate_model_pair(
    onnx_path: Path, config_path: Path, check_names: bool = True
) -> Tuple[bool, str]:
    """
    Kiem tra mot cap file model co dung dinh dang khong.

    Tra ve (hop_le, ly_do). Khong nem exception de goi tu giao dien duoc.

    `check_names=False` khi kiem tra ban sao TAM (duoi .part): luc do chi
    xet NOI DUNG, vi ten file tam co y khac de khong bao gio de lai cap file
    nua voi neu bi ngat giua chung.
    """
    onnx_path = Path(onnx_path)
    config_path = Path(config_path)

    if not onnx_path.is_file():
        return False, f"Không tìm thấy file model: {onnx_path.name}"
    if not config_path.is_file():
        return False, f"Không tìm thấy file cấu hình: {config_path.name}"

    if check_names:
        if onnx_path.suffix.lower() != ONNX_SUFFIX:
            return False, "File model phải có đuôi .onnx"
        if not config_path.name.lower().endswith(CONFIG_SUFFIX):
            return False, "File cấu hình phải có đuôi .onnx.json"

    try:
        size = onnx_path.stat().st_size
    except OSError as exc:
        return False, f"Không đọc được file model: {exc}"
    if size < MIN_ONNX_BYTES:
        return False, (
            f"File model chỉ {size} byte — quá nhỏ, nhiều khả năng tải lỗi hoặc sai file"
        )

    # ONNX la protobuf, 8 byte dau khong phai text; kiem tra so bo de bat file HTML/loi
    try:
        with open(onnx_path, "rb") as fp:
            head = fp.read(8)
    except OSError as exc:
        return False, f"Không đọc được file model: {exc}"
    if head[:1] in (b"<", b"{") or head[:5] == b"<!DOC":
        return False, "File model không phải ONNX (có vẻ là trang HTML hoặc JSON lỗi)"

    try:
        with open(config_path, "r", encoding="utf-8") as fp:
            config = json.load(fp)
    except UnicodeDecodeError:
        return False, "File cấu hình không phải UTF-8"
    except json.JSONDecodeError as exc:
        return False, f"File cấu hình không phải JSON hợp lệ: {exc}"
    except OSError as exc:
        return False, f"Không đọc được file cấu hình: {exc}"

    if not isinstance(config, dict):
        return False, "File cấu hình phải là một đối tượng JSON"

    # Piper luon co sample_rate (truc tiep hoac trong "audio")
    audio = config.get("audio") if isinstance(config.get("audio"), dict) else {}
    if not (config.get("sample_rate") or audio.get("sample_rate")):
        return False, "File cấu hình thiếu sample_rate — không phải cấu hình Piper"

    return True, ""


# -----------------------------------------------------------------------------
# Quan ly kho model
# -----------------------------------------------------------------------------


class PiperModelManager:
    """
    Tim, kiem tra va cai dat model Piper vao thu muc du lieu nguoi dung.

    KHONG tu dong tai model tu Internet: hien chua xac minh duoc URL on dinh
    nao, ma bia URL/SHA-256 thi nguy hiem hon la khong co. Nguoi dung tu chon
    2 file model; khi nao co nguon chinh thuc kiem chung duoc thi bo sung.
    """

    def __init__(self, models_dir: Optional[Path] = None):
        self._models_dir = Path(models_dir) if models_dir else None

    @property
    def models_dir(self) -> Path:
        return self._models_dir if self._models_dir else piper_models_dir()

    # -- tra cuu --------------------------------------------------------------

    # -- lien ket voice_key -> file model that -------------------------------
    #
    # KHONG duoc suy doan ten file ONNX tu ten hien thi. Giong nhu Ngoc Huyen
    # co ten file do ben phat hanh quyet dinh, nen nguoi dung chon dung cap file
    # va lien ket duoc luu lai o day.

    @property
    def bindings_path(self) -> Path:
        return self.models_dir / "models.json"

    def _load_bindings(self) -> Dict[str, Dict[str, str]]:
        path = self.bindings_path
        if not path.is_file():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save_bindings(self, data: Dict[str, Dict[str, str]]) -> bool:
        path = self.bindings_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.part")
            with open(tmp, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
            return True
        except OSError:
            return False

    def binding_for(self, name: str) -> Optional[Tuple[Path, Path]]:
        """Cap file da lien ket voi `name`, hoac None."""
        entry = self._load_bindings().get(name)
        if not isinstance(entry, dict):
            return None
        onnx = entry.get("onnx")
        config = entry.get("config")
        if not onnx or not config:
            return None
        return Path(onnx), Path(config)

    def bind(self, name: str, onnx_path: Path, config_path: Path) -> Tuple[bool, str]:
        """
        Lien ket mot voice_key voi cap file model NGUOI DUNG da chon.

        Dung khi ten file khong theo quy uoc `<voice_key>.onnx` - tuyet doi
        khong doan ten file tu ten hien thi.
        """
        ok, reason = validate_model_pair(Path(onnx_path), Path(config_path))
        if not ok:
            return False, reason
        data = self._load_bindings()
        data[name] = {"onnx": str(Path(onnx_path)), "config": str(Path(config_path))}
        if not self._save_bindings(data):
            return False, "Không ghi được models.json"
        return True, f"Đã liên kết model cho '{name}'"

    def unbind(self, name: str) -> None:
        data = self._load_bindings()
        if data.pop(name, None) is not None:
            self._save_bindings(data)

    def canonical_paths_for(self, name: str) -> Tuple[Path, Path]:
        """Duong dan theo QUY UOC trong kho, bo qua lien ket."""
        base = self.models_dir
        return base / f"{name}{ONNX_SUFFIX}", base / f"{name}{CONFIG_SUFFIX}"

    def paths_for(self, name: str) -> Tuple[Path, Path]:
        """
        Duong dan cap file model cua `name`.

        Uu tien lien ket nguoi dung da chon; neu chua co thi dung quy uoc
        `<name>.onnx` + `<name>.onnx.json` trong thu muc model.
        """
        bound = self.binding_for(name)
        if bound is not None:
            return bound
        base = self.models_dir
        return base / f"{name}{ONNX_SUFFIX}", base / f"{name}{CONFIG_SUFFIX}"

    def find(self, name: str) -> PiperModel:
        """Trang thai cua mot model theo ten. Khong bao gio nem exception."""
        onnx_path, config_path = self.paths_for(name)
        has_onnx = onnx_path.is_file()
        has_config = config_path.is_file()

        if not has_onnx and not has_config:
            return PiperModel(name=name)
        if not (has_onnx and has_config):
            return PiperModel(
                name=name,
                onnx_path=onnx_path if has_onnx else None,
                config_path=config_path if has_config else None,
            )

        ok, reason = validate_model_pair(onnx_path, config_path)
        if not ok:
            return PiperModel(
                name=name, onnx_path=onnx_path, config_path=config_path, error=reason
            )
        return PiperModel(name=name, onnx_path=onnx_path, config_path=config_path)

    def installed_names(self) -> List[str]:
        """Ten cac model da cai day du (co ca 2 file va hop le)."""
        base = self.models_dir
        if not base.is_dir():
            return []
        names: List[str] = []
        for bound_name in self._load_bindings():
            if self.find(bound_name).installed:
                names.append(bound_name)
        try:
            for path in sorted(base.glob(f"*{ONNX_SUFFIX}")):
                if path.name.endswith(CONFIG_SUFFIX):
                    continue
                name = path.name[: -len(ONNX_SUFFIX)]
                if name not in names and self.find(name).installed:
                    names.append(name)
        except OSError:
            return []
        return names

    def status_map(self, names: List[str]) -> Dict[str, PiperModel]:
        return {name: self.find(name) for name in names}

    # -- cai dat thu cong -----------------------------------------------------

    def install_from_files(
        self, name: str, onnx_source: Path, config_source: Path
    ) -> Tuple[bool, str]:
        """
        Cai model tu 2 file nguoi dung tu chon.

        Ghi vao file tam roi moi doi ten, de khong bao gio de lai cap file
        nua voi khi bi ngat giua chung.
        """
        onnx_source = Path(onnx_source)
        config_source = Path(config_source)

        ok, reason = validate_model_pair(onnx_source, config_source)
        if not ok:
            return False, reason

        try:
            target_dir = ensure_models_dir() if self._models_dir is None else self.models_dir
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return False, f"Không tạo được thư mục model: {exc}"

        onnx_target, config_target = self.canonical_paths_for(name)
        onnx_tmp = onnx_target.with_suffix(onnx_target.suffix + ".part")
        config_tmp = config_target.with_suffix(config_target.suffix + ".part")

        try:
            shutil.copyfile(onnx_source, onnx_tmp)
            shutil.copyfile(config_source, config_tmp)
        except OSError as exc:
            onnx_tmp.unlink(missing_ok=True)
            config_tmp.unlink(missing_ok=True)
            return False, f"Không sao chép được file model: {exc}"

        # Xac minh lai ban da sao chep TRUOC khi doi ten thanh file that.
        # Bo qua kiem tra ten vi ban tam co duoi .part.
        ok, reason = validate_model_pair(onnx_tmp, config_tmp, check_names=False)
        if not ok:
            onnx_tmp.unlink(missing_ok=True)
            config_tmp.unlink(missing_ok=True)
            return False, f"Bản sao chép không hợp lệ: {reason}"

        try:
            os.replace(onnx_tmp, onnx_target)
            os.replace(config_tmp, config_target)
        except OSError as exc:
            onnx_tmp.unlink(missing_ok=True)
            config_tmp.unlink(missing_ok=True)
            return False, f"Không hoàn tất cài model: {exc}"

        # File da nam dung quy uoc nen khong can lien ket rieng nua
        self.unbind(name)
        return True, f"Đã cài model '{name}'"

    def remove(self, name: str) -> Tuple[bool, str]:
        """Xoa mot model khoi kho (chi trong thu muc du lieu nguoi dung)."""
        onnx_path, config_path = self.paths_for(name)
        removed = False
        for path in (onnx_path, config_path):
            try:
                if path.is_file():
                    path.unlink()
                    removed = True
            except OSError as exc:
                return False, f"Không xoá được {path.name}: {exc}"
        self.unbind(name)
        return (True, f"Đã xoá model '{name}'") if removed else (False, "Model chưa được tải")
