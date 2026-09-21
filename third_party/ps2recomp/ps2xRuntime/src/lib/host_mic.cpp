// Sprint 7 Task 9b (owner request 2026-09-18): the host microphone behind PS2X_MIC_DEVICE, captured into a
// MicRing, and PS2X_MIC_DUMP=<file.wav> so a human can play back what the capture half actually heard.
//
// miniaudio.h is included WITHOUT MINIAUDIO_IMPLEMENTATION, the same rule the launcher's mic_devices.cpp
// follows: raylib's raudio.c (:178) already compiled it into libraylib, and its defines remove the decoders
// and the high-level engine but not device I/O, so capture is there.
#include "runtime/host_mic.h"
#include "runtime/mic_format.h"

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <mutex>
#include <thread>

#include "external/miniaudio.h"
#include "ps2x/knobs.h"

// raudio.c :167 defines MA_NO_WAV, so miniaudio's encoder is not in the library: the 44-byte header is
// written by hand, in the shape ps2_audio.cpp :358-379 writes it, with channels = 1, blockAlign = 2 and
// byteRate = 32000 for 16 kHz mono 16-bit. See host_mic.h for what dataSize == 0 means.
void hostMicWavHeader(uint8_t *p, uint32_t dataSize, uint32_t sampleRate)
{
    auto put32 = [&](size_t at, uint32_t v) { p[at] = static_cast<uint8_t>(v); p[at + 1] = static_cast<uint8_t>(v >> 8); p[at + 2] = static_cast<uint8_t>(v >> 16); p[at + 3] = static_cast<uint8_t>(v >> 24); };
    auto put16 = [&](size_t at, uint16_t v) { p[at] = static_cast<uint8_t>(v); p[at + 1] = static_cast<uint8_t>(v >> 8); };
    // dataSize 0 = "not known yet" (the dump is still being written, and only a clean stop patches the real
    // sizes in): both size fields say 0xFFFFFFFF, which every player treats as "read to the end of the file",
    // so a run that was killed still leaves a playable WAV instead of one claiming zero bytes.
    const bool unknown = dataSize == 0u;
    std::memcpy(p, "RIFF", 4);
    put32(4, unknown ? 0xFFFFFFFFu : 36u + dataSize);
    std::memcpy(p + 8, "WAVEfmt ", 8);
    put32(16, 16);
    put16(20, 1);                  // PCM
    put16(22, 1);                  // mono
    put32(24, sampleRate);
    put32(28, sampleRate * 2u);    // byteRate: 32000 at 16 kHz
    put16(32, 2);                  // blockAlign
    put16(34, 16);                 // bits per sample
    std::memcpy(p + 36, "data", 4);
    put32(40, unknown ? 0xFFFFFFFFu : dataSize);
}

