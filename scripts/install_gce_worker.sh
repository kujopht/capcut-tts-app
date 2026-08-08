#!/usr/bin/env bash
#
# Cài TTS worker PRODUCTION lên VM Linux (Google Compute Engine). Idempotent.
#
#   sudo ./scripts/install_gce_worker.sh --install-only
#   sudo ./scripts/install_gce_worker.sh --enable-and-start
#
# KHÔNG BAO GIỜ:
#   * tạo, sửa hay in secret — tệp env do người vận hành tự tạo;
#   * tự khởi động worker khi chỉ truyền `--install-only`;
#   * ghi vào thư mục model;
#   * chạm tới worker staging.
#
# VÌ SAO TÁCH `--install-only` KHỎI `--enable-and-start`: cài đặt là thao tác an
# toàn, còn khởi động worker production nghĩa là nó bắt đầu **nhận job thật** và
# ghi vào Appwrite/R2 production. Hai việc đó không nên nằm sau cùng một lệnh.

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/fanfic-audio}"
MODELS_DIR="${MODELS_DIR:-/opt/fanfic-models/nghitts/piper-tts}"
ENV_FILE="${ENV_FILE:-/etc/fanfic-audio/worker-prod.env}"
SERVICE_USER="${SERVICE_USER:-fanfic}"
UNIT_NAME="fanfic-worker-prod.service"
VENV_PY="$APP_DIR/.venv/bin/python"

CHE_DO=""
for tham_so in "$@"; do
  case "$tham_so" in
    --install-only)     CHE_DO="install" ;;
    --enable-and-start) CHE_DO="start" ;;
    -h|--help)
      sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Tham số không hiểu: $tham_so"; exit 2 ;;
  esac
done

if [[ -z "$CHE_DO" ]]; then
  echo "Phải chọn MỘT trong hai:"
  echo "  --install-only       cài/cập nhật unit, KHÔNG khởi động"
  echo "  --enable-and-start   cài rồi bật và khởi động (worker sẽ nhận job THẬT)"
  exit 2
fi

loi() { echo "  [HỎNG] $*"; THAT_BAI=1; }
tot() { echo "  [ OK ] $*"; }
THAT_BAI=0

echo "=== 0. Quyền và môi trường ==="
[[ $EUID -eq 0 ]] || { echo "Phải chạy bằng sudo/root."; exit 2; }
tot "chạy bằng root"
echo "  APP_DIR    = $APP_DIR"
echo "  MODELS_DIR = $MODELS_DIR"
echo "  ENV_FILE   = $ENV_FILE"
echo "  USER       = $SERVICE_USER"

echo
echo "=== 1. Phụ thuộc hệ thống ==="
if command -v ffmpeg >/dev/null 2>&1; then
  tot "ffmpeg: $(ffmpeg -version 2>/dev/null | head -1 | cut -c1-60)"
else
  # Chương ra nhiều hơn một đoạn thì `_concat_mp3` ghép bằng ffmpeg, và
  # `_find_ffmpeg()` CHỈ tra PATH — không có biến môi trường nào trỏ đường dẫn.
  loi "thiếu ffmpeg — chương nhiều đoạn sẽ hỏng MERGE_FFMPEG_MISSING"
fi

if [[ -x "$VENV_PY" ]]; then
  tot "venv python: $("$VENV_PY" --version 2>&1)"
else
  loi "không thấy $VENV_PY"
fi

if [[ -x "$VENV_PY" ]] && "$VENV_PY" -c "import piper" >/dev/null 2>&1; then
  tot "piper-tts: $("$VENV_PY" -c 'import piper,sys; print(getattr(piper,"__version__","?"))' 2>/dev/null)"
else
  loi "venv chưa có gói piper-tts"
fi

echo
echo "=== 2. Mã nguồn ==="
if [[ -f "$APP_DIR/server/worker.py" ]]; then
  tot "mã nguồn ở $APP_DIR"
else
  loi "không thấy $APP_DIR/server/worker.py"
fi

