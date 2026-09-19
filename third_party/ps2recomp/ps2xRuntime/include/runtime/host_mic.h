#pragma once
// Sprint 7 Task 9b (owner request 2026-09-18): the host microphone, captured but not yet spoken.
//
// CAPTURE RATE: 16 kHz, mono, signed 16-bit -- the rate the RING runs at, not the rate the game asks for.
// Sprint 8 Goal 3 RETRACTS the old "FORMAT ASSUMPTION: 16 kHz" here: Task 9c's spike is settled, and the
// game's own lgAudOpen callers build an openparam of {Mode=2, channels=1, bits=0x10, rate=0x2b11, latency=500}
// (game/analysis/socom2_game.elf.decomp.c:48336-48342, byte-identically at :86590-86594) -- 0x2b11 is 11025.
// So lgaud.cpp ALWAYS resamples this ring down to 11025 Hz; see runtime/mic_format.h for that arithmetic.
#include "runtime/mic_format.h"
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

// Single producer (the capture callback), single consumer (HostMic::read, or the PS2X_MIC_DUMP writer). Never
// overwrites unread frames: a dropped frame is counted, not smuggled in.
class MicRing
{
public:
    explicit MicRing(size_t frames) : m_buf(frames + 1u, 0), m_read(0), m_write(0), m_dropped(0) {}

    size_t write(const int16_t *src, size_t n)
    {
        const size_t cap = m_buf.size();
        size_t w = m_write.load(std::memory_order_relaxed);
        const size_t r = m_read.load(std::memory_order_acquire);
        const size_t room = (r + cap - w - 1u) % cap;
        const size_t take = n < room ? n : room;
        for (size_t i = 0; i < take; ++i)
        {
            m_buf[w] = src[i];
            w = (w + 1u) % cap;
        }
        m_write.store(w, std::memory_order_release);
        if (take < n)
            m_dropped.fetch_add(n - take, std::memory_order_relaxed);
        return take;
    }

    size_t read(int16_t *dst, size_t n)
    {
        const size_t cap = m_buf.size();
        size_t r = m_read.load(std::memory_order_relaxed);
        const size_t w = m_write.load(std::memory_order_acquire);
        const size_t have = (w + cap - r) % cap;
        const size_t take = n < have ? n : have;
        for (size_t i = 0; i < take; ++i)
        {
            dst[i] = m_buf[r];
            r = (r + 1u) % cap;
        }
        m_read.store(r, std::memory_order_release);
        return take;
    }

    size_t available() const
    {
        const size_t cap = m_buf.size();
        return (m_write.load(std::memory_order_acquire) + cap - m_read.load(std::memory_order_acquire)) % cap;
    }
    size_t dropped() const { return m_dropped.load(std::memory_order_relaxed); }

private:
    std::vector<int16_t> m_buf;
    std::atomic<size_t> m_read;
    std::atomic<size_t> m_write;
    std::atomic<size_t> m_dropped;
};

class HostMic
{
public:
    static constexpr uint32_t kSampleRate = 16000u;   // see the FORMAT ASSUMPTION above
    static constexpr size_t kRingFrames = 16000u;     // one second

    HostMic();
    ~HostMic();
    // Open the named capture device (miniaudio, 16 kHz mono s16) and start filling the ring. False, with a
    // reason in error(), when the device is not there or will not open -- never fatal: a missing microphone
    // must not stop the game starting.
    bool start(const std::string &deviceName);
    // PS2X_MIC_FAKE=<file.wav>: the capture device replaced by a WAV, looped in real time. This is what gives
    // CI, the Linux VM and the driven harness a "microphone" with a KNOWN signal, so the game-read dump can be
    // correlated against it without a human speaking (Sprint 8 Goal 3 Task 1). Resampled once, on open, to
    // kSampleRate, then fed in at real time; running() and read() are the device's, byte for byte.
    bool startFromFile(const std::string &wavPath);
    size_t read(int16_t *out, size_t frames);
    // PS2X_MIC_DUMP, Sprint 8 Goal 3 Task 1 Step 6: a TEE off the capture callback into a ring of its own, so
    // the dump and the game are not two consumers splitting one ring between them. Same knob, new mechanism.
    void startDumpTee(const std::string &wavPath);
    void stopDumpTee();
    void stop();
    bool running() const { return m_running; }
    const std::string &error() const { return m_error; }

private:
    struct Impl;
    std::unique_ptr<Impl> m_impl;
    bool m_running = false;
    std::string m_error;
};

// The 44-byte WAV header of a 16-bit mono stream, written by hand (raudio.c defines MA_NO_WAV, so miniaudio's
// encoder is not in the library). Sprint 7 review finding F6: a dump is only patched with its real sizes on a
// clean stop, so `dataSize == 0` means "not known yet" and writes 0xFFFFFFFF in both size fields -- players read
// such a file to EOF, which is what a killed run needs, instead of seeing a header that claims zero bytes.
void hostMicWavHeader(uint8_t *header44, uint32_t dataSize, uint32_t sampleRate);

// The process's capture source, or nullptr when none was started. g_hostMic was a file static with no accessor,
// which is why nothing outside host_mic.cpp could reach the ring; this is the missing link between the runtime
// and the IOP module (Sprint 8 Goal 3 Task 1 Step 7).
HostMic *hostMic();

// PS2X_MIC_GAMEREAD_DUMP=<file.wav>: every frame handed to the IOP headset module's Read (lgaud 0x08) is
// appended here, at HostMic::kSampleRate. This is the proof's second file -- correlating it against what
// PS2X_MIC_FAKE fed in is what shows the game really took the microphone out of the ring, with no human
// speaking (Sprint 8 Goal 3). The knob is read here, on the runtime side, so the IOP module stays free of
// the environment. Inert, and free, when the variable is unset. Opened lazily, closed by stopHostMic().
void hostMicGameReadDump(const int16_t *frames, size_t count);
void hostMicGameReadDumpClose();

// PS2X_MIC_FAKE / PS2X_MIC_DEVICE / PS2X_MIC_DUMP, read once at start-up. Does nothing at all when neither
// PS2X_MIC_FAKE nor PS2X_MIC_DEVICE is set -- which is the default, and what the gate runs with.
void startHostMicFromEnvironment();
void stopHostMic();
