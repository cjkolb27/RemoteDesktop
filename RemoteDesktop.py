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
from queue import Queue
import av
import PyNvVideoCodec as nvc
import win32api
import win32con

WIDTH, HEIGHT = 2560, 1440
FPS = 30
GPU_ID = 0

ENC_PARAMS = {
    "bitrate": "18M",              # 10 Megabits per second
    "max_bitrate": "30M",
    "rc_mode": "vbr",
    "profile": "main",
    "multi_pass": "disabled",
    "bframes": 0,
}

encoder = nvc.CreateEncoder(
    width=WIDTH,
    height=HEIGHT,
    fmt="ABGR",
    codec="hevc",
    gop=60,
    usecpuinputbuffer=True,
    fps=60,
    preset="P2",
    **ENC_PARAMS
)

codec_ctx = av.CodecContext.create('hevc', 'r')
codec_ctx.flags |= getattr(av.codec.context.Flags, 'LOW_DELAY', 0x0008)
# codec_ctx.thread_type = 'SLICE'

def mouse_evt(event, x, y, flags, param):
    # Mouse is Moving
    win32api.SetCursor(None)
    # if event == cv2.EVENT_MOUSEMOVE:
    #     win32api.SetCursor(win32api.LoadCursor(0, win32con.IDC_SIZEALL))

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
        self.hostname_label = QtWidgets.QLabel("Hostname:")
        self.hostname_edit = QtWidgets.QLineEdit("")

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
        serverSocket.bind(("0.0.0.0", port))
        serverSocket.listen(1)

        def streamToClient(conn):
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            fqueue = Queue(maxsize=3)
            def capture():
                with mss.mss() as sct:
                    monitor = sct.monitors[1]
                    while not End[0]:
                        sct_img = sct.grab(monitor)
                        frame = np.array(sct_img) #[:, :, :3]  # RGB
                        if fqueue.full():
                            print("Full")
                            try: fqueue.get_nowait() # Always keep the queue fresh
                            except: pass
                        fqueue.put(frame)

            def sending(conns):
                try:
                    fps_start_time = time.time()
                    fps_counter = 0
                    current_fps = 0
                    while not End[0]:
                        frame = fqueue.get()
                        packets = encoder.Encode(frame)
                        fps_counter += 1
                        if (time.time() - fps_start_time) > 1.0:
                            current_fps = fps_counter
                            print(f"SERVER (Capture) FPS: {current_fps}")
                            fps_counter = 0
                            fps_start_time = time.time()
                        if packets:
                            packets = packets
                            
                            # conns.send(len(packets).to_bytes(4, 'big') + packets)

                except (BrokenPipeError, ConnectionResetError):
                    print("Client disconnected")
                    pass

                finally:
                    conns.close()

            threading.Thread(target=capture, daemon=True).start()
            threading.Thread(target=sending, args=(conn,), daemon=True).start()
        print("Looking For Connections")
        serverSocket.settimeout(0.5)
        while not End[0]:
            try:
                connId, _ = serverSocket.accept()
                print("Client Connected")
                threading.Thread(
                    target=streamToClient,
                    args=(connId,),
                    daemon=True
                ).start()
            except:
                continue
        serverSocket.close()
    else:
        clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        clientSocket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        print("Looking for server")
        try:
            clientSocket.connect((host, port))
        except OSError:
            return
        print("Server found")

        def recv_exact(sock, size):
            data = b""
            while len(data) < size:
                chunk = sock.recv(size - len(data))
                if not chunk:
                    raise ConnectionError("Socket closed")
                data += chunk
            return data
        
        try:
            display_fps_start_time = time.time()
            display_fps_counter = 0
            display_fps_text = "FPS: 0"

            while not End[0]:
                size = recv_exact(clientSocket, 4)
                if not size:
                    break
                size = int.from_bytes(size, 'big')
                packets = recv_exact(clientSocket, size)
                raw = bytes(packets)
                if not raw: # Skip empty packets
                    continue
                frames = av.Packet(raw)
                try:
                    allFrames = codec_ctx.decode(frames)
                    for f in allFrames:
                        img = f.to_ndarray(format='rgb24')
                        # img_upscaled = cv2.resize(img, (2560, 1440), interpolation=cv2.INTER_LINEAR)

                        display_fps_counter += 1
                        if (time.time() - display_fps_start_time) > 1.0:
                            display_fps_text = f"FPS: {display_fps_counter}"
                            display_fps_counter = 0
                            display_fps_start_time = time.time()

                        win_name = "Decoded Video"    
                        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)

                        # Draw the FPS on the image before showing it
                        cv2.putText(img, display_fps_text, (10, 30), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        
                        cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                        cv2.setMouseCallback(win_name, mouse_evt)
                        
                        cv2.imshow(win_name, img)
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            break
                except Exception as e:
                    print(f"Error: {e}")
                    continue
        finally:
            clientSocket.close()
            cv2.destroyAllWindows()
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
