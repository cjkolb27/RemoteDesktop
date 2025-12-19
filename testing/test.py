import mss
import numpy as np
import sys
import cv2
from typing import List
import PyNvVideoCodec as nvc
import time

OUTPUT_FILE = "compressed_screen_capture.h264"
WIDTH = 1280
HEIGHT = 720
FPS = 30
BITRATE = 10_000_000
GOP = FPS
GPU_ID = 0

# enc_params = {
#     'preset': 'p1',             # p1 is the fastest (lowest latency)
#     'tuning_info': 'ultralowlatency', 
#     'codec': 'h264',
#     'fps': '30',
#     'bitrate': '10000000',
#     'gop': '30',
#     'repeat_sps_pps': '1',      # Vital for streaming!
#     'zerolatency': '1',         # Forces the encoder to output as fast as possible
#     'delay': '0',               # Minimize internal delay
#     'max_num_ref_frames': '1'   # Minimize frame dependency
# }

# enc_params = {
#     'preset': 'p4',
#     'tuning_info': 'high_quality',
#     'codec': 'h264',
#     'fps': '30',
#     'bitrate': '10000000',
#     'gop': '30'
# }
enc_params = {
    'codec': 'h264',
    'fps': '30',
    'bitrate': '10000000',
    # 'preset': 'p1',
    # 'tuning_info': 'ultralowlatency',
    'gop': '30',
    'bframes': '0',
    'zerolatency': '1',
    'repeat_sps_pps': '1'
}

# Use CreateEncoder based on your dir() list
encoder = nvc.PyNvEncoder(
    WIDTH,
    HEIGHT,
    "NV12",
    GPU_ID,
    0,
    True,
    enc_params
)

# decoder = nvc.PyNvDecoder(WIDTH, HEIGHT, nvc.Pixel_Format.NV12, nvc.cudaVideoCodec.H264, GPU_ID)
decoder = nvc.PyNvDecoder()

