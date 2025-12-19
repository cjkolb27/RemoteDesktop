import sys
import socket
import threading
from PyQt5 import QtWidgets, QtCore
from pathlib import Path
import pyaudio
import numpy as np
import time
import cv2
import mss
import subprocess

class SocketReader:
    def __init__(self, sock):
        self.sock = sock
    
    def read(self, n):
        return self.sock.recv(n)

# Dummy backend – replace with real logic
class RemoteStreamer(QtCore.QObject):
    status_changed = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = False
    
    def writeSettings(self, hostname, port, sc, inputString):
        with open((Path(__file__).parent / "Data" / "info.txt"), "w", newline='') as info:
            info.write(f"{hostname}\r\n{port}\r\n{sc}\r\n{inputString}\r\n")

    def start(self, hostname, port, sc, inputString):
        print(f"Starting stream to {hostname}:{port}")
        self.running = True
        self.status_changed.emit(f"Running → {hostname}:{port}")
        with open((Path(__file__).parent / "Data" / "info.txt"), "w", newline='') as info:
            info.write(f"{hostname}\r\n{port}\r\n{sc}\r\n{inputString}\r\n")

    def stop(self):
        print("Stopping stream")
        self.running = False
        self.status_changed.emit("Stopped")
        End[0] = True

    def flipflop(self, server):
        print(f"{server} Flipped")


