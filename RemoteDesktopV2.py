import sys
import socket
import threading
from PyQt5 import QtWidgets, QtCore
from pathlib import Path
import pyaudio
import numpy as np
import time
from queue import Queue
import PyNvVideoCodec as nvc
import pygame
import keyboard
from pynput.keyboard import Controller, Key
from pynput.mouse import Button, Controller as MouseController
import bettercam
import ast
from collections import deque
import psutil
import struct

WIDTH, HEIGHT = 2560, 1440
FPS = 60
GPU_ID = 0

print(dir(nvc.OutputColorType))

def get_clock_offset(sock, server):
    times = 10
    offset = []
    if server:
        for _ in range(times):
            print("Something")
            request = sock.recv(12, socket.MSG_WAITALL)
            if not request: 
                break
            t = time.time()
            sock.sendall(struct.pack('>d', t))
        return None
    else:
        for _ in range(times):
            t0 = time.time()
            sock.sendall(b'SYNC_REQUEST')
            response = sock.recv(8, socket.MSG_WAITALL)
            if not response: 
                break
            st = struct.unpack('>d', response)[0]

            t1 = time.time()
            rtt = t1 - t0
            off = st - (t0 + rtt / 2)

            offset.append(off)
            time.sleep(0.01)
            print(f"server={st}, client_est={t0 + rtt/2}, offset={off}, rtt={rtt}")
    return sum(offset) / len(offset)

def recv_exact(sock, size):
    # Pre-allocate the memory once
    view = memoryview(bytearray(size))
    pos = 0
    while pos < size:
        nbytes = sock.recv_into(view[pos:], size - pos)
        if not nbytes:
            raise ConnectionError("Socket closed")
        pos += nbytes
    return view.tobytes() # Or return memoryview for even more speed

# Dummy backend – replace with real logic
class RemoteStreamer(QtCore.QObject):
    status_changed = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = False
    
    def writeSettings(self, hostname, port, sc, inputString, encode):
        with open((Path(__file__).parent / "Data" / "info.txt"), "w", newline='') as info:
            info.write(f"{hostname}\r\n{port}\r\n{sc}\r\n{inputString}\r\n{encode}\r\n")

    def start(self, hostname, port, sc, inputString, encode):
        print(f"Starting stream to {hostname}:{port}")
        self.running = True
        self.status_changed.emit(f"Running → {hostname}:{port}")
        with open((Path(__file__).parent / "Data" / "info.txt"), "w", newline='') as info:
            info.write(f"{hostname}\r\n{port}\r\n{sc}\r\n{inputString}\r\n{encode}\r\n")

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

        self.encode_label = QtWidgets.QLabel("Encoding Format:")
        self.encode_box = QtWidgets.QComboBox()
        self.encode_box.addItem("H264")
        self.encode_box.addItem("HEVC")
        self.encode_box.addItem("AV1")

        self.port_label = QtWidgets.QLabel("Server Port:")
        self.port_spin = QtWidgets.QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(1)
        self.serverclient = "True"
        self.inputString = ""
        self.encode = ""
        self.input = 0
        with open((Path(__file__).parent / "Data" / "info.txt"), "r", newline='') as info:
            self.hostname_edit = QtWidgets.QLineEdit(info.readline().replace("\r\n", ""))
            self.port_spin.setValue(int(info.readline()))
            self.serverclient = info.readline().replace("\r\n", "")
            self.inputString = info.readline().replace("\r\n", "")
            self.encode = info.readline().replace("\r\n", "")
            print(self.inputString)

        self.status_lbl = QtWidgets.QLabel("Stopped")
        self.encode_box.setCurrentIndex(self.encode_box.findText(self.encode))

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
        form_layout.addRow(self.encode_label, self.encode_box)

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
        self.encode = self.encode_box.currentText()
        if checked:
            self.serverclient = "True"
            self.hostname_edit.setEnabled(False)
            self.encode_box.setEnabled(False)
        else:
            self.serverclient = "False"
            self.hostname_edit.setEnabled(True)
            self.encode_box.setEnabled(True)
        self.streamer.writeSettings(dest_ip, dest_port, self.serverclient, self.inputString, self.encode)
    
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
        self.encode = self.encode_box.currentText()
        dest_port = self.port_spin.value()
        sc = self.serverclient
        self.streamer.start(dest_hostname, dest_port, sc, self.inputString, self.encode)
        if self.serverclient == "True":
            self.client_btn.setEnabled(False)
            self.thread = threading.Thread(target=tryConnect, args=(True, socket.gethostname(), int(dest_port), int(self.input), self.encode), daemon=True)
        else:
            self.server_btn.setEnabled(False)
            self.thread = threading.Thread(target=tryConnect, args=(False, dest_hostname, int(dest_port), int(self.input), self.encode), daemon=True)
        self.thread.start()

