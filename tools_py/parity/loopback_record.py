"""Record what Windows sends to an output device (WASAPI loopback) into a 16-bit PCM WAV.

    python -m tools_py.parity.loopback_record <out.wav> <seconds> [device-substring]

Sprint 9 Q0 (2026-09-20): the first PCSX2 AUDIO reference this project has taken. PCSX2's own SPU2 wave logger is a
dev-build feature (the release ignores [SPU2/Debug] Log_WAVE_Output -- verified: the keys were set, PCSX2 opened SPU2,
nothing was written), so the emulator's output is captured at the endpoint instead. The default endpoint is used unless
a substring names another; the capture's rate is the endpoint's own (a 44.1 kHz Bluetooth speaker gives 44.1 kHz).
Anything else the machine plays during the capture lands in the file too -- run it on a quiet machine.
Needs pyaudiowpatch (pip; WASAPI loopback is not in stock PyAudio). Windows only.
"""
import os
import struct
import sys
import time
import wave


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[2]); return 2
    out, seconds = argv[1], float(argv[2])
    want = argv[3].lower() if len(argv) > 3 else None
    import pyaudiowpatch as pa
    p = pa.PyAudio()
    try:
        wasapi = p.get_host_api_info_by_type(pa.paWASAPI)
        default = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
        dev = None
        for lb in p.get_loopback_device_info_generator():
            if want is None and lb["name"].startswith(default["name"]):
                dev = lb; break
            if want is not None and want in lb["name"].lower():
                dev = lb; break
        if dev is None:
            print("no loopback device for", want or default["name"]); return 3
        rate = int(dev["defaultSampleRate"]); ch = int(dev["maxInputChannels"])
        print(f"recording {seconds:.0f}s from '{dev['name']}' at {rate} Hz, {ch} ch -> {out}", flush=True)
        frames = []
        # A WASAPI loopback delivers packets only while the endpoint is rendering: on a silent endpoint read()
        # blocks, and a silent stretch inside a game (a load screen) would be dropped from the file rather than
        # recorded as silence -- which would ruin exactly the gap measurement this exists for. So this process
        # renders silence to the same endpoint for the whole capture, and the loopback runs at the endpoint's rate.
        keepalive = p.open(format=pa.paInt16, channels=2, rate=rate, output=True, output_device_index=default["index"],
                           frames_per_buffer=1024)
        zeros = bytes(1024 * 2 * 2)   # one silent buffer, stereo s16
        stream = p.open(format=pa.paInt16, channels=ch, rate=rate, input=True, input_device_index=dev["index"],
                        frames_per_buffer=1024)
        # Sprint 11 audio-out: the capture's own wall clock, so tools_py/parity/cb_trace.py can lay an endpoint dip
        # (seconds into this file) against the game's callback trace (microseconds since a wall-clock t0). The
        # first packet's stamp is the file's first frame, give or take one 1024-frame read.
        start = time.time()
        print(f"start_epoch={start:.3f}", flush=True)
        # The session monitor (app_volume monitor) sees this process too: its loopback capture stream is a session
        # on the render endpoint whose meter reads the endpoint's mix. The pid lets the verdict leave it out.
        print(f"pid={os.getpid()}", flush=True)
        deadline = start + seconds
        first = True
        try:
            while time.time() < deadline:
                keepalive.write(zeros, exception_on_underflow=False)
                frames.append(stream.read(1024, exception_on_overflow=False))
                if first:
                    print(f"first_packet_epoch={time.time():.3f}", flush=True)
                    first = False
        finally:
            stream.stop_stream(); stream.close()
            keepalive.stop_stream(); keepalive.close()
        with wave.open(out, "wb") as w:
            w.setnchannels(ch); w.setsampwidth(2); w.setframerate(rate); w.writeframes(b"".join(frames))
        total = sum(len(f) for f in frames) // (2 * ch)
        print(f"wrote {total} frames ({total / rate:.1f}s) at {rate} Hz", flush=True)
        return 0
    finally:
        p.terminate()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
