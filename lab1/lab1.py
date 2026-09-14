import codecs
import sys
from pathlib import Path

try:
    import serial
    from serial.tools import list_ports
except ModuleNotFoundError:
    serial = None
    list_ports = None

try:
    from PyQt6 import QtCore, QtGui, QtWidgets
except ModuleNotFoundError:
    print("PyQt6 is not installed. Install dependencies: pip install PyQt6 pyserial")
    raise


BAUD_RATE = 9600
PARITY = "N"
STOP_BITS = 1
TIMEOUT_SECONDS = 0.05
WRITE_TIMEOUT_SECONDS = 1


class ReceiverThread(QtCore.QThread):
    data_received = QtCore.pyqtSignal(str)
    error_occurred = QtCore.pyqtSignal(str)

    def __init__(self, serial_port):
        super().__init__()
        self.serial_port = serial_port
        self._running = True
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def run(self):
        while self._running:
            try:
                if self.serial_port is None or not self.serial_port.is_open:
                    break

                waiting = self.serial_port.in_waiting
                if waiting:
                    raw_data = self.serial_port.read(waiting)
                    text = self.decoder.decode(raw_data)
                    if text:
                        self.data_received.emit(text)
                else:
                    self.msleep(20)
            except (OSError, serial.SerialException) as error:
                if self._running:
                    self.error_occurred.emit(f"Data receive error: {error}")
                break
            except Exception as error:
                if self._running:
                    self.error_occurred.emit(f"Unexpected receive error: {error}")
                break

    def stop(self):
        self._running = False
        self.wait(1000)


class MessageInput(QtWidgets.QPlainTextEdit):
    send_requested = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setPlaceholderText("Type a message and press Enter")

    def keyPressEvent(self, event):
        if event.key() in (
            QtCore.Qt.Key.Key_Return,
            QtCore.Qt.Key.Key_Enter,
        ):
            message = self.toPlainText() + "\n"
            self.clear()
            self.send_requested.emit(message)
            event.accept()
            return

        super().keyPressEvent(event)


