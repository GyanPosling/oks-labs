import codecs
import sys

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

    def __init__(self):
        super().__init__()
        self.setPlaceholderText("Type a message and press Enter to send")

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
        self.resize(900, 620)

        self.create_widgets()
        self.create_layout()
        self.connect_signals()
        self.apply_styles()
        self.load_ports()

        self.status_timer = QtCore.QTimer(self)
        self.status_timer.timeout.connect(self.update_status_counter)
        self.status_timer.start(1000)

    def create_widgets(self):
        self.port_combo = QtWidgets.QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self.port_combo.addItem("")

        self.byte_size_combo = QtWidgets.QComboBox()
        self.byte_size_combo.addItem("")
        for byte_size in (5, 6, 7, 8):
            self.byte_size_combo.addItem(str(byte_size), byte_size)

        self.input_text = MessageInput()
        self.input_text.setEnabled(False)

        self.output_text = QtWidgets.QPlainTextEdit()
        self.output_text.setReadOnly(True)

        self.status_text = QtWidgets.QPlainTextEdit()
        self.status_text.setReadOnly(True)

    def create_layout(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        control_group = QtWidgets.QGroupBox("Control Window")
        control_layout = QtWidgets.QFormLayout(control_group)
        control_layout.addRow("COM port:", self.port_combo)
        control_layout.addRow("Byte size:", self.byte_size_combo)

        messages_layout = QtWidgets.QHBoxLayout()
        input_group = QtWidgets.QGroupBox("Input Window")
        input_layout = QtWidgets.QVBoxLayout(input_group)
        input_layout.addWidget(self.input_text)

        output_group = QtWidgets.QGroupBox("Output Window")
        output_layout = QtWidgets.QVBoxLayout(output_group)
        output_layout.addWidget(self.output_text)

        messages_layout.addWidget(input_group, 1)
        messages_layout.addWidget(output_group, 1)

        status_group = QtWidgets.QGroupBox("Status Window")
        status_layout = QtWidgets.QVBoxLayout(status_group)
        status_layout.addWidget(self.status_text)

        main_layout.addWidget(control_group)
        main_layout.addLayout(messages_layout, 1)
        main_layout.addWidget(status_group, 1)

    def connect_signals(self):
        self.port_combo.currentTextChanged.connect(self.try_open_port)
        self.port_combo.lineEdit().editingFinished.connect(self.try_open_port)
        self.byte_size_combo.currentIndexChanged.connect(self.try_open_port)
        self.input_text.send_requested.connect(self.send_message)

    def apply_styles(self):
        self.setStyleSheet(
            """
            QWidget {
                background: #f4f6f8;
                color: #1f2933;
                font-family: Segoe UI, Arial, sans-serif;
                font-size: 14px;
            }
            QGroupBox {
                border: 1px solid #cbd5df;
                border-radius: 6px;
                margin-top: 12px;
                padding: 12px;
                background: #ffffff;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QComboBox, QPlainTextEdit {
                border: 1px solid #aab7c4;
                border-radius: 4px;
                background: #ffffff;
                padding: 6px;
            }
            QPlainTextEdit:disabled {
                background: #eef2f6;
                color: #6b7785;
            }
            """
        )

    def load_ports(self):
        if serial is None:
            self.show_error("pyserial is not installed. Install dependencies: pip install PyQt6 pyserial")
            return

        available_ports = [port.device for port in list_ports.comports()]
        self.port_combo.addItems(available_ports)
        if not available_ports:
            self.write_status("No COM ports found. You can enter the port manually, for example COM3.")

    def try_open_port(self):
        if self.serial_port is not None:
            return

        port_name = self.port_combo.currentText().strip()
        byte_size = self.byte_size_combo.currentData()

        if not port_name or byte_size is None:
            return

        self.open_port(port_name, byte_size)

    def open_port(self, port_name, byte_size):
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
        self.input_text.setEnabled(True)
        self.input_text.setFocus()

        self.write_status(f"Opened port: {port_name}")
        self.write_status(f"Baud rate: {BAUD_RATE}")
        self.write_status(f"Byte size: {byte_size}")
        self.write_status("Parity: none")
        self.write_status("Stop bits: 1")
        self.write_status("Transmission: line by line after Enter")

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
            self.write_status(f"Sent message: {message.rstrip()}")
        except (OSError, serial.SerialException) as error:
            self.show_error(f"Data send error: {error}")

    def append_received_text(self, text):
        cursor = self.output_text.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.output_text.setTextCursor(cursor)
        self.output_text.ensureCursorVisible()

    def handle_receiver_error(self, message):
        self.write_status(message)
        self.input_text.setEnabled(False)

    def update_status_counter(self):
        lines = self.status_text.toPlainText().splitlines()
        lines = [line for line in lines if not line.startswith("Sent characters:")]
        lines.append(f"Sent characters: {self.sent_characters}")
        self.status_text.setPlainText("\n".join(lines))
        self.status_text.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def write_status(self, message):
        self.status_text.appendPlainText(message)

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
