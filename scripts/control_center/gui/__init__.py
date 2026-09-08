"""Giao diện ĐỒ HOẠ (PySide6) cho Router Control Center — bản V0.1.1.

VÌ SAO CÓ GÓI NÀY: bản V0.1 chỉ có TUI Textual. Nó chạy được, nhưng thao
tác chuột và clipboard trong terminal không đáng tin — dán một câu lệnh
nhiều dòng vào ô chat là việc thường ngày, và nó không hoạt động chắc chắn.
Đó là lý do bản này tồn tại, và cũng là tiêu chí nghiệm thu của nó.

VÌ SAO LÀ Qt, KHÔNG PHẢI TAURI: kho này ĐÃ có PySide6
(`requirements-gui.txt`) và ĐÃ có một bộ 397 bài kiểm Qt chạy offscreen
(`tests/`, `QT_QPA_PLATFORM=offscreen`). Quan trọng hơn: `QPlainTextEdit`
và `QTextEdit` mang sẵn clipboard THẬT của Windows — chọn bằng chuột,
Ctrl+C/V/A, menu chuột phải — nên chính cái cổng nghiệm thu khó nhất được
nền tảng lo, không phải do ta tự dựng lại. Tauri sẽ thêm một chuỗi công cụ
Rust+Node cho đúng thứ ta đã có.

    bridge.py   nối tới `ControlCenter` đã phát hành — KHÔNG có logic điều
                phối nào ở đây; chỉ hỏi sổ và phát tín hiệu Qt
    widgets.py  widget dùng lại, gồm các ô văn bản CHỌN/COPY được
    views.py    năm khung: Chat / Tasks / Agents / Logs / Usage
    app.py      cửa sổ chính: thanh trên, hai thanh bên, điều hướng
    __main__.py điểm vào (`python -m scripts.control_center.gui`)

BA ĐIỀU KHÔNG ĐƯỢC PHÁ Ở TẦNG NÀY:

1. **Không nhét logic backend vào frontend.** Mọi quyết định điều phối vẫn
   ở `engine.py`/Router V4. Gói này chỉ đọc `snapshot()` và gọi các hàm
   công khai (`chat`, `pause`, `resume`, `stop`, `mo_khoa_gated`).
2. **Không giành Ctrl+C/Ctrl+V/Ctrl+A.** Không một `QShortcut` hay
   `QAction` nào ở đây được đăng ký các tổ hợp đó ở phạm vi ứng dụng — làm
   vậy là lấy mất hành vi clipboard chuẩn của chính ô văn bản đang gõ. Có
   bài kiểm khoá điều này lại.
3. **Bàn phím chỉ là lối tắt, không bao giờ là kiến thức bắt buộc.** Mọi
   thao tác phải làm được bằng chuột.
"""