def display_frame(packet):
    try:
        packet_arr = np.frombuffer(packet, dtype=np.uint8)
        shape = list(packet_arr.shape)
        strides = list(packet_arr.strides)
        ptr = packet_arr.__array_interface__['data'][0]

        mem_view = nvc.CAIMemoryView(
            shape,      # arg0
            strides,    # arg1
            'B',        # arg2 (unsigned byte)
            ptr,        # arg3
            len(packet),# arg4
            True        # arg5 (read-only)
        )

        packet_data = nvc.PacketData()
        # packet_data.bsl = len(packet)
        # packet_data.bsl_data = mem_view
        
        decoded_frames = decoder.Decode(packet_data)
        print("Something")
        count = 1
        for frame in decoded_frames:
            print(count)
            count += 1
            # Get surface from the DecodedFrame object
            surf = frame.surface
            
            # Prepare NV12 buffer (H * 1.5, W)
            nv12_res = np.ndarray(shape=(HEIGHT * 3 // 2, WIDTH), dtype=np.uint8)
            
            if decoder.DownloadSingleFrame(surf, nv12_res):
                print("YES")
                bgr = cv2.cvtColor(nv12_res, cv2.COLOR_YUV2BGR_NV12)
                cv2.imshow('PC Stream', bgr)
                cv2.waitKey(1)
            else:
                print("NO")
    except Exception as e:
        print(e)

with mss.mss() as sct, open(OUTPUT_FILE, "wb") as f:
    monitor = {"top": 100, "left": 100, "width": WIDTH, "height": HEIGHT}
    
    for i in range(60): # Capture 2 seconds
        img = sct.grab(monitor)
        # MSS is BGRA. Convert to numpy
        bgra = np.array(img, dtype=np.uint8)
        
        # --- Pixel Format Conversion ---
        # Since PySurfaceConverter is missing, we use OpenCV for NV12 conversion
        # NVENC requires NV12 (YUV420 semi-planar)
        yuv = cv2.cvtColor(bgra, cv2.COLOR_BGRA2YUV_I420)
        
        # Convert I420 to NV12 (NV12 has interleaved UV)
        # This is a standard transformation for H.264 hardware encoders
        h, w = HEIGHT, WIDTH
        y = yuv[0:h, :]
        u = yuv[h:h+h//4, :].reshape(h//2, w//2)
        v = yuv[h+h//4:, :].reshape(h//2, w//2)
        uv = np.empty((h//2, w), dtype=np.uint8)
        uv[:, 0::2] = u
        uv[:, 1::2] = v
        nv12_array = np.vstack((y, uv))

        # --- Encode ---
        # PyNvEncoder.Encode in 2.0.3 can accept a numpy array 
        # representing the raw NV12 buffer
        packets = encoder.Encode(nv12_array)
        print(f"{i} Length of packets: {len(packets)}")
        
        if packets:
            print("Write")
            f.write(packets)
            display_frame(packets)

        time.sleep(1 / FPS)

print("Encode complete")


# enc_params = {
#     'gpu_id': str(GPU_ID),
#     'fps': str(FPS),
#     'bitrate': str(BITRATE),
#     'gop': str(GOP),
#     'enable_b_frames': '0'  # must be '0' or '1' as string
# }

# encoder = nvc.PyNvEncoder(
#     WIDTH,
#     HEIGHT,
#     "ARGB",        # codec string
#     GPU_ID,
#     0,             # use_opencl = 0
#     True,          # use CPU input buffer
#     enc_params
# )

# # --- 2. Screen capture ---
# with mss.mss() as sct, open(OUTPUT_FILE, "wb") as f:
#     monitor = {"top": 100, "left": 100, "width": WIDTH, "height": HEIGHT}

#     img = sct.grab(monitor)

#     # MSS returns BGRA
#     bgra = np.asarray(img, dtype=np.uint8)

#     # Convert BGRA → NV12 (CPU conversion)
#     # nvc.
#     # yuv = nvc.ConvertBGRAToNV12(
#     #     bgra,
#     #     width=WIDTH,
#     #     height=HEIGHT
#     # )

#     # --- 3. Encode ---
#     packets = encoder.Encode(bgra)

#     for p in packets:
#         f.write(p)

#     # Flush
#     for p in encoder.Flush():
#         f.write(p)

# print("Encode complete")

# WIDTH = 1280
# HEIGHT = 720
# OUTPUT_FILE = "compressed_screen_capture.h264"

# # --- 1. Setup CUDA Context and Encoder ---
# try:
#     # Initialize Cuda Stream and Context (Required for PyNvVideoCodec)
#     cuda_ctx = nvc.CudaContext() 
#     #cuda_ctx.Set { (0) } # Use GPU 0
    
#     # Configure the H.264 Encoder (Low-Latency for streaming/screencast)
#     enc_config = nvc.H264EncoderConfiguration(
#         WIDTH, 
#         HEIGHT, 
#         10000000, # 10 Mbps Bitrate
#         30,       # 30 FPS
#         30,       # GOP Size
#         nvc.NV_ENC_TUNING_INFO.NV_ENC_TUNING_INFO_LOW_LATENCY # Low-latency mode
#     )

#     # Create the Hardware Encoder
#     encoder = nvc.HwEncoder(cuda_ctx, enc_config)
    
# except Exception as e:
#     print(f"Error initializing hardware encoder: {e}")
#     sys.exit(1)

# # --- 2. Setup Memory Buffers and Converters ---
# # A CudaBuffer to hold the raw frame transferred from the CPU
# frame_buffer = nvc.CudaBuffer(cuda_ctx, WIDTH * HEIGHT * 4, nvc.GpuAllocType.DEV) 
# # A SurfaceConverter to change the color format from RGB to NV12 (NVENC's preferred format)
# converter = nvc.SurfaceConverter(cuda_ctx, nvc.Format.BGRA, nvc.Format.NV12) 

# # --- 3. Main Capture and Encode Process ---
# with mss.mss() as sct, open(OUTPUT_FILE, "wb") as out_file:
#     # Define the screen region to capture (e.g., a 1280x720 area)
#     monitor = {"top": 100, "left": 100, "width": WIDTH, "height": HEIGHT}
    
#     # Capture one frame
#     sct_img = sct.grab(monitor)
    
#     # The mss library returns a ScreenShot object, which holds raw BGRA data.
#     # We save the byte data directly.
#     raw_bytes: bytes = sct_img.rgb
    
#     # A. Transfer raw bytes from CPU to the GPU's memory buffer
#     frame_buffer.CopyFrom({ raw_bytes })
    
#     # B. Convert the color format and create a GPU Surface
#     # The Surface.Make function wraps the raw data in a format PyNvVideoCodec understands.
#     in_surf = nvc.Surface.Make(frame_buffer, WIDTH, HEIGHT, nvc.Format.BGRA, 0)
#     nv12_surf = converter.Execute(in_surf) # Execute the color conversion on the GPU
    
#     # C. Encode the Frame
#     status = encoder.Encode(nv12_surf)
    
#     # D. Retrieve and Save the Compressed H.264 Data
#     if status == nvc.HwEncoder.Status.OK:
#         # Get all encoded packets/NAL units from the encoder
#         encoded_data_packets: List[nvc.PacketData] = encoder.Get(encoded_frames=True)
        
#         for packet in encoded_data_packets:
#             # packet.GetData() returns the compressed byte stream
#             out_file.write(packet.GetData())

#     # E. Flush the encoder to get any remaining buffered frames
#     flush_packets = encoder.Flush()
#     for packet in flush_packets:
#          out_file.write(packet.GetData())

# print(f"\nSuccessfully compressed screen capture and saved to: {OUTPUT_FILE}")
