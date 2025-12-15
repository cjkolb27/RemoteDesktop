import mss
import numpy as np
#import cv2 # Used here only to verify/save the final bytes
import sys
from typing import List
import PyNvVideoCodec as nvc
from time import time

WIDTH = 1280
HEIGHT = 720
OUTPUT_FILE = "compressed_screen_capture.h264"

# --- 1. Setup CUDA Context and Encoder ---
try:
    # Initialize Cuda Stream and Context (Required for PyNvVideoCodec)
    cuda_ctx = nvc.CudaContext() 
    #cuda_ctx.Set { (0) } # Use GPU 0
    
    # Configure the H.264 Encoder (Low-Latency for streaming/screencast)
    enc_config = nvc.H264EncoderConfiguration(
        WIDTH, 
        HEIGHT, 
        10000000, # 10 Mbps Bitrate
        30,       # 30 FPS
        30,       # GOP Size
        nvc.NV_ENC_TUNING_INFO.NV_ENC_TUNING_INFO_LOW_LATENCY # Low-latency mode
    )

    # Create the Hardware Encoder
    encoder = nvc.HwEncoder(cuda_ctx, enc_config)
    
except Exception as e:
    print(f"Error initializing hardware encoder: {e}")
    sys.exit(1)

# --- 2. Setup Memory Buffers and Converters ---
# A CudaBuffer to hold the raw frame transferred from the CPU
frame_buffer = nvc.CudaBuffer(cuda_ctx, WIDTH * HEIGHT * 4, nvc.GpuAllocType.DEV) 
# A SurfaceConverter to change the color format from RGB to NV12 (NVENC's preferred format)
converter = nvc.SurfaceConverter(cuda_ctx, nvc.Format.BGRA, nvc.Format.NV12) 

# --- 3. Main Capture and Encode Process ---
with mss.mss() as sct, open(OUTPUT_FILE, "wb") as out_file:
    # Define the screen region to capture (e.g., a 1280x720 area)
    monitor = {"top": 100, "left": 100, "width": WIDTH, "height": HEIGHT}
    
    # Capture one frame
    sct_img = sct.grab(monitor)
    
    # The mss library returns a ScreenShot object, which holds raw BGRA data.
    # We save the byte data directly.
    raw_bytes: bytes = sct_img.rgb
    
    # A. Transfer raw bytes from CPU to the GPU's memory buffer
    frame_buffer.CopyFrom({ raw_bytes })
    
    # B. Convert the color format and create a GPU Surface
    # The Surface.Make function wraps the raw data in a format PyNvVideoCodec understands.
    in_surf = nvc.Surface.Make(frame_buffer, WIDTH, HEIGHT, nvc.Format.BGRA, 0)
    nv12_surf = converter.Execute(in_surf) # Execute the color conversion on the GPU
    
    # C. Encode the Frame
    status = encoder.Encode(nv12_surf)
    
    # D. Retrieve and Save the Compressed H.264 Data
    if status == nvc.HwEncoder.Status.OK:
        # Get all encoded packets/NAL units from the encoder
        encoded_data_packets: List[nvc.PacketData] = encoder.Get(encoded_frames=True)
        
        for packet in encoded_data_packets:
            # packet.GetData() returns the compressed byte stream
            out_file.write(packet.GetData())

    # E. Flush the encoder to get any remaining buffered frames
    flush_packets = encoder.Flush()
    for packet in flush_packets:
         out_file.write(packet.GetData())

print(f"\nSuccessfully compressed screen capture and saved to: {OUTPUT_FILE}")