echo
echo "=== 3. Thư mục model + tính nhất quán config/symlink ==="
if [[ -d "$MODELS_DIR" ]]; then
  SO_ONNX=$(find "$MODELS_DIR" -maxdepth 1 -name '*.onnx' ! -name '*.onnx.json' | wc -l)
  tot "thư mục model có $SO_ONNX tệp .onnx"
  if [[ -x "$VENV_PY" && -f "$APP_DIR/scripts/validate_nghitts_models.py" ]]; then
    echo "  -- chạy validate_nghitts_models.py (chỉ đọc) --"
    if "$VENV_PY" "$APP_DIR/scripts/validate_nghitts_models.py" \
         --models-dir "$MODELS_DIR" --no-load | sed 's/^/     /'; then
      tot "mọi cặp .onnx/.onnx.json hợp lệ (symlink không gãy)"
    else
      loi "có model hỏng — xem danh sách ở trên"
    fi
  fi
else
  loi "không thấy thư mục model $MODELS_DIR"
fi

echo
echo "=== 4. Tệp môi trường ==="
# TUYỆT ĐỐI không tạo và không sửa tệp này. Nó chứa credential Appwrite/R2
# production; script cài đặt không có việc gì phải biết nội dung của nó.
if [[ -f "$ENV_FILE" ]]; then
  QUYEN=$(stat -c '%a' "$ENV_FILE")
  tot "có $ENV_FILE (quyền $QUYEN)"
  [[ "$QUYEN" == "600" || "$QUYEN" == "640" ]] || \
    echo "  [CẢNH BÁO] quyền nên là 600 (hoặc 640 nếu nhóm cần đọc)"
  if grep -qE '^\s*FAS_ENV\s*=\s*production\s*$' "$ENV_FILE"; then
    tot "FAS_ENV=production"
  else
    loi "$ENV_FILE không đặt FAS_ENV=production — unit sẽ thoát mã 2"
  fi
else
  loi "chưa có $ENV_FILE — người vận hành phải tự tạo, script này không tạo hộ"
fi

if [[ "$THAT_BAI" -ne 0 ]]; then
  echo
  echo "DỪNG: còn mục HỎNG ở trên. Không cài unit."
  exit 1
fi

echo
echo "=== 5. Người dùng dịch vụ ==="
if id -u "$SERVICE_USER" >/dev/null 2>&1; then
  tot "người dùng $SERVICE_USER đã có"
else
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
  tot "đã tạo người dùng hệ thống $SERVICE_USER (không login được)"
fi
# Đọc mã nguồn thì cần; ghi thì không. Model để nguyên chủ sở hữu — worker chỉ đọc.
chown -R "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR" 2>/dev/null || true

echo
echo "=== 6. Cài/cập nhật unit ==="
NGUON_UNIT="$APP_DIR/deploy/$UNIT_NAME"
DICH_UNIT="/etc/systemd/system/$UNIT_NAME"
[[ -f "$NGUON_UNIT" ]] || { echo "  không thấy $NGUON_UNIT"; exit 1; }
if [[ -f "$DICH_UNIT" ]] && cmp -s "$NGUON_UNIT" "$DICH_UNIT"; then
  tot "unit đã đúng, không cần ghi lại"
else
  install -m 0644 "$NGUON_UNIT" "$DICH_UNIT"
  tot "đã ghi $DICH_UNIT"
fi
systemctl daemon-reload
tot "daemon-reload"

echo
if [[ "$CHE_DO" == "install" ]]; then
  echo "=== 7. XONG — CHƯA khởi động (--install-only) ==="
  echo
  echo "  Worker CHƯA chạy và CHƯA nhận job nào."
  echo "  Khi nào muốn chạy thật:"
  echo "      sudo $0 --enable-and-start"
  echo
  echo "  Kiểm nhịp sau khi chạy:"
  echo "      sudo -u $SERVICE_USER env PYTHONPATH=$APP_DIR \\"
  echo "        FAS_VAR_DIR=/var/lib/fanfic-audio-prod \\"
  echo "        $VENV_PY -m server.worker --check"
  exit 0
fi

echo "=== 7. Bật và khởi động ==="
echo "  Worker production sẽ bắt đầu NHẬN JOB THẬT."
systemctl enable "$UNIT_NAME"
systemctl restart "$UNIT_NAME"
sleep 3
systemctl --no-pager --lines=15 status "$UNIT_NAME" || true
echo
echo "  Xem log:  journalctl -u $UNIT_NAME -f"
