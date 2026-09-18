// Sprint 7 Task 9b (owner request 2026-09-18): the host microphone behind PS2X_MIC_DEVICE, captured into a
// MicRing, and PS2X_MIC_DUMP=<file.wav> so a human can play back what the capture half actually heard.
//
// miniaudio.h is included WITHOUT MINIAUDIO_IMPLEMENTATION, the same rule the launcher's mic_devices.cpp
// follows: raylib's raudio.c (:178) already compiled it into libraylib, and its defines remove the decoders
// and the high-level engine but not device I/O, so capture is there.
#include "runtime/host_mic.h"

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <mutex>
#include <thread>

#include "external/miniaudio.h"

namespace
{
    // raudio.c :167 defines MA_NO_WAV, so miniaudio's encoder is not in the library: the 44-byte header is
    // written by hand, in the shape ps2_audio.cpp :358-379 writes it, with channels = 1, blockAlign = 2 and
    // byteRate = 32000 for 16 kHz mono 16-bit.
    void buildMonoWavHeader(uint8_t *p, uint32_t dataSize, uint32_t sampleRate)
    {
        auto put32 = [&](size_t at, uint32_t v) { p[at] = static_cast<uint8_t>(v); p[at + 1] = static_cast<uint8_t>(v >> 8); p[at + 2] = static_cast<uint8_t>(v >> 16); p[at + 3] = static_cast<uint8_t>(v >> 24); };
        auto put16 = [&](size_t at, uint16_t v) { p[at] = static_cast<uint8_t>(v); p[at + 1] = static_cast<uint8_t>(v >> 8); };
        std::memcpy(p, "RIFF", 4);
        put32(4, 36u + dataSize);
        std::memcpy(p + 8, "WAVEfmt ", 8);
        put32(16, 16);
        put16(20, 1);                  // PCM
        put16(22, 1);                  // mono
        put32(24, sampleRate);
        put32(28, sampleRate * 2u);    // byteRate: 32000 at 16 kHz
        put16(32, 2);                  // blockAlign
        put16(34, 16);                 // bits per sample
        std::memcpy(p + 36, "data", 4);
        put32(40, dataSize);
    }
}

struct HostMic::Impl
{
    ma_context ctx{};
    ma_device device{};
    bool ctxOpen = false;
    bool deviceOpen = false;
    MicRing ring{HostMic::kRingFrames};
};

namespace
{
    void micDataCallback(ma_device *device, void *pOutput, const void *pInput, ma_uint32 frameCount)
    {
        (void)pOutput;
        auto *ring = static_cast<MicRing *>(device->pUserData);
        if (ring == nullptr || pInput == nullptr)
            return;
        ring->write(static_cast<const int16_t *>(pInput), static_cast<size_t>(frameCount));
    }
}

HostMic::HostMic() : m_impl(new Impl()) {}

HostMic::~HostMic()
{
    stop();
}

bool HostMic::start(const std::string &deviceName)
{
    stop();
    m_error.clear();
    if (deviceName.empty())
    {
        m_error = "no device name";
        return false;
    }
    if (ma_context_init(nullptr, 0, nullptr, &m_impl->ctx) != MA_SUCCESS)
    {
        m_error = "the host audio backend would not start";
        return false;
    }
    m_impl->ctxOpen = true;
    ma_device_info *playback = nullptr;
    ma_uint32 playbackCount = 0;
    ma_device_info *capture = nullptr;
    ma_uint32 captureCount = 0;
    if (ma_context_get_devices(&m_impl->ctx, &playback, &playbackCount, &capture, &captureCount) != MA_SUCCESS)
    {
        m_error = "the capture devices could not be enumerated";
        stop();
        return false;
    }
    const ma_device_info *picked = nullptr;
    for (ma_uint32 i = 0; i < captureCount; ++i)
    {
        if (deviceName == capture[i].name)
        {
            picked = &capture[i];
            break;
        }
    }
    if (picked == nullptr)
    {
        m_error = "no capture device by that name";
        stop();
        return false;
    }
    ma_device_config cfg = ma_device_config_init(ma_device_type_capture);
    cfg.capture.pDeviceID = const_cast<ma_device_id *>(&picked->id);
    cfg.capture.format = ma_format_s16;
    cfg.capture.channels = 1;
    cfg.sampleRate = kSampleRate;
    cfg.dataCallback = &micDataCallback;
    cfg.pUserData = &m_impl->ring;
    if (ma_device_init(&m_impl->ctx, &cfg, &m_impl->device) != MA_SUCCESS)
    {
        m_error = "the device would not open 16 kHz mono 16-bit";
        stop();
        return false;
    }
    m_impl->deviceOpen = true;
    if (ma_device_start(&m_impl->device) != MA_SUCCESS)
    {
        m_error = "the device opened but would not start";
        stop();
        return false;
    }
    m_running = true;
    return true;
}

