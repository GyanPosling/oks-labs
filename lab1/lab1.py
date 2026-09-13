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
                waiting = self.serial_port.in_waiting
                if waiting:
                    raw_data = self.serial_port.read(waiting)
                    text = self.decoder.decode(raw_data)
                    if text:
                        self.data_received.emit(text)
                else:
                    self.msleep(20)
            except (OSError, serial.SerialException) as error:
                self.error_occurred.emit(f"Data receive error: {error}")
                break

    def stop(self):
        self._running = False
        self.wait(1000)


class MessageInput(QtWidgets.QPlainTextEdit):
    send_requested = QtCore.pyqtSignal(str)

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
        return super().eventFilter(watched, event)

    def enterEvent(self, event):
        super().enterEvent(event)
        self.open_popup_on_hover()

    def open_popup_on_hover(self):
        if self.isEnabled() and not self.view().isVisible():
            QtCore.QTimer.singleShot(0, self._show_popup)

    def _show_popup(self):
        if self.isEnabled() and not self.view().isVisible():
            self.showPopup()


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

        self.setWindowTitle("Lab 1: COM Port")
        self.resize(900, 560)

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
        self.port_combo.addItem("")

        self.byte_size_combo = HoverComboBox()
        for byte_size in (5, 6, 7, 8):
            self.byte_size_combo.addItem(str(byte_size), byte_size)
        self.byte_size_combo.setCurrentIndex(-1)

        self.input_text = MessageInput()

        self.output_text = QtWidgets.QPlainTextEdit()
        self.output_text.setReadOnly(True)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

    def create_layout(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        control_group = QtWidgets.QGroupBox("Control")
        control_layout = QtWidgets.QFormLayout(control_group)
        control_layout.addRow("COM port:", self.port_combo)
        control_layout.addRow("Byte size:", self.byte_size_combo)

        messages_layout = QtWidgets.QHBoxLayout()

        input_group = QtWidgets.QGroupBox("Input")
        input_layout = QtWidgets.QVBoxLayout(input_group)
        input_layout.addWidget(self.input_text)

        output_group = QtWidgets.QGroupBox("Output")
        output_layout = QtWidgets.QVBoxLayout(output_group)
        output_layout.addWidget(self.output_text)

        messages_layout.addWidget(input_group, 1)
        messages_layout.addWidget(output_group, 1)

        status_group = QtWidgets.QGroupBox("Status")
        status_layout = QtWidgets.QVBoxLayout(status_group)
        status_layout.addWidget(self.status_label)

        main_layout.addWidget(control_group)
        main_layout.addLayout(messages_layout, 1)
        main_layout.addWidget(status_group)

    def connect_signals(self):
        self.port_combo.activated.connect(self.try_open_port)
        self.byte_size_combo.currentIndexChanged.connect(self.try_open_port)
        self.input_text.send_requested.connect(self.send_message)

    def apply_styles(self):
        arrow_path = Path(__file__).resolve().parent.joinpath("down-arrow.svg").as_posix()
        self.setStyleSheet(
            f"""
            QWidget {{
                background: #f4f6f8;
                color: #1f2933;
                font-family: Segoe UI, Arial, sans-serif;
                font-size: 14px;
            }}
            QGroupBox {{
                border: 1px solid #cbd5df;
                border-radius: 4px;
                margin-top: 12px;
                padding: 12px;
                background: #ffffff;
                font-weight: 600;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }}
            QPlainTextEdit {{
                border: 1px solid #aab7c4;
                border-radius: 4px;
                background: #ffffff;
                padding: 6px;
            }}
            QComboBox {{
                border: 1px solid #aab7c4;
                border-radius: 4px;
                background: #ffffff;
                min-height: 28px;
                padding-left: 6px;
                padding-right: 28px;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 28px;
                border-left: 1px solid #aab7c4;
                background: #e8eef3;
            }}
            QComboBox::down-arrow {{
                image: url({arrow_path});
                width: 12px;
                height: 8px;
            }}
            QComboBox QAbstractItemView {{
                background: #ffffff;
                color: #1f2933;
                selection-background-color: #d9e2ec;
                border: 1px solid #aab7c4;
            }}
            QLabel {{
                font-weight: 400;
            }}
            """
        )

    def load_ports(self):
        if serial is None:
            self.show_error("pyserial is not installed. Install dependencies: pip install PyQt6 pyserial")
            return

        available_ports = [port.device for port in list_ports.comports()]
        self.port_combo.addItems(available_ports)
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
        except serial.SerialException as error:
            self.serial_port = None
            self.show_error(f"Failed to open {port_name}: {error}")
            return

        self.port_combo.setEnabled(False)
        self.byte_size_combo.setEnabled(False)
        self.input_text.setFocus()

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
        except (OSError, serial.SerialException) as error:
            self.show_error(f"Data send error: {error}")

    def append_received_text(self, text):
        cursor = self.output_text.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.output_text.setTextCursor(cursor)
        self.output_text.ensureCursorVisible()

    def handle_receiver_error(self, message):
        self.show_error(message)

    def update_status_counter(self):
        self.status_label.setText(f"Sent characters: {self.sent_characters}")

    def show_error(self, message):
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
