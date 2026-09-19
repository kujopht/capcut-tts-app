"""
Captures screenshots and state inspection for Content Factory v2 Monitor App.
Captures:
- Tab 1: Content Pipeline
- Tab 2: Account Pool (all 14 accounts)
- Tab 3: Published Catalog (Living Novel Production)
- Tab 4: Completed Archive Gallery
- Production Diff Modal Dialog
"""

import os
import sys
import time
import json
from pathlib import Path

# Fix stdout for Windows
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from scripts.content_factory.factory_monitor_app import (
    FactoryMonitorMainWindow,
    get_active_runner_pid,
    free_system_memory,
)
from scripts.content_factory.pipeline_ui_components import DiffResultDialog
from scripts.content_factory.production_diff_engine import ProductionDiffEngine


def run_v2_inspection():
    print("[*] Khởi tạo PySide6 Application...")
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    out_dir = PROJECT_ROOT / "scratch" / "screenshots_factory_monitor"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[*] Khởi tạo FactoryMonitorMainWindow v2...")
    window = FactoryMonitorMainWindow()
    if hasattr(window, "quota_timer"):
        window.quota_timer.stop()

    window.show()
    print("[*] Cửa sổ hiển thị. Đang nạp dữ liệu từ DataPollWorker...")

    # Wait for poll worker to emit initial data
    start = time.time()
    while time.time() - start < 4.0:
        app.processEvents()
        time.sleep(0.05)

    # 1. Chụp Tab 1: Content Pipeline
    print("[*] Chụp Tab 1: Content Pipeline...")
    window._switch_view(0)
    app.processEvents()
    time.sleep(0.5)
    app.processEvents()

    shot_tab1 = out_dir / "content_factory_v2_tab1_pipeline.png"
    pix1 = window.grab()
    pix1.save(str(shot_tab1))
    print(f"    [OK] Đã lưu Tab 1: {shot_tab1}")

    # 2. Chụp Tab 2: Account Pool (All 14 accounts)
    print("[*] Chụp Tab 2: Account Pool (14 Accounts)...")
    window._switch_view(1)
    app.processEvents()
    time.sleep(0.5)
    app.processEvents()

    shot_tab2 = out_dir / "content_factory_v2_tab2_accounts.png"
    pix2 = window.grab()
    pix2.save(str(shot_tab2))
    print(f"    [OK] Đã lưu Tab 2: {shot_tab2}")

    # 3. Chụp Tab 3: Published Catalog
    print("[*] Chụp Tab 3: Published Catalog (Living Novel Production)...")
    window._switch_view(2)
    app.processEvents()
    time.sleep(0.5)
    app.processEvents()

    shot_tab3 = out_dir / "content_factory_v2_tab3_catalog.png"
    pix3 = window.grab()
    pix3.save(str(shot_tab3))
    print(f"    [OK] Đã lưu Tab 3: {shot_tab3}")

    # 4. Chụp Tab 4: Archive Gallery
    print("[*] Chụp Tab 4: Kho Lưu Trữ (Historical Archive)...")
    window._switch_view(3)
    app.processEvents()
    time.sleep(0.5)
    app.processEvents()

    shot_tab4 = out_dir / "content_factory_v2_tab4_archive.png"
    pix4 = window.grab()
    pix4.save(str(shot_tab4))
    print(f"    [OK] Đã lưu Tab 4: {shot_tab4}")

    # 5. Chụp Modal Dialog: Production Diff Dialog on Hatake
    print("[*] Chụp Modal Dialog: Production Diff Dialog...")
    diff_engine = ProductionDiffEngine()
    real_chs = diff_engine._get_registered_chapters("royalroad", "156690")
    candidate_chapters = [
        {"order": r["chapter_order"], "title": f"Chương {r['chapter_order']}", "source_text_hash": r["source_text_hash"]}
        for r in real_chs
    ] + [
        {"order": len(real_chs) + 1, "title": f"Chương {len(real_chs) + 1}: Synthetic New Chapter", "source_text_hash": "synth_hash_13"}
    ]
    diff_rep = diff_engine.diff({
        "platform": "royalroad",
        "work_id": "156690",
        "title": "[Naruto SI] Trọng Sinh Gia Tộc Hatake: Cú Sốc Của Kỹ Sư Vật Liệu",
        "chapters": candidate_chapters,
    })
    dlg = DiffResultDialog(diff_rep, window)
    dlg.show()
    app.processEvents()
    time.sleep(0.5)
    app.processEvents()

    shot_dlg = out_dir / "content_factory_v2_diff_dialog.png"
    pix_dlg = dlg.grab()
    pix_dlg.save(str(shot_dlg))
    print(f"    [OK] Đã lưu Diff Dialog: {shot_dlg}")
    dlg.accept()

    # Save metadata inspection
    ui_state = {
        "title": window.windowTitle(),
        "geometry": f"{window.width()}x{window.height()}",
        "tabs": [
            window.btn_view_pipeline.text(),
            window.btn_view_accounts.text(),
            window.btn_view_catalog.text(),
            window.btn_view_gallery.text(),
        ],
        "runner_status": window.lbl_runner_status.text(),
        "ram_status": window.lbl_ram_status.text(),
        "account_cards_count": len(window.page_accounts.account_cards),
        "account_names": list(window.page_accounts.account_cards.keys()),
        "published_catalog_rows": window.page_catalog.table.rowCount(),
        "pipeline_table_rows": window.page_pipeline.table.rowCount(),
    }

    report_file = out_dir / "content_factory_v2_inspection.json"
    report_file.write_text(json.dumps(ui_state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    [OK] Đã lưu báo cáo UI v2: {report_file}")

    window.close()
    app.processEvents()
    print("[*] Hoàn tất chụp ảnh giao diện v2!")


if __name__ == "__main__":
    run_v2_inspection()
