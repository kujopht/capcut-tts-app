"""
Theme cho Fanfic Audio Studio — Qt stylesheet thuan, khong dung framework ngoai.

Mac dinh la dark theme voi mau nhan xanh tim (#7C5CFF -> #4C7DFF).
"""

from __future__ import annotations

from typing import Dict

THEME_DARK = "dark"
THEME_LIGHT = "light"

DARK: Dict[str, str] = {
    "bg": "#12121A",
    "surface": "#1A1A24",
    "surface_alt": "#20202C",
    "elevated": "#262635",
    "border": "#30304A",
    "border_soft": "#26263A",
    "text": "#E9E9F2",
    "text_dim": "#A6A6C0",
    "text_faint": "#75758F",
    "accent": "#7C5CFF",
    "accent_hover": "#8E74FF",
    "accent_press": "#6A49F0",
    "accent_soft": "#2A2350",
    "accent_2": "#4C7DFF",
    "success": "#35D6A0",
    "warn": "#FFB454",
    "error": "#FF5C7A",
    "selection": "#33306A",
}

LIGHT: Dict[str, str] = {
    "bg": "#F4F4F9",
    "surface": "#FFFFFF",
    "surface_alt": "#F7F7FC",
    "elevated": "#FFFFFF",
    "border": "#D8D8E6",
    "border_soft": "#E6E6F0",
    "text": "#1B1B27",
    "text_dim": "#5A5A72",
    "text_faint": "#8A8AA3",
    "accent": "#6A49F0",
    "accent_hover": "#7C5CFF",
    "accent_press": "#573AD6",
    "accent_soft": "#EBE6FF",
    "accent_2": "#3C6DF0",
    "success": "#12A97B",
    "warn": "#C77700",
    "error": "#D63456",
    "selection": "#E0D9FF",
}

#: Mau cho tung trang thai job/part (dung ca trong bang va nhan trang thai)
STATE_COLORS = {
    "pending": "text_dim",
    "running": "accent_2",
    "success": "success",
    "partial": "warn",
    "failed": "error",
    "stopped": "warn",
    "skipped": "text_faint",
    "idle": "text_dim",
    "paused": "warn",
    "stopping": "warn",
    "blocked": "error",
    "finished": "success",
    "unknown": "text_faint",
}


def palette(theme: str) -> Dict[str, str]:
    return LIGHT if theme == THEME_LIGHT else DARK


def state_color(theme: str, state: str) -> str:
    colors = palette(theme)
    return colors.get(STATE_COLORS.get(state, "text_dim"), colors["text_dim"])


