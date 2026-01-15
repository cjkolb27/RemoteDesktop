import sys
import socket
import threading
from PyQt5 import QtWidgets, QtCore
from pathlib import Path
import pyaudio
import numpy as np
import time
from queue import Queue
import av
import PyNvVideoCodec as nvc
import pygame
import keyboard
from pynput.keyboard import Controller, Key
from pynput.mouse import Button, Controller as MouseController
import bettercam
import ast

WIDTH, HEIGHT = 2560, 1440
FPS = 60
GPU_ID = 0

print(f"{pygame.K_UP} {pygame.K_DOWN} {pygame.K_LEFT} {pygame.K_RIGHT}")

ENC_PARAMS = {
    "bitrate": "20M",              # 10 Megabits per second
    "max_bitrate": "20M",
    "rc_mode": "vbr",
    "profile": "main",
    "multi_pass": "disabled",
    "bframes": 0,
    "video_full_range_flag": 0,       # 0 = Limited range (Standard for video)
    "color_primaries": 1,            # 1 = BT.709 (SDR)
    "transfer_characteristics": 1,   # 1 = BT.709 (SDR)
    "matrix_coefficients": 1         # 1 = BT.709 (SDR)
}

encoder = nvc.CreateEncoder(
    width=WIDTH,
    height=HEIGHT,
    fmt="ABGR",
    codec="hevc",
    gop=60,
    usecpuinputbuffer=True,
    fps=60,
    preset="P1",
    **ENC_PARAMS
)

codec_ctx = av.CodecContext.create('hevc', 'r')
codec_ctx.flags |= getattr(av.codec.context.Flags, 'LOW_DELAY', 0x0008)
codec_ctx.thread_type = 'SLICE'