def tryConnect(server, host, port, input, encode):
    print("Thread Started")
    End[0] = False
    if server:
        serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print(f"{host} {port}")
        serverSocket.bind(("0.0.0.0", port))
        serverSocket.listen()

        def streamToClient(conn):
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            # fqueue = Queue(maxsize=1)
            fqueue = deque(maxlen=1)
            def capture():
                p = psutil.Process()
                p.nice(psutil.HIGH_PRIORITY_CLASS)
                camera = bettercam.create(device_idx=0, output_color="BGRA")
                camera.start(target_fps=120, video_mode=True)

                while not End[0]:
                    frame = camera.get_latest_frame()
                    fqueue.append((time.time(), frame))

            def sending(conns):
                try:
                    p = psutil.Process()
                    p.nice(psutil.HIGH_PRIORITY_CLASS)
                    ENC_PARAMS = {
                        "bitrate": "40M",
                        "max_bitrate": "45M",
                        "vbv_buffer_size": "2M",
                        "rc": "vbr",                # CBR is more stable for AV1 networking
                        # "tuning_info": "low_latency",
                        "tuning_info": "high_quality",
                        "color_primaries": "bt709",
                        "transfer_characteristics": "bt709",
                        "colorspace": "bt709",
                        "video_full_range_flag": "1",
                        "repeat_seq_header": "1",   # Added for AV1
                        "bf": "0",
                        "aq_mode": "2",
                        "temporal_aq": "1",           # Prevents "crawling" noise in background
                        "intra_refresh": "1",
                        "intra_refresh_cnt": "240",   # Slower refresh = more bits for static details
                        "multipass": "fullres",
                    }

                    encoder = nvc.CreateEncoder(
                        width=WIDTH,
                        height=HEIGHT,
                        fmt="ABGR",
                        codec="av1",
                        gop=240,
                        usecpuinputbuffer=True,
                        fps=120,
                        preset="P5",
                        **ENC_PARAMS
                    )
                    fps_start_time = time.time()
                    fps_counter = 0
                    current_fps = 0
                    first = True
                    while not End[0]:
                        try:
                            t, frame = fqueue.popleft()
                        except IndexError:
                            time.sleep(0.0005)
                            continue
                        packets = encoder.Encode(frame)
                        if first and packets.startswith(b'DKIF'):
                            packets = packets[32:]
                            first = False
                        if len(packets) > 12:
                            packets = packets[12:]
                        fps_counter += 1
                        if (time.time() - fps_start_time) > 1.0:
                            current_fps = fps_counter
                            print(f"SERVER (Capture) FPS: {current_fps}")
                            fps_counter = 0
                            fps_start_time = time.time()
                        if packets:
                            payload = struct.pack('>d', t) + packets
                            conns.sendall(len(payload).to_bytes(4, 'big') + payload)

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
                        size = conns.recv(4)
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
                get_clock_offset(connId, True)
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

        offset = get_clock_offset(clientSocket, False)
        print(f"The offset: {offset}")
        
        try:
            pygame.init()
            screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN | pygame.DOUBLEBUF | pygame.HWSURFACE | pygame.SCALED, vsync=0)
            pygame.display.set_caption("Remote Desktop")
            font = pygame.font.SysFont("Arial", 24)

            nvdec = nvc.CreateDecoder(
                gpuid=0,
                codec=nvc.cudaVideoCodec.AV1,
                outputColorType=nvc.OutputColorType.RGB,
                cudacontext=0,
                cudastream=0,
                latency=nvc.DisplayDecodeLatencyType.ZERO,
                usedevicememory=False
            )

            fs = [0.0, 0.0, 0.0, 0.0]

            def inputs(cs):
                p = psutil.Process()
                p.nice(psutil.HIGH_PRIORITY_CLASS)
                while not End[0]:
                    for event in iqueue.get():
                        # event = iqueue.get()
                        if event.type == pygame.QUIT:
                            End[0] = True
                        elif event.type == pygame.KEYDOWN:
                            if event.key == pygame.K_LSHIFT or event.key == pygame.K_RSHIFT:
                                string = "CD:S".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            elif event.key == pygame.K_LALT or event.key == pygame.K_RALT:
                                string = "CD:A".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            elif event.key == pygame.K_TAB:
                                string = "CD:T".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            elif event.key == pygame.K_LCTRL or event.key == pygame.K_RCTRL:
                                string = "CD:C".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            elif event.key == pygame.K_CAPSLOCK:
                                string = "CD:CA".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            elif pygame.K_F1 <= event.key <= pygame.K_F12:
                                string = f"CD:F{event.key - pygame.K_F1 + 1}".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            elif pygame.K_RIGHT <= event.key <= pygame.K_UP:
                                string = f"CD:A{event.key - pygame.K_RIGHT + 1}".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            elif event.unicode:
                                string = f"KD:{event.unicode}".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                        elif event.type == pygame.KEYUP:
                            if event.key == pygame.K_LSHIFT or event.key == pygame.K_RSHIFT:
                                string = "CU:S".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            elif event.key == pygame.K_LALT or event.key == pygame.K_RALT:
                                string = "CU:A".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            elif event.key == pygame.K_TAB:
                                string = "CU:T".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            elif event.key == pygame.K_LCTRL or event.key == pygame.K_RCTRL:
                                string = "CU:C".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            elif event.key == pygame.K_CAPSLOCK:
                                string = "CU:CA".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            elif pygame.K_F1 <= event.key <= pygame.K_F12:
                                string = f"CU:F{event.key - pygame.K_F1 + 1}".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            elif pygame.K_RIGHT <= event.key <= pygame.K_UP:
                                string = f"CU:A{event.key - pygame.K_RIGHT + 1}".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            elif event.unicode:
                                string = f"KU:{event.unicode}".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                        elif event.type == pygame.MOUSEMOTION:
                            mx, my = pygame.mouse.get_pos()
                            string = f"M:{mx}:{my}".encode()
                            cs.sendall(len(string).to_bytes(4, 'big') + string)
                        elif event.type == pygame.MOUSEBUTTONDOWN:
                            if event.button == 4:
                                string = "SU".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            elif event.button == 5:
                                string = "SD".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            elif event.button == 6:
                                string = "B".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            elif event.button == 7:
                                string = "F".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                            else:
                                string = f"MD:{pygame.mouse.get_pressed()}".encode()
                                cs.sendall(len(string).to_bytes(4, 'big') + string)
                        elif event.type == pygame.MOUSEBUTTONUP and event.button != 4 and event.button != 5 and event.button != 6 and event.button != 7:
                            string = f"MU:{pygame.mouse.get_pressed()}".encode()
                            cs.sendall(len(string).to_bytes(4, 'big') + string)

            fqueue = deque(maxlen=100)
            equeue = deque(maxlen=20)
            iqueue = Queue(maxsize=100)
            
            def stream(cs):
                p = psutil.Process()
                p.nice(psutil.HIGH_PRIORITY_CLASS)
                try:
                    while not End[0]:
                        start = time.perf_counter()
                        size = cs.recv(4)
                        if not size:
                            break
                        size = int.from_bytes(size, 'big')
                        raw = recv_exact(cs, size)
                        t = struct.unpack('>d', raw[:8])[0]
                        raw = raw[8:]
                        if not raw: # Skip empty packets
                            continue
                        fqueue.append((t, raw))
                        fs[0] = time.perf_counter() - start
                except OSError:
                    End[0] = True

            def decoding():
                p = psutil.Process()
                p.nice(psutil.HIGH_PRIORITY_CLASS)
                while not End[0]:
                    start = time.perf_counter()
                    try:
                        t, raw = fqueue.popleft() 
                    except IndexError:
                        time.sleep(0.0005)
                        continue
                    bitstream = np.frombuffer(raw, dtype=np.uint8)
                    packet_meta = nvc.PacketData()
                    packet_meta.bsl_data = bitstream.ctypes.data
                    packet_meta.bsl = bitstream.nbytes
                    packet_meta.pts = 0 # or your actual timestamp
                    for frame in nvdec.Decode(packet_meta):
                        cpu_abgr = np.from_dlpack(frame)
                        equeue.append((t, cpu_abgr))
                    fs[1] = time.perf_counter() - start

            threading.Thread(target=inputs, args=(clientSocket,), daemon=True).start()
            threading.Thread(target=stream, args=(clientSocket,), daemon=True).start()
            threading.Thread(target=decoding, args=(), daemon=True).start()
            
            display_fps_start_time = time.perf_counter()
            display_fps_counter = 0
            display_fps_text = "FPS: 0"
            surface = None
            max_length = 60
            f0 = deque(maxlen=max_length)
            f1 = deque(maxlen=max_length)
            f2 = deque(maxlen=max_length)
            f3 = deque(maxlen=max_length)
            fps_surface = font.render("", True, (0, 255, 0))
            clock = pygame.time.Clock()
            TARGET_FPS = 62
            start = 1/TARGET_FPS
            while not End[0]:
                try:
                    clock.tick(TARGET_FPS)
                    iqueue.put(pygame.event.get())
                    # try:
                    #     while len(equeue) > 4:
                    #         equeue.popleft()
                    #     if len(equeue) >= 1:
                    #         bgr = None
                    #         while bgr is None:
                    #             try:
                    #                 t, bgr = equeue.popleft()
                    #             except IndexError:
                    #                 time.sleep(.0005)
                    #                 bgr = None
                    #                 continue
                    #     else:
                    #         time.sleep(.0005)
                    #         continue
                    # except IndexError:
                    #     time.sleep(0.0005)
                    #     continue
                    while len(equeue) > 3:
                        equeue.popleft()
                    if len(equeue) >= 1:
                        t, bgr = equeue.popleft()
                    else:
                        time.sleep(.0005)
                        continue
                    # start = time.perf_counter()
                    # print(bgr.shape)
                    h, w, _ = bgr.shape
                    # if surface is None:
                    #     print(f"{w, h}")
                    #     surface = pygame.Surface((w, h))

                    surface = pygame.image.frombuffer(bgr, (w, h), 'BGR')
                    display_fps_counter += 1
                    if (time.perf_counter() - display_fps_start_time) > 1.0:
                        display_fps_text = f"FPS: {display_fps_counter}"
                        display_fps_counter = 0
                        display_fps_start_time = time.perf_counter()

                    screen.blit(surface, (0, 0))
                    f0.append(fs[0])
                    f1.append(fs[1])
                    f2.append(fs[2])
                    f3.append(fs[3])
                    if len(f1) == f1.maxlen:
                        fps_surface = font.render(f"{display_fps_text} \r\nInternet {len(fqueue)}: {round(sum(f0) / len(f0), 5)} \r\nDecoding {len(equeue)}: {round(sum(f1) / len(f1), 5)} \r\nDisplaying: {round(sum(f2) / len(f2), 5)} \r\nRound Trip: {round(sum(f3) / len(f3), 1)}", True, (0, 255, 0), (0, 0, 0))
                        f0 = deque(maxlen=max_length)
                        f1 = deque(maxlen=max_length)
                        f2 = deque(maxlen=max_length)
                        f3 = deque(maxlen=max_length)
                    screen.blit(fps_surface, (10, 10))
                    fs[3] = (time.time()- (t - offset )) * 1000
                    pygame.display.flip()
                    fs[2] = time.perf_counter() - start
                    start = time.perf_counter()
                    # pygame.display.flip()
                    # print(f"Display frame time: {time.perf_counter() - start}")
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