def build_stylesheet(theme: str = THEME_DARK) -> str:
    """Sinh Qt stylesheet cho toan bo ung dung."""
    c = palette(theme)
    return f"""
* {{
    font-family: "Segoe UI", "Segoe UI Variable", Arial, sans-serif;
    font-size: 13px;
    outline: none;
}}

QWidget {{
    background-color: {c['bg']};
    color: {c['text']};
}}

QMainWindow, QDialog {{
    background-color: {c['bg']};
}}

/* ---------- Sidebar ---------- */
#Sidebar {{
    background-color: {c['surface']};
    border-right: 1px solid {c['border_soft']};
}}

#SidebarBrand {{
    background-color: transparent;
}}

#SidebarLogo {{
    background-color: transparent;
    font-size: 22px;
}}

#SidebarBrandName {{
    background-color: transparent;
    font-size: 14px;
    font-weight: 700;
    color: {c['text']};
}}

#SidebarBrandSub {{
    background-color: transparent;
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.4px;
    color: {c['text_dim']};
}}

#SidebarTag {{
    color: {c['text_faint']};
    font-size: 11px;
    padding: 2px 2px 6px 2px;
}}

QPushButton#NavButton {{
    background-color: transparent;
    color: {c['text_dim']};
    border: none;
    border-radius: 9px;
    padding: 11px 14px;
    text-align: left;
    font-size: 13.5px;
    font-weight: 600;
}}

QPushButton#NavButton:hover {{
    background-color: {c['surface_alt']};
    color: {c['text']};
}}

QPushButton#NavButton:checked {{
    background-color: {c['accent_soft']};
    color: {c['text']};
    border-left: 3px solid {c['accent']};
    padding-left: 11px;
}}

/* ---------- Card / khung ---------- */
#Card {{
    background-color: {c['surface']};
    border: 1px solid {c['border_soft']};
    border-radius: 12px;
}}

#DropZone {{
    background-color: {c['surface_alt']};
    border: 2px dashed {c['border']};
    border-radius: 12px;
    color: {c['text_dim']};
    padding: 14px;
}}

#DropZoneActive {{
    background-color: {c['accent_soft']};
    border: 2px dashed {c['accent']};
    border-radius: 12px;
    color: {c['text']};
    padding: 14px;
}}

QLabel#PageTitle {{
    font-size: 19px;
    font-weight: 700;
    color: {c['text']};
}}

QLabel#PageHint, QLabel#Hint {{
    color: {c['text_dim']};
    font-size: 12px;
}}

QLabel#SectionTitle {{
    font-size: 13.5px;
    font-weight: 700;
    color: {c['text']};
    padding-bottom: 2px;
}}

QLabel#SummaryBig {{
    font-size: 15px;
    font-weight: 700;
    color: {c['accent']};
}}

QLabel#WarnLabel {{
    color: {c['warn']};
    font-weight: 600;
}}

QLabel#ErrorLabel {{
    color: {c['error']};
    font-weight: 600;
}}

/* ---------- Nut ---------- */
QPushButton {{
    background-color: {c['elevated']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {c['surface_alt']};
    border-color: {c['accent']};
}}

QPushButton:pressed {{
    background-color: {c['accent_press']};
    color: #FFFFFF;
}}

QPushButton:disabled {{
    background-color: {c['surface_alt']};
    color: {c['text_faint']};
    border-color: {c['border_soft']};
}}

QPushButton#Primary {{
    background-color: {c['accent']};
    color: #FFFFFF;
    border: none;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 700;
    border-radius: 9px;
}}

QPushButton#Primary:hover {{
    background-color: {c['accent_hover']};
}}

QPushButton#Primary:pressed {{
    background-color: {c['accent_press']};
}}

QPushButton#Primary:disabled {{
    background-color: {c['surface_alt']};
    color: {c['text_faint']};
}}

QPushButton#Danger {{
    background-color: transparent;
    color: {c['error']};
    border: 1px solid {c['error']};
}}

QPushButton#Danger:hover {{
    background-color: {c['error']};
    color: #FFFFFF;
}}

QPushButton#Ghost {{
    background-color: transparent;
    border: 1px solid {c['border']};
    color: {c['text_dim']};
    font-weight: 600;
}}

QPushButton#Ghost:hover {{
    color: {c['text']};
    border-color: {c['accent']};
}}

/* ---------- Nhap lieu ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background-color: {c['surface_alt']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 7px 9px;
    selection-background-color: {c['accent']};
    selection-color: #FFFFFF;
}}

QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QComboBox:focus {{
    border-color: {c['accent']};
}}

QLineEdit:disabled, QPlainTextEdit:disabled, QSpinBox:disabled {{
    color: {c['text_faint']};
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}

QComboBox QAbstractItemView {{
    background-color: {c['elevated']};
    color: {c['text']};
    border: 1px solid {c['border']};
    selection-background-color: {c['accent']};
    selection-color: #FFFFFF;
    outline: none;
}}

QSpinBox::up-button, QSpinBox::down-button {{
    width: 16px;
    background-color: {c['elevated']};
    border: none;
}}

/* ---------- Bang ---------- */
QTableWidget, QTableView, QTreeWidget, QTreeView, QListWidget {{
    background-color: {c['surface']};
    alternate-background-color: {c['surface_alt']};
    color: {c['text']};
    border: 1px solid {c['border_soft']};
    border-radius: 10px;
    gridline-color: {c['border_soft']};
    selection-background-color: {c['selection']};
    selection-color: {c['text']};
}}

QTableWidget::item, QTreeWidget::item, QListWidget::item {{
    padding: 5px 6px;
    border: none;
}}

QTableWidget::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {{
    background-color: {c['selection']};
    color: {c['text']};
}}

QHeaderView::section {{
    background-color: {c['elevated']};
    color: {c['text_dim']};
    border: none;
    border-bottom: 1px solid {c['border']};
    border-right: 1px solid {c['border_soft']};
    padding: 7px 6px;
    font-weight: 700;
    font-size: 12px;
}}

QTableCornerButton::section {{
    background-color: {c['elevated']};
    border: none;
}}

/* ---------- Progress ---------- */
QProgressBar {{
    background-color: {c['surface_alt']};
    border: 1px solid {c['border_soft']};
    border-radius: 8px;
    height: 16px;
    text-align: center;
    color: {c['text']};
    font-size: 11px;
    font-weight: 700;
}}

QProgressBar::chunk {{
    background-color: {c['accent']};
    border-radius: 7px;
}}

/* ---------- Scrollbar ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 11px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: {c['border']};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: {c['accent']};
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 11px;
    margin: 2px;
}}

QScrollBar::handle:horizontal {{
    background: {c['border']};
    border-radius: 5px;
    min-width: 30px;
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px;
    width: 0px;
}}

QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ---------- Khac ---------- */
QCheckBox, QRadioButton {{
    color: {c['text']};
    spacing: 7px;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {c['border']};
    border-radius: 4px;
    background-color: {c['surface_alt']};
}}

QCheckBox::indicator:checked {{
    background-color: {c['accent']};
    border-color: {c['accent']};
}}

/* O tick trong bang (chon nhieu giong). Dung mau nen dam nhat de nhin ro
   tren ca dong thuong va dong ke so le. */
QTableView::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {c['border']};
    border-radius: 4px;
    background-color: {c['bg']};
}}

QTableView::indicator:hover {{
    border-color: {c['accent']};
}}

QTableView::indicator:checked {{
    background-color: {c['accent']};
    border: 1px solid {c['accent']};
}}

QSplitter::handle {{
    background-color: {c['border_soft']};
}}

QSplitter::handle:horizontal {{
    width: 3px;
}}

QSplitter::handle:vertical {{
    height: 3px;
}}

QStatusBar {{
    background-color: {c['surface']};
    color: {c['text_dim']};
    border-top: 1px solid {c['border_soft']};
}}

QStatusBar::item {{
    border: none;
}}

QToolTip {{
    background-color: {c['elevated']};
    color: {c['text']};
    border: 1px solid {c['accent']};
    padding: 5px;
    border-radius: 6px;
}}

QScrollArea {{
    border: none;
    background-color: transparent;
}}

#StatusPill {{
    background-color: {c['surface_alt']};
    border: 1px solid {c['border']};
    border-radius: 12px;
    padding: 4px 12px;
    color: {c['text_dim']};
    font-size: 12px;
    font-weight: 600;
}}

#LogPanel {{
    background-color: {c['surface']};
    border: 1px solid {c['border_soft']};
    border-radius: 10px;
    color: {c['text_dim']};
    font-family: "Cascadia Mono", Consolas, monospace;
    font-size: 11.5px;
}}
"""
