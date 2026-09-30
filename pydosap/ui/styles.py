"""Tema escuro da aplicação (paleta Fusion + QSS), na identidade visual Magnum Tires."""
from PySide6.QtGui import QColor, QPalette

# --- paleta -----------------------------------------------------------------
RED = "#EB1D26"          # vermelho da marca Magnum
RED_HOVER = "#FF3A42"
RED_PRESSED = "#C4141C"

BG_0 = "#121316"         # fundo da janela
BG_1 = "#1A1C1F"         # painéis / grupos
BG_2 = "#212327"         # campos de entrada, linhas alternadas
BG_3 = "#2B2E33"         # hover / bordas de destaque
BORDER = "#34373D"

TEXT = "#E8E9EB"
TEXT_MUTED = "#9AA0A8"
TEXT_DISABLED = "#5B5F66"

GREEN = "#2FB170"
GREEN_BG = "#173225"
YELLOW = "#E0A72E"
YELLOW_BG = "#332B14"
RED_STATUS = "#F04A4F"
RED_BG = "#341A1C"

ACCENT = RED  # mantido por compatibilidade com o resto do código

# Altura padrão de linha das tabelas (QTableView/QTableWidget) em toda a aplicação —
# um pouco maior que o padrão do Qt para facilitar a leitura.
ALTURA_LINHA = 30


def aplicar_paleta_escura(app) -> None:
    """Paleta Fusion escura — cobre diálogos nativos (QMessageBox, QFileDialog...)
    que o QSS sozinho não alcança."""
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG_0))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(BG_2))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(BG_1))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(BG_1))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(BG_2))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.Link, QColor(RED_HOVER))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(RED))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(TEXT_DISABLED))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(TEXT_DISABLED))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(TEXT_DISABLED))
    app.setPalette(pal)


