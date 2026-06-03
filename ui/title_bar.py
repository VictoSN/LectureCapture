from PyQt6.QtWidgets import QPushButton, QLabel, QHBoxLayout
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QMouseEvent

def attach_window_controls(window, header_layout: QHBoxLayout, title: str = None) -> None:
    if title:
        title_label = QLabel(title)
        header_layout.insertWidget(0, title_label)

    header_layout.addStretch()

    min_button = QPushButton("—")
    min_button.setFixedSize(30, 30)
    min_button.clicked.connect(window.showMinimized)
    header_layout.addWidget(min_button)

    max_button = QPushButton("□")
    max_button.setFixedSize(30, 30)
    def toggle_max():
        if window.isMaximized():
            window.showNormal()
        else:
            window.showMaximized()
    max_button.clicked.connect(toggle_max)
    header_layout.addWidget(max_button)

    close_button = QPushButton("✕")
    close_button.setFixedSize(30, 30)
    close_button.clicked.connect(window.close)
    header_layout.addWidget(close_button)

    # Drag logic — attach to the widget that owns the header layout
    header_widget = header_layout.parentWidget()
    if not header_widget:
        return

    header_widget._drag_pos = None

    def mouse_press(event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            header_widget._drag_pos = event.globalPosition().toPoint() - window.frameGeometry().topLeft()

    def mouse_move(event: QMouseEvent):
        if header_widget._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            window.move(event.globalPosition().toPoint() - header_widget._drag_pos)

    def mouse_release(event: QMouseEvent):
        header_widget._drag_pos = None

    def mouse_double_click(event: QMouseEvent):
        toggle_max()

    header_widget.mousePressEvent = mouse_press
    header_widget.mouseMoveEvent = mouse_move
    header_widget.mouseReleaseEvent = mouse_release
    header_widget.mouseDoubleClickEvent = mouse_double_click