import mss
import numpy as np
import cv2
import av
import PyNvVideoCodec as nvc
import threading
from queue import Queue
import time

# --- Encoder setup ---
WIDTH, HEIGHT = 2560, 1440
FPS = 30
GPU_ID = 0

ENC_PARAMS = {
    "bitrate": "40M",              # 10 Megabits per second
}

encoder = nvc.CreateEncoder(
    width=WIDTH,
    height=HEIGHT,
    fmt="ABGR",
    codec="h264",
    gop=0,
    usecpuinputbuffer=True,
    fps=FPS,
    preset="P1",
    **ENC_PARAMS
)

codec_ctx = av.CodecContext.create('h264', 'r')
codec_ctx.flags |= getattr(av.codec.context.Flags, 'LOW_DELAY', 0x0008)
codec_ctx.thread_type = 'SLICE'

fqueue = Queue(maxsize=3)
def capture():
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        fps_start_time = time.time()
        fps_counter = 0
        current_fps = 0
        while True:
            sct_img = sct.grab(monitor)
            frame = np.array(sct_img) #[:, :, :3]  # RGB
            #frame_1080 = cv2.resize(frame, (1920, 1080), interpolation=cv2.INTER_NEAREST)
            
            packets = encoder.Encode(frame)
            fps_counter += 1
            if (time.time() - fps_start_time) > 1.0:
                current_fps = fps_counter
                print(f"SERVER (Capture) FPS: {current_fps}")
                fps_counter = 0
                fps_start_time = time.time()
            if packets:
                if fqueue.full():
                    try: fqueue.get_nowait() # Always keep the queue fresh
                    except: pass
                fqueue.put(packets)

threading.Thread(target=capture, daemon=True).start()

display_fps_start_time = time.time()
display_fps_counter = 0
display_fps_text = "FPS: 0"

while True:
    packets = fqueue.get()
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

            # Draw the FPS on the image before showing it
            cv2.putText(img, display_fps_text, (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
            cv2.imshow("Decoded Video", img)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    except Exception as e:
        print(f"Error: {e}")
        continue