class HoverComboBox(QtWidgets.QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.view().setMouseTracking(True)
        self.view().installEventFilter(self)
        self.view().viewport().setMouseTracking(True)
        self.view().viewport().installEventFilter(self)

    def setEditable(self, editable):
        super().setEditable(editable)
        line_edit = self.lineEdit()
        if editable and line_edit is not None:
            line_edit.setMouseTracking(True)
            line_edit.installEventFilter(self)

    def eventFilter(self, watched, event):
        if (
            self.lineEdit() is not None
            and watched is self.lineEdit()
            and event.type() == QtCore.QEvent.Type.Enter
        ):
            self.open_popup_on_hover()
        elif event.type() == QtCore.QEvent.Type.Leave:
            self.close_popup_if_pointer_outside()
        return super().eventFilter(watched, event)

    def enterEvent(self, event):
        super().enterEvent(event)
        self.open_popup_on_hover()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.close_popup_if_pointer_outside()

    def open_popup_on_hover(self):
        if self.isEnabled() and not self.view().isVisible():
            QtCore.QTimer.singleShot(0, self._show_popup)

    def _show_popup(self):
        if self.isEnabled() and not self.view().isVisible():
            self.showPopup()

    def close_popup_if_pointer_outside(self):
        QtCore.QTimer.singleShot(60, self._hide_popup_if_pointer_outside)

    def _hide_popup_if_pointer_outside(self):
        if not self.view().isVisible():
            return

        cursor_position = QtGui.QCursor.pos()
        combo_rect = QtCore.QRect(self.mapToGlobal(QtCore.QPoint(0, 0)), self.size())
        popup_rect = QtCore.QRect(
            self.view().mapToGlobal(QtCore.QPoint(0, 0)),
            self.view().size(),
        )

        if not combo_rect.contains(cursor_position) and not popup_rect.contains(cursor_position):
            self.hidePopup()


class ComPortWindow(QtWidgets.QWidget):
    # Available COM port parameters:
    # baudrate: standard speeds, for example 110, 300, 1200, 2400, 4800,
    # 9600, 19200, 38400, 57600, 115200.
    # bytesize: 5, 6, 7, 8.
    # parity: none, even, odd, mark, space.
    # stopbits: 1, 1.5, 2.
    # Variant 2 requires choosing bytesize; the other parameters are fixed.

    def __init__(self):
        super().__init__()
        self.serial_port = None
        self.receiver = None
        self.sent_characters = 0
        self.status_message = "Select COM port and byte size"

        self.setWindowTitle("Lab 1: COM Port")
        self.resize(960, 600)

        self.create_widgets()
        self.create_layout()
        self.apply_styles()
        self.load_ports()
        self.connect_signals()
        self.update_status_counter()

        self.status_timer = QtCore.QTimer(self)
        self.status_timer.timeout.connect(self.update_status_counter)
        self.status_timer.start(1000)

        self.input_text.setFocus()

    def create_widgets(self):
        self.port_combo = HoverComboBox()

        self.byte_size_combo = HoverComboBox()
        for byte_size in (5, 6, 7, 8):
            self.byte_size_combo.addItem(str(byte_size), byte_size)
        self.byte_size_combo.setCurrentIndex(-1)
        self.byte_size_combo.setMaxVisibleItems(self.byte_size_combo.count())

        self.input_text = MessageInput()

        self.output_text = QtWidgets.QPlainTextEdit()
        self.output_text.setReadOnly(True)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setObjectName("statusText")
        self.status_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.status_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
        )
        self.status_label.setWordWrap(True)

    def create_layout(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        control_panel = self.create_panel("Control")
        control_grid = QtWidgets.QGridLayout()
        control_grid.setHorizontalSpacing(16)
        control_grid.setVerticalSpacing(8)

        port_label = self.create_field_label("COM port")
        byte_size_label = self.create_field_label("Byte size")

        control_grid.addWidget(port_label, 0, 0)
        control_grid.addWidget(byte_size_label, 0, 1)
        control_grid.addWidget(self.port_combo, 1, 0)
        control_grid.addWidget(self.byte_size_combo, 1, 1)
        control_grid.setColumnStretch(0, 1)
        control_grid.setColumnStretch(1, 1)
        control_panel.layout().addLayout(control_grid)

        status_panel = self.create_panel("State")
        status_panel.layout().setContentsMargins(14, 10, 14, 10)
        status_panel.layout().setSpacing(4)
        status_panel.setFixedHeight(92)
        status_layout = status_panel.layout()
        status_layout.addWidget(self.status_label)

        top_layout = QtWidgets.QHBoxLayout()
        top_layout.setSpacing(16)
        top_layout.addWidget(
            control_panel,
            7,
            alignment=QtCore.Qt.AlignmentFlag.AlignTop,
        )
        top_layout.addWidget(
            status_panel,
            3,
            alignment=QtCore.Qt.AlignmentFlag.AlignTop,
        )

        messages_layout = QtWidgets.QHBoxLayout()
        messages_layout.setSpacing(16)

        input_group = self.create_panel("Input")
        input_layout = input_group.layout()
        input_layout.addWidget(self.input_text)

        output_group = self.create_panel("Output")
        output_layout = output_group.layout()
        output_layout.addWidget(self.output_text)

        messages_layout.addWidget(input_group, 1)
        messages_layout.addWidget(output_group, 1)

        main_layout.addLayout(top_layout)
        main_layout.addLayout(messages_layout, 1)

    def create_panel(self, title):
        panel = QtWidgets.QFrame()
        panel.setObjectName("panel")

        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        title_label = QtWidgets.QLabel(title)
        title_label.setObjectName("sectionTitle")
        layout.addWidget(title_label)

        return panel

    def create_field_label(self, text):
        label = QtWidgets.QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def connect_signals(self):
        self.port_combo.activated.connect(self.try_open_port)
        self.byte_size_combo.currentIndexChanged.connect(self.try_open_port)
        self.input_text.send_requested.connect(self.send_message)

    def apply_styles(self):
        arrow_path = Path(__file__).resolve().parent.joinpath("down-arrow.svg").as_posix()
        self.setStyleSheet(
            f"""
            QWidget {{
                background: #101418;
                color: #ecfeff;
                font-family: Segoe UI, Arial, sans-serif;
                font-size: 14px;
            }}
            QFrame#panel {{
                background: #182026;
                border: 1px solid #2f3d46;
            }}
            QLabel#sectionTitle {{
                color: #ecfeff;
                font-size: 15px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}
            QLabel#fieldLabel {{
                color: #9fb7bd;
                font-size: 12px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
            QPlainTextEdit {{
                border: 1px solid #2f3d46;
                background: #0d1216;
                color: #ecfeff;
                padding: 10px;
                selection-background-color: #0f766e;
            }}
            QPlainTextEdit:focus {{
                border: 1px solid #2dd4bf;
            }}
            QComboBox {{
                border: 1px solid #2f3d46;
                background: #0d1216;
                color: #ecfeff;
                min-height: 34px;
                padding-left: 10px;
                padding-right: 34px;
            }}
            QComboBox:hover {{
                border: 1px solid #2dd4bf;
                background: #132027;
            }}
            QComboBox:disabled {{
                color: #6f858b;
                background: #12191e;
                border: 1px solid #25323a;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 32px;
                border-left: 1px solid #2f3d46;
                background: #17262d;
            }}
            QComboBox::down-arrow {{
                image: url({arrow_path});
                width: 12px;
                height: 8px;
            }}
            QComboBox QAbstractItemView {{
                background: #182026;
                color: #ecfeff;
                selection-background-color: #0f766e;
                border: 1px solid #2f3d46;
                outline: 0;
            }}
            QLabel {{
                font-weight: 400;
                background: transparent;
            }}
            QLabel#statusText {{
                color: #ecfeff;
                font-size: 12px;
            }}
            """
        )

    def load_ports(self):
        if serial is None:
            self.show_error("pyserial is not installed. Install dependencies: pip install PyQt6 pyserial")
            return

        available_ports = [port.device for port in list_ports.comports()]
        self.port_combo.addItems(available_ports)
        self.port_combo.setMaxVisibleItems(max(1, self.port_combo.count()))
        self.port_combo.setCurrentIndex(-1)
        if not available_ports:
            self.write_status("No COM ports found.")

    def try_open_port(self):
        if self.serial_port is not None:
            return

        port_name = self.port_combo.currentText().strip()
        byte_size = self.byte_size_combo.currentData()

        if not port_name or byte_size is None:
            return

        self.open_port(port_name, byte_size)

    def open_port(self, port_name, byte_size):
        if serial is None:
            self.show_error("pyserial is not installed. Install dependencies: pip install PyQt6 pyserial")
            return

        try:
            self.serial_port = serial.Serial(
                port=port_name,
                baudrate=BAUD_RATE,
                bytesize=byte_size,
                parity=PARITY,
                stopbits=STOP_BITS,
                timeout=TIMEOUT_SECONDS,
                write_timeout=WRITE_TIMEOUT_SECONDS,
            )
        except (serial.SerialException, OSError, ValueError) as error:
            self.serial_port = None
            self.show_error(f"Failed to open {port_name}: {error}")
            return

        self.port_combo.setEnabled(False)
        self.byte_size_combo.setEnabled(False)
        self.input_text.setFocus()
        self.write_status(f"Opened {port_name}")

        self.receiver = ReceiverThread(self.serial_port)
        self.receiver.data_received.connect(self.append_received_text)
        self.receiver.error_occurred.connect(self.handle_receiver_error)
        self.receiver.start()

    def send_message(self, message):
        if self.serial_port is None or not self.serial_port.is_open:
            self.show_error("COM port is not open.")
            return

        try:
            for character in message:
                self.serial_port.write(character.encode("utf-8"))
            self.sent_characters += len(message)
            self.write_status(f"Last sent: {len(message)} characters")
        except (OSError, serial.SerialException, UnicodeEncodeError, ValueError) as error:
            self.show_error(f"Data send error: {error}")

    def append_received_text(self, text):
        clean_text = text.replace("\r\n", "\n").replace("\r", "\n")
        cursor = QtGui.QTextCursor(self.output_text.document())
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        cursor.insertText(clean_text)
        self.output_text.ensureCursorVisible()

    def handle_receiver_error(self, message):
        self.show_error(message)

    def update_status_counter(self):
        self.status_label.setText(f"Sent characters: {self.sent_characters}")

    def write_status(self, message):
        self.status_message = message
        self.update_status_counter()

    def show_error(self, message):
        self.write_status(message)
        QtWidgets.QMessageBox.critical(self, "Error", message)

    def closeEvent(self, event):
        if self.receiver is not None:
            self.receiver.stop()
            self.receiver = None

        if self.serial_port is not None and self.serial_port.is_open:
            self.serial_port.close()

        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = ComPortWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