class MainWindow(QtWidgets.QWidget):
    def __init__(self, streamer: RemoteStreamer):
        super().__init__()
        self.streamer = streamer

        self.thread = None

        # UI elements
        self.hostname_label   = QtWidgets.QLabel("Hostname:")
        self.hostname_edit  = QtWidgets.QLineEdit("")

        self.port_label = QtWidgets.QLabel("Server Port:")
        self.port_spin = QtWidgets.QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(1)
        self.serverclient = "True"
        self.inputString = ""
        self.input = 0
        with open((Path(__file__).parent / "Data" / "info.txt"), "r", newline='') as info:
            self.hostname_edit = QtWidgets.QLineEdit(info.readline().replace("\r\n", ""))
            self.port_spin.setValue(int(info.readline()))
            self.serverclient = info.readline().replace("\r\n", "")
            self.inputString = info.readline().replace("\r\n", "")
            print(self.inputString)

        self.status_lbl = QtWidgets.QLabel("Stopped")

        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if self.inputString in dev['name'] and dev['hostApi'] == 0:
                self.input = i
            print(f"Index: {i}, Name: {dev['name']}, Host API: {dev['hostApi']}")

        p.terminate()

        pa = pyaudio.PyAudio()
        print(pa.get_device_info_by_index(self.input))
        pa.terminate()

        self.server_btn = QtWidgets.QPushButton("Server")
        self.server_btn.setCheckable(True)
        self.server_btn.setFixedSize(130, 40)
        self.client_btn = QtWidgets.QPushButton("Client")
        self.client_btn.setCheckable(True)
        self.client_btn.setFixedSize(130, 40)
        self.start_btn = QtWidgets.QPushButton("Start")
        self.stop_btn  = QtWidgets.QPushButton("Stop")

        group = QtWidgets.QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.server_btn, 1)
        group.addButton(self.client_btn, 2)

        # Layout
        form_layout = QtWidgets.QFormLayout()
        form_layout.addRow(self.server_btn, self.client_btn)
        form_layout.addRow(self.hostname_label, self.hostname_edit)
        form_layout.addRow(self.port_label, self.port_spin)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addLayout(form_layout)
        main_layout.addWidget(self.status_lbl)
        main_layout.addLayout(btn_layout)

        # Connections
        self.server_btn.toggled.connect(self.on_flipflop)
        self.start_btn.clicked.connect(self.on_start)
        self.stop_btn.clicked.connect(self.on_stop)
        self.streamer.status_changed.connect(self.status_lbl.setText)
        if self.serverclient == "True":
            self.server_btn.setChecked(True)
        else:
            self.client_btn.setChecked(True)
        self.stop_btn.setEnabled(False)
    
    def on_flipflop(self, checked: bool):
        self.streamer.flipflop(checked)
        dest_ip = self.hostname_edit.text()
        dest_port = self.port_spin.value()
        if checked:
            self.serverclient = "True"
            self.hostname_edit.setEnabled(False)
        else:
            self.serverclient = "False"
            self.hostname_edit.setEnabled(True)
        self.streamer.writeSettings(dest_ip, dest_port, self.serverclient, self.inputString)
    
    def on_stop(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.client_btn.setEnabled(True)
        self.server_btn.setEnabled(True)
        self.streamer.stop()
        self.thread.join()
        self.thread = None

    def on_start(self):
        if self.streamer.running:
            QtWidgets.QMessageBox.information(self, "Info", "Already running")
            return
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        dest_hostname = self.hostname_edit.text()
        dest_port = self.port_spin.value()
        sc = self.serverclient
        self.streamer.start(dest_hostname, dest_port, sc, self.inputString)
        if self.serverclient == "True":
            self.client_btn.setEnabled(False)
            self.thread = threading.Thread(target=tryConnect, args=(True, socket.gethostname(), int(dest_port), int(self.input)))
        else:
            self.server_btn.setEnabled(False)
            self.thread = threading.Thread(target=tryConnect, args=(False, dest_hostname, int(dest_port), int(self.input)))
        self.thread.start()

def tryConnect(server, host, port, input):
    print("Thread Started")
    End[0] = False
    if server:
        serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print(f"{host} {port}")
        serverSocket.bind((host, port))
        serverSocket.listen(1)

        def streamToClient(conn):
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            # fqueue = Queue(maxsize=3)
            WIDTH = 1280
            HEIGHT = 720
            FPS = 30
            ffmpeg = subprocess.Popen(
                [
                    "ffmpeg",
                    "-f", "rawvideo",
                    "-pix_fmt", "bgr24",
                    "-s", f"{WIDTH}x{HEIGHT}",
                    "-r", str(FPS),
                    "-i", "-",

                    "-c:v", "h264_nvenc",
                    "-preset", "p1",
                    "-tune", "ull",
                    "-rc", "cbr",
                    "-b:v", "8M",
                    "-maxrate", "8M",
                    "-bufsize", "4M",

                    "-g", "30",
                    "-forced-idr", "1",
                    "-pix_fmt", "yuv420p",
                    "-profile:v", "high",

                    "-f", "mpegts",
                    "pipe:1"
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )
            def capture():
                with mss.mss() as sct:
                    monitor = sct.monitors[2]
                    while True:
                        rgb = np.array(sct.grab(monitor))[:, :, :3]
                        rgb = cv2.resize(rgb, (WIDTH, HEIGHT))
                        rgb = rgb.astype(np.uint8)
                        try:
                            ffmpeg.stdin.write(rgb.tobytes())
                        except (BrokenPipeError, OSError):
                            break
                        # time.sleep(1 / FPS)

            def sending(conns):
                try:
                    while True:
                        data = ffmpeg.stdout.read(4096)
                        if not data:
                            break
                        conns.sendall(data)

                except (BrokenPipeError, ConnectionResetError):
                    print("Client disconnected")
                    pass

                finally:
                    conns.close()

            threading.Thread(target=capture, daemon=True).start()
            threading.Thread(target=sending, args=(conn,), daemon=True).start()

        while not End[0]:
            connId, _ = serverSocket.accept()
            print("Client Connected")
            threading.Thread(
                target=streamToClient,
                args=(connId,),
                daemon=True
            ).start()
        serverSocket.close()
    else:
        # clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # clientSocket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # print("Looking for server")
        # try:
        #     clientSocket.connect((host, port))
        # except OSError:
        #     return
        
        try:
            cmd = [
                "ffplay",
                "-loglevel", "warning",
                "-fflags", "nobuffer",
                "-flags", "low_delay",
                "-framedrop",
                "-sync", "ext",
                "-probesize", "32",
                "-analyzeduration", "0",
                "-vf", "setpts=PTS-STARTPTS",
                f"tcp://{host}:{port}"
            ]

            subprocess.run(cmd)
        finally:
            # clientSocket.close()
            print("Client closed connections")
    return

if __name__ == "__main__":
    End = [True]
    End[0] = False
    rate = 44100
    channels = 2
    blocksize = 128
    app = QtWidgets.QApplication(sys.argv)
    streamer = RemoteStreamer()
    win = MainWindow(streamer)
    win.setWindowTitle("Python Audio Streamer")
    win.resize(300, 150)
    win.show()
    sys.exit(app.exec_())