size_t HostMic::read(int16_t *out, size_t frames)
{
    if (!m_impl)
        return 0;
    return m_impl->ring.read(out, frames);
}

void HostMic::stop()
{
    if (!m_impl)
        return;
    if (m_impl->deviceOpen)
    {
        ma_device_uninit(&m_impl->device);
        m_impl->deviceOpen = false;
    }
    if (m_impl->ctxOpen)
    {
        ma_context_uninit(&m_impl->ctx);
        m_impl->ctxOpen = false;
    }
    m_running = false;
}

namespace
{
    HostMic *g_hostMic = nullptr;

    // PS2X_MIC_DUMP: while this thread runs it is the ring's only consumer -- it drains every 20 ms and
    // appends the frames to a 16 kHz mono 16-bit WAV whose two sizes are patched when it stops.
    struct MicDump
    {
        std::thread thread;
        std::atomic<bool> stop{false};
        std::FILE *file = nullptr;
        std::string path;
        size_t frames = 0;
    };
    MicDump *g_dump = nullptr;

    void startDump(HostMic &mic, const char *path)
    {
        MicDump *dump = new MicDump();
        dump->path = path;
        dump->file = std::fopen(path, "wb");
        if (dump->file == nullptr)
        {
            std::cerr << "[mic] PS2X_MIC_DUMP: cannot write " << path << std::endl;
            delete dump;
            return;
        }
        uint8_t header[44] = {};
        buildMonoWavHeader(header, 0, HostMic::kSampleRate);   // sizes patched on stop; a killed run reads by length
        std::fwrite(header, 1, 44, dump->file);
        g_dump = dump;
        dump->thread = std::thread([dump, &mic]()
        {
            std::vector<int16_t> block(1024);
            for (;;)
            {
                const bool last = dump->stop.load(std::memory_order_acquire);
                for (;;)
                {
                    const size_t got = mic.read(block.data(), block.size());
                    if (got == 0)
                        break;
                    std::fwrite(block.data(), sizeof(int16_t), got, dump->file);
                    dump->frames += got;
                }
                if (last)
                    return;
                std::this_thread::sleep_for(std::chrono::milliseconds(20));
            }
        });
        std::cout << "[mic] PS2X_MIC_DUMP -> " << path << " (16 kHz mono 16-bit)" << std::endl;
    }

    void stopDump()
    {
        if (g_dump == nullptr)
            return;
        MicDump *dump = g_dump;
        g_dump = nullptr;
        dump->stop.store(true, std::memory_order_release);
        if (dump->thread.joinable())
            dump->thread.join();
        if (dump->file != nullptr)
        {
            // The two sizes patched on stop, exactly as closeMixerStream does (ps2_audio.cpp :425-435).
            const uint32_t dataSize = static_cast<uint32_t>(dump->frames * 2u);
            uint8_t header[44] = {};
            buildMonoWavHeader(header, dataSize, HostMic::kSampleRate);
            std::fseek(dump->file, 0, SEEK_SET);
            std::fwrite(header, 1, 44, dump->file);
            std::fclose(dump->file);
            std::cout << "[mic] wrote " << dump->path << " (" << dump->frames << " frames, " << dataSize << " bytes)" << std::endl;
        }
        delete dump;
    }
}

void startHostMicFromEnvironment()
{
    const char *name = std::getenv("PS2X_MIC_DEVICE");
    if (name == nullptr || name[0] == 0)
        return;   // the default, and what the gate runs with: no capture device is opened at all
    if (g_hostMic != nullptr)
        return;
    g_hostMic = new HostMic();
    if (!g_hostMic->start(name))
    {
        // Never fatal: a missing microphone must not stop the game starting.
        std::cerr << "[mic] PS2X_MIC_DEVICE: " << g_hostMic->error() << " (" << name << ")" << std::endl;
        delete g_hostMic;
        g_hostMic = nullptr;
        return;
    }
    std::cout << "[mic] capturing \"" << name << "\" at " << HostMic::kSampleRate << " Hz mono" << std::endl;
    const char *dumpPath = std::getenv("PS2X_MIC_DUMP");
    if (dumpPath != nullptr && dumpPath[0] != 0)
        startDump(*g_hostMic, dumpPath);
}

void stopHostMic()
{
    stopDump();
    if (g_hostMic == nullptr)
        return;
    g_hostMic->stop();
    delete g_hostMic;
    g_hostMic = nullptr;
}
