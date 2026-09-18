#pragma once
// Sprint 7 Task 9b (owner request 2026-09-18): the host microphone, captured but not yet spoken.
//
// FORMAT ASSUMPTION: 16 kHz, mono, signed 16-bit. SOCOM II's headset path is liblgaud 1.08 (LGAUD.IRX +
// HEADSETO.IRX, research/05 section 2), and the stubbed lgAudInit advertises a 0x800-byte stream buffer
// (ps2xIOP/src/modules/lgaud.cpp:21) -- 1024 frames of 16-bit mono, 64 ms at 16 kHz. Nothing in the tree has
// yet READ a rate off the module, so this is an assumption; Task 9c's spike is what settles it.
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
    size_t read(int16_t *out, size_t frames);
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

// PS2X_MIC_DEVICE / PS2X_MIC_DUMP, read once at start-up. Does nothing at all when PS2X_MIC_DEVICE is unset.
void startHostMicFromEnvironment();
void stopHostMic();