def recv_exact(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("Socket closed")
        data += chunk
    return data

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
            # print(f"Index: {i}, Name: {dev['name']}, Host API: {dev['hostApi']}")

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
            fqueue = Queue(maxsize=1)
            def capture():
                camera = bettercam.create(device_idx=0, output_color="BGRA")
                camera.start(target_fps=60, video_mode=True)

                while not End[0]:
                    frame = camera.get_latest_frame()
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
                            conns.send(len(packets).to_bytes(4, 'big') + packets)

                except (BrokenPipeError, ConnectionResetError):
                    print("Client disconnected")
                    pass

                finally:
                    End[0] = True
                    conns.close()

            def input(conns):
                kb = Controller()
                m = MouseController()
                le = False
                mi = False
                ri = False
                shift = False
                alt = False
                tab = False
                ctrl = False
                cap = False
                cd_map = {
                    "S": Key.shift,
                    "A": Key.alt,
                    "T": Key.tab,
                    "C": Key.ctrl,
                    "CA": Key.caps_lock,
                    "F1": Key.f1,
                    "F2": Key.f2,
                    "F3": Key.f3,
                    "F4": Key.f4,
                    "F5": Key.f5,
                    "F6": Key.f6,
                    "F7": Key.f7,
                    "F8": Key.f8,
                    "F9": Key.f9,
                    "F10": Key.f10,
                    "F11": Key.f11,
                    "F12": Key.f12,
                    "A1": Key.right,
                    "A2": Key.left,
                    "A3": Key.down,
                    "A4": Key.up
                }

                try:
                    while not End[0]:
                        size = recv_exact(conns, 4)
                        if not size:
                            break
                        size = int.from_bytes(size, 'big')
                        data = recv_exact(conns, size).decode()
                        print(data)

                        split = data.split(":")
                        print(split)
                        if split[0] == "M":
                            m.position = (int(split[1]), int(split[2]))
                        elif split[0] == "KD":
                            if len(split) > 2:
                                split[1] = ':'
                            kb.press(getattr(Key, split[1]) if split[1] in Key.__members__ else split[1])
                        elif split[0] == "KU":
                            if len(split) > 2:
                                split[1] = ':'
                            kb.release(getattr(Key, split[1]) if split[1] in Key.__members__ else split[1])
                        elif split[0] == "MD":
                            keys = ast.literal_eval(split[1])
                            left, middle, right = keys
                            if left and not le:
                                le = True
                                m.press(Button.left)
                            elif middle and not mi:
                                mi = True
                                m.press(Button.middle)
                            elif right and not ri:
                                ri = True
                                m.press(Button.right)
                        elif split[0] == "MU":
                            keys = ast.literal_eval(split[1])
                            left, middle, right = keys
                            if not left and le:
                                le = False
                                m.release(Button.left)
                            elif not middle and mi:
                                mi = False
                                m.release(Button.middle)
                            elif not right and ri:
                                ri = False
                                m.release(Button.right)
                        elif split[0] == "SU":
                            m.scroll(0, 1)
                        elif split[0] == "SD":
                            m.scroll(0, -1)
                        elif split[0] == "B":
                            m.press(Button.x1)
                            m.release(Button.x1)
                        elif split[0] == "F":
                            m.press(Button.x2)
                            m.release(Button.x2)
                        elif split[0] == "CD":
                            kb.press(cd_map[split[1]])
                        elif split[0] == "CU":
                            kb.release(cd_map[split[1]])

                except Exception as e:
                    print(e)
                    End[0] = True

            threading.Thread(target=capture, daemon=True).start()
            threading.Thread(target=sending, args=(conn,), daemon=True).start()
            threading.Thread(target=input, args=(conn,), daemon=True).start()

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
        
        try:
            pygame.init()
            screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN | pygame.DOUBLEBUF | pygame.HWSURFACE | pygame.SCALED)
            pygame.display.set_caption("Remote Desktop")
            font = pygame.font.SysFont("Arial", 24)

            display_fps_start_time = time.time()
            display_fps_counter = 0
            display_fps_text = "FPS: 0"

            while not End[0]:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        End[0] = True
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_LSHIFT or event.key == pygame.K_RSHIFT:
                            string = "CD:S".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        elif event.key == pygame.K_LALT or event.key == pygame.K_RALT:
                            string = "CD:A".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        elif event.key == pygame.K_TAB:
                            string = "CD:T".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        elif event.key == pygame.K_LCTRL or event.key == pygame.K_RCTRL:
                            string = "CD:C".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        elif event.key == pygame.K_CAPSLOCK:
                            string = "CD:CA".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        elif pygame.K_F1 <= event.key <= pygame.K_F12:
                            string = f"CD:F{event.key - pygame.K_F1 + 1}".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        elif pygame.K_RIGHT <= event.key <= pygame.K_UP:
                            string = f"CD:A{event.key - pygame.K_RIGHT + 1}".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        elif event.unicode:
                            string = f"KD:{event.unicode}".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                    elif event.type == pygame.KEYUP:
                        if event.key == pygame.K_LSHIFT or event.key == pygame.K_RSHIFT:
                            string = "CU:S".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        elif event.key == pygame.K_LALT or event.key == pygame.K_RALT:
                            string = "CU:A".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        elif event.key == pygame.K_TAB:
                            string = "CU:T".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        elif event.key == pygame.K_LCTRL or event.key == pygame.K_RCTRL:
                            string = "CU:C".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        elif event.key == pygame.K_CAPSLOCK:
                            string = "CU:CA".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        elif pygame.K_F1 <= event.key <= pygame.K_F12:
                            string = f"CU:F{event.key - pygame.K_F1 + 1}".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        elif pygame.K_RIGHT <= event.key <= pygame.K_UP:
                            string = f"CU:A{event.key - pygame.K_RIGHT + 1}".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        elif event.unicode:
                            string = f"KU:{event.unicode}".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                    elif event.type == pygame.MOUSEMOTION:
                        mx, my = pygame.mouse.get_pos()
                        string = f"M:{mx}:{my}".encode()
                        clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        if event.button == 4:
                            string = "SU".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        elif event.button == 5:
                            string = "SD".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        elif event.button == 6:
                            string = "B".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        elif event.button == 7:
                            string = "F".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                        else:
                            string = f"MD:{pygame.mouse.get_pressed()}".encode()
                            clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                    elif event.type == pygame.MOUSEBUTTONUP and event.button != 4 and event.button != 5 and event.button != 6 and event.button != 7:
                        string = f"MU:{pygame.mouse.get_pressed()}".encode()
                        clientSocket.sendall(len(string).to_bytes(4, 'big') + string)
                size = recv_exact(clientSocket, 4)
                if not size:
                    break
                size = int.from_bytes(size, 'big')
                packets = recv_exact(clientSocket, size)
                raw = bytes(packets)
                if not raw: # Skip empty packets
                    continue
                try:
                    frames = av.Packet(raw)
                    allFrames = codec_ctx.decode(frames)
                    for f in allFrames:
                        img = f.to_ndarray(format='rgb24')
                        # img_upscaled = cv2.resize(img, (2560, 1440), interpolation=cv2.INTER_LINEAR)
                        surface = pygame.image.frombuffer(img.data, (f.width, f.height), 'BGR')
                        display_fps_counter += 1
                        if (time.time() - display_fps_start_time) > 1.0:
                            display_fps_text = f"FPS: {display_fps_counter}"
                            display_fps_counter = 0
                            display_fps_start_time = time.time()

                        screen.blit(surface, (0, 0)) 
                        fps_surface = font.render(display_fps_text, True, (0, 255, 0))
                        screen.blit(fps_surface, (10, 10))
                        pygame.display.update()
                except Exception as e:
                    print(f"Error: {e}")
                    continue
        finally:
            clientSocket.close()
            pygame.quit()
            print("Client closed connections")
    return

if __name__ == "__main__":
    for key in keyboard._os_keyboard.scan_code_to_vk:
        keyboard.release(key)
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