// Sprint 8 Goal 3 Task 1: the reader for the header above, so PS2X_MIC_FAKE can put a known WAV where a
// capture device would be (and so the dumps this goal writes can be read back by ps2x_tests). Declared in
// runtime/mic_format.h, defined here because it touches <cstdio>, which that header stays free of.
// 16-bit PCM only; a data size of 0 or 0xFFFFFFFF means "to the end of the file" -- the two values
// hostMicWavHeader leaves behind when a run was killed before the sizes were patched (host_mic.h:94-98).
bool micWavRead(const std::string &path, std::vector<int16_t> &samples, MicFormat &format, std::string &error)
{
    samples.clear();
    error.clear();
    std::FILE *f = std::fopen(path.c_str(), "rb");
    if (f == nullptr)
    {
        error = "cannot open " + path;
        return false;
    }
    auto fail = [&](const char *why) {
        std::fclose(f);
        error = std::string(why) + " (" + path + ")";
        samples.clear();
        return false;
    };
    auto u32 = [](const uint8_t *p) {
        return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
               (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
    };
    auto u16 = [](const uint8_t *p) {
        return static_cast<uint16_t>(static_cast<uint16_t>(p[0]) | (static_cast<uint16_t>(p[1]) << 8));
    };

    uint8_t riff[12] = {};
    if (std::fread(riff, 1, 12, f) != 12u)
        return fail("shorter than a RIFF header");
    if (std::memcmp(riff, "RIFF", 4) != 0 || std::memcmp(riff + 8, "WAVE", 4) != 0)
        return fail("not a RIFF/WAVE file");

    bool haveFormat = false;
    for (;;)
    {
        uint8_t chunk[8] = {};
        const size_t got = std::fread(chunk, 1, 8, f);
        if (got != 8u)
            break;                       // a clean end of file: no more chunks
        const uint32_t size = u32(chunk + 4);
        if (std::memcmp(chunk, "fmt ", 4) == 0)
        {
            if (size < 16u)
                return fail("the fmt chunk is too short");
            uint8_t fmt[16] = {};
            if (std::fread(fmt, 1, 16, f) != 16u)
                return fail("the fmt chunk is truncated");
            if (u16(fmt) != 1u)
                return fail("not uncompressed PCM");
            if (u16(fmt + 14) != 16u)
                return fail("not 16-bit samples");
            format.channels = static_cast<uint8_t>(u16(fmt + 2));
            format.rate = u32(fmt + 4);
            format.bits = 16u;
            haveFormat = true;
            if (size > 16u && std::fseek(f, static_cast<long>(size - 16u), SEEK_CUR) != 0)
                return fail("the fmt chunk runs past the end of the file");
        }
        else if (std::memcmp(chunk, "data", 4) == 0)
        {
            if (!haveFormat)
                return fail("a data chunk before its fmt chunk");
            // 0 and 0xFFFFFFFF both mean "not known": read every byte that is actually there.
            const bool unknown = size == 0u || size == 0xFFFFFFFFu;
            // Sprint 8 review MUST FIX: `remaining` is counted in SAMPLES, because that is what the loop
            // below compares it against and decrements it by. It used to be set to the chunk size in
            // BYTES, so the loop read twice the data chunk and carried straight on into whatever chunk
            // followed -- a WAV with a trailing LIST chunk had its metadata decoded as audio. The format
            // handling above has already refused anything but 16-bit PCM, so a sample is two bytes.
            const size_t kBytesPerSample = 2u;
            size_t remaining = unknown ? static_cast<size_t>(-1)
                                       : static_cast<size_t>(size) / kBytesPerSample;
            int16_t block[1024];
            while (remaining != 0u)
            {
                const size_t want = remaining < sizeof(block) / sizeof(block[0]) ? remaining
                                                                                 : sizeof(block) / sizeof(block[0]);
                const size_t read = std::fread(block, sizeof(int16_t), want, f);
                if (read == 0u)
                    break;
                samples.insert(samples.end(), block, block + read);
                if (!unknown)
                    remaining -= read;
                if (read < want)
                    break;
            }
            break;
        }
        else if (std::fseek(f, static_cast<long>(size + (size & 1u)), SEEK_CUR) != 0)
        {
            return fail("a chunk runs past the end of the file");
        }
    }
    std::fclose(f);
    if (!haveFormat)
    {
        error = "no fmt chunk (" + path + ")";
        return false;
    }
    if (samples.empty())
    {
        error = "no samples (" + path + ")";
        return false;
    }
    if (!format.supported())
    {
        error = "unsupported format: " + std::to_string(format.rate) + " Hz, " +
                std::to_string(static_cast<unsigned>(format.channels)) + " channel(s), " +
                std::to_string(static_cast<unsigned>(format.bits)) + "-bit (" + path + ")";
        samples.clear();
        return false;
    }
    return true;
}

namespace
{
    // Sprint 8 Goal 3 Task 1 Step 6: the capture callback's two destinations. The dump used to be a SECOND
    // CONSUMER of the game's ring (host_mic.cpp:163-165 said so in its own comment), so the moment the game
    // started reading, the two split the audio between them and both files were wrong. It is a tee now: one
    // producer, two rings, one consumer each.
    struct MicSink
    {
        MicRing ring{HostMic::kRingFrames};
        MicRing dumpRing{HostMic::kRingFrames};
        std::atomic<bool> dumpOn{false};

        void push(const int16_t *frames, size_t count)
        {
            ring.write(frames, count);
            if (dumpOn.load(std::memory_order_acquire))
                dumpRing.write(frames, count);
        }
    };

    void micDataCallback(ma_device *device, void *pOutput, const void *pInput, ma_uint32 frameCount)
    {
        (void)pOutput;
        auto *sink = static_cast<MicSink *>(device->pUserData);
        if (sink == nullptr || pInput == nullptr)
            return;
        sink->push(static_cast<const int16_t *>(pInput), static_cast<size_t>(frameCount));
    }
}

struct HostMic::Impl
{
    ma_context ctx{};
    ma_device device{};
    bool ctxOpen = false;
    bool deviceOpen = false;
    MicSink sink;

    // PS2X_MIC_FAKE: the file, already at kSampleRate, and the thread that feeds it in at real time.
    std::vector<int16_t> fake;
    size_t fakeCursor = 0u;
    std::thread feeder;
    std::atomic<bool> feederStop{false};

    // PS2X_MIC_DUMP: the tee's own consumer.
    std::thread dumpThread;
    std::atomic<bool> dumpStop{false};
    std::FILE *dumpFile = nullptr;
    std::string dumpPath;
    size_t dumpFrames = 0u;
};

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
    cfg.pUserData = &m_impl->sink;
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

// PS2X_MIC_FAKE: a microphone that is a file. The WAV is read and resampled to kSampleRate ONCE, here, so the
// feeder thread does no arithmetic at all; it then writes 1024 frames every 64 ms -- the real-time pace of a
// 16 kHz capture device, and the same block the device callback delivers -- and wraps at the end.
bool HostMic::startFromFile(const std::string &wavPath)
{
    stop();
    m_error.clear();
    std::vector<int16_t> samples;
    MicFormat format{};
    if (!micWavRead(wavPath, samples, format, m_error))
        return false;

    std::vector<int16_t> atRingRate;
    if (format.rate == kSampleRate)
    {
        atRingRate = std::move(samples);
    }
    else
    {
        const double ratio = static_cast<double>(kSampleRate) / static_cast<double>(format.rate);
        atRingRate.resize(static_cast<size_t>(static_cast<double>(samples.size()) * ratio) + 2u);
        double phase = 0.0;
        const size_t written = micResampleLinear(samples.data(), samples.size(), format.rate,
                                                 atRingRate.data(), atRingRate.size(), kSampleRate, phase);
        atRingRate.resize(written);
    }
    if (atRingRate.size() < 2u)
    {
        m_error = "too few samples to loop";
        return false;
    }
    m_impl->fake = std::move(atRingRate);
    m_impl->fakeCursor = 0u;
    m_impl->feederStop.store(false, std::memory_order_release);
    m_running = true;

    Impl *impl = m_impl.get();
    m_impl->feeder = std::thread([impl]()
    {
        std::vector<int16_t> block(1024);
        while (!impl->feederStop.load(std::memory_order_acquire))
        {
            for (size_t i = 0; i < block.size(); ++i)
            {
                block[i] = impl->fake[impl->fakeCursor];
                impl->fakeCursor = (impl->fakeCursor + 1u) % impl->fake.size();
            }
            impl->sink.push(block.data(), block.size());
            std::this_thread::sleep_for(std::chrono::milliseconds(64));
        }
    });
    return true;
}

size_t HostMic::read(int16_t *out, size_t frames)
{
    if (!m_impl)
        return 0;
    return m_impl->sink.ring.read(out, frames);
}

// Only the game's ring is drained. The PS2X_MIC_DUMP tee is a SECOND ring with its own consumer and its
// own file (the tee of Task 1 Step 6): draining it here would punch a hole in the dump every time the
// game started recording, which is the one thing that file exists to rule out.
size_t HostMic::discardPending()
{
    if (!m_impl)
        return 0u;
    return m_impl->sink.ring.clear();
}

void HostMic::startDumpTee(const std::string &pattern)
{
    if (!m_impl || m_impl->sink.dumpOn.load(std::memory_order_acquire))
        return;
    const std::string wavPath = hostMicDumpPath(pattern);
    m_impl->dumpFile = std::fopen(wavPath.c_str(), "wb");
    if (m_impl->dumpFile == nullptr)
    {
        std::cerr << "[mic] PS2X_MIC_DUMP: cannot write " << wavPath << std::endl;
        return;
    }
    uint8_t header[44] = {};
    hostMicWavHeader(header, 0, HostMic::kSampleRate);   // 0 = unknown: 0xFFFFFFFF sizes, patched on a clean stop
    std::fwrite(header, 1, 44, m_impl->dumpFile);
    m_impl->dumpPath = wavPath;
    m_impl->dumpFrames = 0u;
    m_impl->dumpStop.store(false, std::memory_order_release);
    m_impl->sink.dumpOn.store(true, std::memory_order_release);

    Impl *impl = m_impl.get();
    m_impl->dumpThread = std::thread([impl]()
    {
        std::vector<int16_t> block(1024);
        for (;;)
        {
            const bool last = impl->dumpStop.load(std::memory_order_acquire);
            for (;;)
            {
                const size_t got = impl->sink.dumpRing.read(block.data(), block.size());
                if (got == 0)
                    break;
                std::fwrite(block.data(), sizeof(int16_t), got, impl->dumpFile);
                impl->dumpFrames += got;
            }
            if (last)
                return;
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
        }
    });
    std::cout << "[mic] PS2X_MIC_DUMP -> " << wavPath << " (tee off the capture callback, "
              << HostMic::kSampleRate << " Hz mono 16-bit)" << std::endl;
}

void HostMic::stopDumpTee()
{
    if (!m_impl || !m_impl->sink.dumpOn.load(std::memory_order_acquire))
        return;
    m_impl->dumpStop.store(true, std::memory_order_release);
    if (m_impl->dumpThread.joinable())
        m_impl->dumpThread.join();
    m_impl->sink.dumpOn.store(false, std::memory_order_release);
    if (m_impl->dumpFile != nullptr)
    {
        // The two sizes patched on stop, exactly as closeMixerStream does (ps2_audio.cpp :425-435).
        const uint32_t dataSize = static_cast<uint32_t>(m_impl->dumpFrames * 2u);
        uint8_t header[44] = {};
        hostMicWavHeader(header, dataSize, HostMic::kSampleRate);
        std::fseek(m_impl->dumpFile, 0, SEEK_SET);
        std::fwrite(header, 1, 44, m_impl->dumpFile);
        std::fclose(m_impl->dumpFile);
        m_impl->dumpFile = nullptr;
        std::cout << "[mic] wrote " << m_impl->dumpPath << " (" << m_impl->dumpFrames << " frames, "
                  << dataSize << " bytes)" << std::endl;
    }
}

void HostMic::stop()
{
    if (!m_impl)
        return;
    stopDumpTee();
    m_impl->feederStop.store(true, std::memory_order_release);
    if (m_impl->feeder.joinable())
        m_impl->feeder.join();
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

    // A lazily-opened PCM WAV sink for the two proof dumps. The knob is read once, on the first frame that
    // arrives, so an unset variable costs one bool test per call and never a getenv on the RPC path. The
    // rate and the channel count come from the caller, because these files carry whatever lgAudOpen asked
    // for (8000 Hz mono on the voice path, 8000 Hz stereo coming back) and not the ring's 16 kHz.
    const char kTitleToken[] = "{title}";
    struct WavSink
    {
        const char *knob;
        const char *what;
        std::mutex mutex;
        std::FILE *file = nullptr;
        std::string path;
        size_t bytes = 0u;
        uint32_t rate = 0u;
        uint8_t channels = 1u;
        bool checked = false;

        void write(const void *data, size_t byteCount, uint32_t sampleRate, uint8_t channelCount)
        {
            std::lock_guard<std::mutex> lock(mutex);
            if (!checked)
            {
                checked = true;
                const char *where = ps2x::knob(knob);
                if (where != nullptr && where[0] != 0)
                {
                    const std::string resolved = hostMicDumpPath(where);
                    file = std::fopen(resolved.c_str(), "wb");
                    if (file == nullptr)
                    {
                        std::cerr << "[mic] " << knob << ": cannot write " << resolved << std::endl;
                    }
                    else
                    {
                        path = resolved;
                        rate = sampleRate;
                        channels = channelCount == 0u ? 1u : channelCount;
                        uint8_t header[44] = {};
                        wavHeader(header, 0u, rate, channels);   // 0 = unknown until a clean close
                        std::fwrite(header, 1, 44, file);
                        std::cout << "[mic] " << knob << " -> " << path << " (" << what << ", " << rate
                                  << " Hz " << (channels == 1u ? "mono" : "stereo") << " 16-bit)" << std::endl;
                    }
                }
            }
            if (file == nullptr || data == nullptr || byteCount == 0u)
                return;
            std::fwrite(data, 1, byteCount, file);
            bytes += byteCount;
        }

        void close()
        {
            std::lock_guard<std::mutex> lock(mutex);
            checked = false;
            if (file == nullptr)
                return;
            uint8_t header[44] = {};
            wavHeader(header, static_cast<uint32_t>(bytes), rate, channels);
            std::fseek(file, 0, SEEK_SET);
            std::fwrite(header, 1, 44, file);
            std::fclose(file);
            file = nullptr;
            std::cout << "[mic] wrote " << path << " (" << bytes << " bytes of " << what << ")" << std::endl;
            bytes = 0u;
            path.clear();
        }

        // hostMicWavHeader is mono-only by construction; the playback dump is whatever the game opened.
        static void wavHeader(uint8_t *p, uint32_t dataSize, uint32_t sampleRate, uint8_t channelCount)
        {
            if (channelCount <= 1u)
            {
                hostMicWavHeader(p, dataSize, sampleRate);
                return;
            }
            hostMicWavHeader(p, dataSize, sampleRate);
            const uint32_t blockAlign = 2u * channelCount;
            const uint32_t byteRate = sampleRate * blockAlign;
            p[22] = static_cast<uint8_t>(channelCount);
            p[23] = 0u;
            p[28] = static_cast<uint8_t>(byteRate);
            p[29] = static_cast<uint8_t>(byteRate >> 8);
            p[30] = static_cast<uint8_t>(byteRate >> 16);
            p[31] = static_cast<uint8_t>(byteRate >> 24);
            p[32] = static_cast<uint8_t>(blockAlign);
            p[33] = 0u;
        }
    };

    WavSink g_gameRead{"PS2X_MIC_GAMEREAD_DUMP", "what lgaud 0x08 served the game"};
    WavSink g_playback{"PS2X_MIC_DUMP_PLAYBACK", "what lgaud 0x09 asked the headset to play"};
}

std::string hostMicDumpPath(const std::string &pattern)
{
    const std::string::size_type at = pattern.find(kTitleToken);
    if (at == std::string::npos)
        return pattern;
    const char *title = ps2x::knob("PS2X_WINDOW_TITLE");
    const std::string tag = (title == nullptr || title[0] == 0) ? std::string("A") : std::string(title);
    std::string out = pattern;
    for (std::string::size_type i = out.find(kTitleToken); i != std::string::npos;
         i = out.find(kTitleToken, i + tag.size()))
        out.replace(i, std::strlen(kTitleToken), tag);
    return out;
}

void hostMicGameReadDump(const int16_t *frames, size_t count, uint32_t rate)
{
    g_gameRead.write(frames, count * sizeof(int16_t), rate, 1u);
}

void hostMicGameReadDumpClose()
{
    g_gameRead.close();
}

void hostMicPlaybackDump(const uint8_t *pcm, size_t bytes, uint32_t rate, uint8_t channels)
{
    g_playback.write(pcm, bytes, rate, channels);
}

void hostMicPlaybackDumpClose()
{
    g_playback.close();
}

HostMic *hostMic()
{
    return g_hostMic;
}

void startHostMicFromEnvironment()
{
    const char *fake = ps2x::knob("PS2X_MIC_FAKE");
    const char *name = ps2x::knob("PS2X_MIC_DEVICE");
    const bool haveFake = fake != nullptr && fake[0] != 0;
    const bool haveDevice = name != nullptr && name[0] != 0;
    if (!haveFake && !haveDevice)
        return;   // the default, and what the gate runs with: no capture source of any kind
    if (g_hostMic != nullptr)
        return;
    g_hostMic = new HostMic();
    // R115: PS2X_MIC_FAKE beats PS2X_MIC_DEVICE when both are set -- every driven run sets the fake one
    // deliberately, and a stale device name in the environment must not silently win. The "(fake source)"
    // on the line below is how an operator who did not mean it finds out, on the first line of the log.
    const bool ok = haveFake ? g_hostMic->startFromFile(fake) : g_hostMic->start(name);
    if (!ok)
    {
        // Never fatal: a missing microphone must not stop the game starting.
        std::cerr << "[mic] " << (haveFake ? "PS2X_MIC_FAKE" : "PS2X_MIC_DEVICE") << ": " << g_hostMic->error()
                  << " (" << (haveFake ? fake : name) << ")" << std::endl;
        delete g_hostMic;
        g_hostMic = nullptr;
        return;
    }
    std::cout << "[mic] capturing \"" << (haveFake ? fake : name) << "\" at " << HostMic::kSampleRate
              << " Hz mono" << (haveFake ? " (fake source)" : "") << std::endl;
    const char *dumpPath = ps2x::knob("PS2X_MIC_DUMP");
    if (dumpPath != nullptr && dumpPath[0] != 0)
        g_hostMic->startDumpTee(dumpPath);
}

void stopHostMic()
{
    hostMicGameReadDumpClose();
    hostMicPlaybackDumpClose();
    if (g_hostMic == nullptr)
        return;
    g_hostMic->stopDumpTee();
    g_hostMic->stop();
    delete g_hostMic;
    g_hostMic = nullptr;
}