QSS = f"""
* {{ outline: none; }}

QWidget {{
    background: transparent;
    color: {TEXT};
    font-size: 13px;
    selection-background-color: {RED};
    selection-color: white;
}}

QMainWindow, QDialog {{ background: {BG_0}; }}

QToolTip {{
    background: {BG_1}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 6px;
}}

/* --- painéis ------------------------------------------------------------ */
QGroupBox {{
    background: {BG_1};
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 12px; padding: 0 6px;
    color: {TEXT_MUTED}; background: {BG_0};
}}

QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}

/* --- botões --------------------------------------------------------------*/
QPushButton {{
    padding: 7px 16px; border: 1px solid {BORDER}; border-radius: 6px;
    background: {BG_2}; color: {TEXT};
}}
QPushButton:hover {{ background: {BG_3}; border-color: #454951; }}
QPushButton:pressed {{ background: #17181B; }}
QPushButton:disabled {{ color: {TEXT_DISABLED}; background: {BG_1}; border-color: {BORDER}; }}

QPushButton[primary="true"] {{
    background: {RED}; color: white; border-color: {RED}; font-weight: 600;
}}
QPushButton[primary="true"]:hover {{ background: {RED_HOVER}; border-color: {RED_HOVER}; }}
QPushButton[primary="true"]:pressed {{ background: {RED_PRESSED}; }}
QPushButton[primary="true"]:disabled {{ background: #5C2226; border-color: #5C2226; color: #C9AEAF; }}

QPushButton[danger="true"] {{ color: {RED_STATUS}; border-color: #5C2226; }}
QPushButton[danger="true"]:hover {{ background: {RED_BG}; }}

/* --- campos de entrada ---------------------------------------------------*/
QLineEdit, QDateEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox {{
    padding: 5px 8px; border: 1px solid {BORDER}; border-radius: 6px;
    background: {BG_2}; color: {TEXT};
}}
QLineEdit:focus, QDateEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color: {RED}; }}
QLineEdit:disabled, QDateEdit:disabled {{ color: {TEXT_DISABLED}; background: {BG_1}; }}
QLineEdit::placeholder {{ color: {TEXT_MUTED}; }}

QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {BG_1}; color: {TEXT}; border: 1px solid {BORDER};
    selection-background-color: {RED}; selection-color: white;
}}

QDateEdit::drop-down {{ border: none; width: 22px; }}
QCalendarWidget {{ background: {BG_1}; color: {TEXT}; }}
QCalendarWidget QToolButton {{ color: {TEXT}; background: {BG_2}; }}
QCalendarWidget QAbstractItemView:enabled {{ background: {BG_1}; color: {TEXT}; selection-background-color: {RED}; }}

QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px; border: 1px solid {BORDER}; border-radius: 3px; background: {BG_2};
}}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {RED}; border-color: {RED};
}}

/* --- tabelas ---------------------------------------------------------- */
QTableView, QTableWidget {{
    background: {BG_1};
    alternate-background-color: {BG_2};
    gridline-color: {BORDER};
    selection-background-color: #4A1417;
    selection-color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
QTableView::item, QTableWidget::item {{ padding: 3px 6px; }}
QHeaderView::section {{
    background: {BG_2}; color: {TEXT_MUTED}; padding: 7px;
    border: none; border-right: 1px solid {BORDER}; border-bottom: 1px solid {BORDER};
    font-weight: 600;
}}
QTableCornerButton::section {{ background: {BG_2}; border: none; }}

QScrollBar:vertical {{ background: {BG_0}; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BG_3}; min-height: 24px; border-radius: 5px; }}
QScrollBar::handle:vertical:hover {{ background: #454951; }}
QScrollBar:horizontal {{ background: {BG_0}; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {BG_3}; min-width: 24px; border-radius: 5px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}

/* --- progresso / abas --------------------------------------------------- */
QProgressBar {{
    border: 1px solid {BORDER}; border-radius: 6px; text-align: center;
    min-height: 18px; background: {BG_2}; color: {TEXT};
}}
QProgressBar::chunk {{ background: {RED}; border-radius: 5px; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; top: -1px; background: {BG_0}; }}
QTabBar::tab {{
    padding: 9px 20px; color: {TEXT_MUTED}; background: {BG_1};
    border: 1px solid {BORDER}; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px;
}}
QTabBar::tab:selected {{ color: {TEXT}; background: {BG_0}; font-weight: 600; border-bottom: 2px solid {RED}; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; background: {BG_2}; }}

QMenuBar {{ background: {BG_0}; color: {TEXT}; }}
QMenuBar::item:selected {{ background: {BG_2}; }}
QMenu {{ background: {BG_1}; color: {TEXT}; border: 1px solid {BORDER}; }}
QMenu::item:selected {{ background: {RED}; color: white; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

QStatusBar {{ background: {BG_1}; color: {TEXT_MUTED}; border-top: 1px solid {BORDER}; }}

/* --- selos de status (badges) ------------------------------------------- */
QLabel#badge {{
    padding: 3px 10px; border-radius: 10px; background: {BG_2}; color: {TEXT_MUTED};
    font-weight: 600;
}}
QLabel#badge[status="ok"] {{ background: {GREEN_BG}; color: {GREEN}; }}
QLabel#badge[status="erro"] {{ background: {RED_BG}; color: {RED_STATUS}; }}
QLabel#badge[status="processando"] {{ background: {YELLOW_BG}; color: {YELLOW}; }}

QLabel#valorDestaque {{ font-size: 16px; font-weight: 700; color: {TEXT}; }}

QFrame#bannerResultado {{
    border-radius: 8px; border: 1px solid {BORDER}; background: {BG_2}; padding: 4px;
}}
QFrame#bannerResultado[status="ok"] {{ background: {GREEN_BG}; border-color: {GREEN}; }}
QFrame#bannerResultado[status="erro"] {{ background: {RED_BG}; border-color: {RED_STATUS}; }}
"""
