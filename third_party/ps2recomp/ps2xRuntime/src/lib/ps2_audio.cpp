#include <cstdio>
#include <string>
#include <iostream>
#include <cstdlib>
#include "runtime/ps2_audio.h"
#include "ps2_runtime.h"
#include "runtime/ps2_memory.h"
#include "ps2_host_backend.h"
#include <cstring>
#include <vector>

namespace
{
    std::vector<uint8_t> buildWavFromPcm(const int16_t *pcm, size_t sampleCount, uint32_t sampleRate)
    {
        const uint32_t dataSize = static_cast<uint32_t>(sampleCount * 2);
        const uint32_t fileSize = 36 + dataSize;
        std::vector<uint8_t> wav(8 + fileSize);

        uint8_t *p = wav.data();
        p[0] = 'R';
        p[1] = 'I';
        p[2] = 'F';
        p[3] = 'F';
        p[4] = static_cast<uint8_t>(fileSize);
        p[5] = static_cast<uint8_t>(fileSize >> 8);
        p[6] = static_cast<uint8_t>(fileSize >> 16);
        p[7] = static_cast<uint8_t>(fileSize >> 24);
        p[8] = 'W';
        p[9] = 'A';
        p[10] = 'V';
        p[11] = 'E';
        p[12] = 'f';
        p[13] = 'm';
        p[14] = 't';
        p[15] = ' ';
        p[16] = 16;
        p[17] = 0;
        p[18] = 0;
        p[19] = 0;
        p[20] = 1;
        p[21] = 0;
        p[22] = 1;
        p[23] = 0;
        p[24] = static_cast<uint8_t>(sampleRate);
        p[25] = static_cast<uint8_t>(sampleRate >> 8);
        p[26] = static_cast<uint8_t>(sampleRate >> 16);
        p[27] = static_cast<uint8_t>(sampleRate >> 24);
        const uint32_t byteRate = sampleRate * 2;
        p[28] = static_cast<uint8_t>(byteRate);
        p[29] = static_cast<uint8_t>(byteRate >> 8);
        p[30] = static_cast<uint8_t>(byteRate >> 16);
        p[31] = static_cast<uint8_t>(byteRate >> 24);
        p[32] = 2;
        p[33] = 0;
        p[34] = 16;
        p[35] = 0;
        p[36] = 'd';
        p[37] = 'a';
        p[38] = 't';
        p[39] = 'a';
        p[40] = static_cast<uint8_t>(dataSize);
        p[41] = static_cast<uint8_t>(dataSize >> 8);
        p[42] = static_cast<uint8_t>(dataSize >> 16);
        p[43] = static_cast<uint8_t>(dataSize >> 24);
        if (pcm && dataSize)
            std::memcpy(p + 44, pcm, dataSize);
        return wav;
    }
}

namespace ps2_vag
{
    bool decode(const uint8_t *data, uint32_t sizeBytes,
                std::vector<int16_t> &outPcm, uint32_t &outSampleRate);
}

struct PS2AudioBackend::Impl
{
    // The 989snd mix: one 48 kHz stereo stream fed from the audio thread (research/32 section 4).
    AudioStream mixStream{};
    bool mixStreamOpen = false;
    FILE *dumpFile = nullptr;           // PS2X_AUDIO_DUMP=<wav>: the mix, written as it is rendered (the harness kills the process)
    size_t dumpFrames = 0;
    std::string dumpPath;
    std::mutex dumpMutex;
    struct TrackedSound
    {
        Sound snd;
        uint32_t sampleKey;
    };
    std::vector<TrackedSound> activeSounds;
};

PS2AudioBackend::PS2AudioBackend() : m_impl(std::make_unique<Impl>())
{
}

PS2AudioBackend::~PS2AudioBackend()
{
    closeMixerStream();
    if (m_impl)
        stopAll();
}

void PS2AudioBackend::onVagTransfer(const uint8_t *rdram, uint32_t srcAddr, uint32_t sizeBytes)
{
    if (!rdram || sizeBytes < 48)
        return;

    const uint32_t physAddr = srcAddr & PS2_RAM_MASK;
    if (physAddr + sizeBytes > PS2_RAM_SIZE)
        return;

    std::vector<int16_t> pcm;
    uint32_t sampleRate = 44100;
    if (!ps2_vag::decode(rdram + physAddr, sizeBytes, pcm, sampleRate))
        return;

    std::lock_guard<std::mutex> lock(m_mutex);
    DecodedSample sample;
    sample.pcm = std::move(pcm);
    sample.sampleRate = sampleRate;
    m_sampleBank[physAddr] = std::move(sample);
    m_mostRecentSampleKey = physAddr;
}

void PS2AudioBackend::onVagTransferFromBuffer(const uint8_t *data, uint32_t sizeBytes, uint32_t keyAddr)
{
    if (!data || sizeBytes < 48)
        return;

    std::vector<int16_t> pcm;
    uint32_t sampleRate = 44100;
    if (!ps2_vag::decode(data, sizeBytes, pcm, sampleRate))
        return;

    const uint32_t physAddr = keyAddr & PS2_RAM_MASK;
    std::lock_guard<std::mutex> lock(m_mutex);
    DecodedSample sample;
    sample.pcm = std::move(pcm);
    sample.sampleRate = sampleRate;
    m_sampleBank[physAddr] = sample;
    m_mostRecentSampleKey = physAddr;
    m_loadOrderSamples.push_back(std::move(sample));
    m_loadOrderSampleKeys.push_back(physAddr);
    constexpr size_t kMaxLoadOrderSamples = 32;
    if (m_loadOrderSamples.size() > kMaxLoadOrderSamples)
    {
        m_loadOrderSamples.erase(m_loadOrderSamples.begin());
        m_loadOrderSampleKeys.erase(m_loadOrderSampleKeys.begin());
    }
}

namespace
{
    constexpr uint32_t LIBSD_CMD_SET_VOICE = 0x8010u;
}

void PS2AudioBackend::onSoundCommand(uint32_t sid, uint32_t rpcNum,
                                     const uint8_t *sendBuf, uint32_t sendSize,
                                     uint8_t *recvBuf, uint32_t recvSize)
{
    if (sid != 0x80000701u)
        return;

    if ((rpcNum == LIBSD_CMD_SET_VOICE || (rpcNum & 0xFF00u) == 0x8100u) &&
        sendBuf && sendSize >= 20)
    {
        uint32_t sampleAddr = 0;
        uint32_t voiceIndex = 0xFFFFFFFFu;
        for (int vo = 4; vo >= 0 && voiceIndex == 0xFFFFFFFFu; vo -= 4)
        {
            if (vo < static_cast<int>(sendSize))
            {
                uint32_t v = 0;
                std::memcpy(&v, sendBuf + vo, sizeof(v));
                if (v < 24u)
                    voiceIndex = v;
            }
        }

        constexpr uint32_t kMinPlausibleAddr = 0x1000u;
        for (int off = 12; off <= 24 && sampleAddr == 0; off += 4)
        {
            if (sendSize >= static_cast<uint32_t>(off + 4))
            {
                uint32_t cand = 0;
                std::memcpy(&cand, sendBuf + off, sizeof(cand));
                if (cand >= kMinPlausibleAddr && (cand <= PS2_RAM_MASK || (cand & ~PS2_RAM_MASK) == 0))
                    sampleAddr = cand;
            }
        }
        if (sampleAddr == 0)
            sampleAddr = m_mostRecentSampleKey;

        float pitch = 1.0f;
        if (sendSize >= 12)
        {
            uint16_t pitchHalf = 0;
            std::memcpy(&pitchHalf, sendBuf + 8, sizeof(pitchHalf));
            if (pitchHalf != 0)
                pitch = 4096.0f / static_cast<float>(pitchHalf);
        }
        play(sampleAddr, pitch, 1.0f, voiceIndex);
    }
}

void PS2AudioBackend::play(uint32_t sampleAddr, float pitch, float volume, uint32_t voiceIndex)
{
    std::lock_guard<std::mutex> lock(m_mutex);
    DecodedSample *sampleToPlay = nullptr;
    uint32_t sampleKey = 0;

    auto it = m_sampleBank.find(sampleAddr & PS2_RAM_MASK);
    if (it != m_sampleBank.end())
    {
        sampleToPlay = &it->second;
        sampleKey = it->first;
    }
    else if (voiceIndex != 0xFFFFFFFFu &&
             voiceIndex < m_loadOrderSamples.size() &&
             voiceIndex < m_loadOrderSampleKeys.size())
    {
        sampleToPlay = &m_loadOrderSamples[voiceIndex];
        sampleKey = m_loadOrderSampleKeys[voiceIndex];
    }
    else
    {
        it = m_sampleBank.find(m_mostRecentSampleKey);
        if (it == m_sampleBank.end())
            return;
        sampleToPlay = &it->second;
        sampleKey = it->first;
    }
    if (!sampleToPlay || sampleToPlay->pcm.empty())
        return;

    const bool isBgm = (sampleToPlay->pcm.size() > static_cast<size_t>(sampleToPlay->sampleRate * 5));
    playDecodedSample(sampleKey, *sampleToPlay, pitch, volume, isBgm);
}

void PS2AudioBackend::pruneFinishedSounds()
{
#if defined(PLATFORM_VITA)
    return;
#else
    auto &sounds = m_impl->activeSounds;
    auto it = sounds.begin();
    while (it != sounds.end())
    {
        if (!IsSoundPlaying(it->snd))
        {
            UnloadSound(it->snd);
            it = sounds.erase(it);
        }
        else
        {
            ++it;
        }
    }
#endif
}

void PS2AudioBackend::playDecodedSample(uint32_t sampleKey, DecodedSample &sample, float pitch, float volume,
                                        bool isBgm)
{
#if defined(PLATFORM_VITA)
    (void)sampleKey;
    (void)sample;
    (void)pitch;
    (void)volume;
    (void)isBgm;
    return;
#else
    if (!m_audioReady || sample.pcm.empty())
        return;

    pruneFinishedSounds();

    for (const auto &t : m_impl->activeSounds)
    {
        if (t.sampleKey == sampleKey && IsSoundPlaying(t.snd))
            return;
    }

    auto &sounds = m_impl->activeSounds;
    if (isBgm)
    {
        for (auto it = sounds.begin(); it != sounds.end();)
        {
            if (IsSoundPlaying(it->snd))
            {
                StopSound(it->snd);
                UnloadSound(it->snd);
                it = sounds.erase(it);
            }
            else
                ++it;
        }
    }

    constexpr int kMaxConcurrentSounds = 4;
    while (static_cast<int>(sounds.size()) >= kMaxConcurrentSounds)
    {
        StopSound(sounds.front().snd);
        UnloadSound(sounds.front().snd);
        sounds.erase(sounds.begin());
    }

    std::vector<uint8_t> wav = buildWavFromPcm(sample.pcm.data(), sample.pcm.size(), sample.sampleRate);
    Wave wave = LoadWaveFromMemory(".wav", wav.data(), static_cast<int>(wav.size()));
    if (wave.frameCount <= 0)
        return;
    Sound snd = LoadSoundFromWave(wave);
    UnloadWave(wave);
    SetSoundPitch(snd, pitch);
    SetSoundVolume(snd, volume);
    m_impl->activeSounds.push_back({snd, sampleKey});
    PlaySound(snd);
#endif
}

void PS2AudioBackend::stop(uint32_t voiceId)
{
    (void)voiceId;
}

void PS2AudioBackend::stopAll()
{
    std::lock_guard<std::mutex> lock(m_mutex);
#if defined(PLATFORM_VITA)
    return;
#else
    for (auto &t : m_impl->activeSounds)
    {
        StopSound(t.snd);
        UnloadSound(t.snd);
    }
    m_impl->activeSounds.clear();
#endif
}

// ---- 989snd -------------------------------------------------------------------------------------

namespace
{
    PS2AudioBackend *g_mixStreamOwner = nullptr;
    constexpr size_t kDumpMaxFrames = 48000u * 600u;   // ten minutes

    void mixStreamCallback(void *bufferData, unsigned int frames)
    {
        if (g_mixStreamOwner)
            g_mixStreamOwner->mixerRender(static_cast<int16_t *>(bufferData), frames);
    }

    std::vector<uint8_t> buildStereoWav(const int16_t *pcm, size_t frames, uint32_t sampleRate)
    {
        const uint32_t dataSize = static_cast<uint32_t>(frames * 4);
        std::vector<uint8_t> wav(44 + dataSize);
        uint8_t *p = wav.data();
        auto put32 = [&](size_t at, uint32_t v) { p[at] = static_cast<uint8_t>(v); p[at + 1] = static_cast<uint8_t>(v >> 8); p[at + 2] = static_cast<uint8_t>(v >> 16); p[at + 3] = static_cast<uint8_t>(v >> 24); };
        auto put16 = [&](size_t at, uint16_t v) { p[at] = static_cast<uint8_t>(v); p[at + 1] = static_cast<uint8_t>(v >> 8); };
        std::memcpy(p, "RIFF", 4);
        put32(4, 36 + dataSize);
        std::memcpy(p + 8, "WAVEfmt ", 8);
        put32(16, 16);
        put16(20, 1);
        put16(22, 2);
        put32(24, sampleRate);
        put32(28, sampleRate * 4);
        put16(32, 4);
        put16(34, 16);
        std::memcpy(p + 36, "data", 4);
        put32(40, dataSize);
        std::memcpy(p + 44, pcm, dataSize);
        return wav;
    }
}

void PS2AudioBackend::setAudioReady(bool ready)
{
    m_audioReady = ready;
    if (ready)
        openMixerStream();
    else
        closeMixerStream();
}

void PS2AudioBackend::openMixerStream()
{
    if (!m_impl || m_impl->mixStreamOpen)
        return;
    if (const char *dump = std::getenv("PS2X_AUDIO_DUMP"))
    {
        m_impl->dumpPath = dump;
        m_impl->dumpFile = std::fopen(dump, "wb");
        if (m_impl->dumpFile)
        {
            const std::vector<uint8_t> header = buildStereoWav(nullptr, 0, snd989::kSampleRate);   // sizes patched on close; a killed run reads by file length
            std::fwrite(header.data(), 1, 44, m_impl->dumpFile);
        }
    }
    SetAudioStreamBufferSizeDefault(1024);
    m_impl->mixStream = LoadAudioStream(snd989::kSampleRate, 16, 2);
    if (!IsAudioStreamValid(m_impl->mixStream))
        return;
    g_mixStreamOwner = this;
    SetAudioStreamCallback(m_impl->mixStream, mixStreamCallback);
    PlayAudioStream(m_impl->mixStream);
    m_impl->mixStreamOpen = true;
    std::cout << "[audio] 989snd mix stream open (" << snd989::kSampleRate << " Hz stereo"
              << (m_impl->dumpPath.empty() ? "" : ", dump " + m_impl->dumpPath) << ")" << std::endl;
}

void PS2AudioBackend::closeMixerStream()
{
    if (!m_impl || !m_impl->mixStreamOpen)
        return;
    StopAudioStream(m_impl->mixStream);
    g_mixStreamOwner = nullptr;
    UnloadAudioStream(m_impl->mixStream);
    m_impl->mixStreamOpen = false;
    std::lock_guard<std::mutex> lock(m_impl->dumpMutex);
    if (m_impl->dumpFile)
    {
        const uint32_t dataSize = static_cast<uint32_t>(m_impl->dumpFrames * 4);
        const std::vector<uint8_t> header = buildStereoWav(nullptr, m_impl->dumpFrames, snd989::kSampleRate);
        std::fseek(m_impl->dumpFile, 0, SEEK_SET);
        std::fwrite(header.data(), 1, 44, m_impl->dumpFile);
        std::fclose(m_impl->dumpFile);
        m_impl->dumpFile = nullptr;
        std::cout << "[audio] wrote " << m_impl->dumpPath << " (" << m_impl->dumpFrames << " frames, " << dataSize << " bytes)" << std::endl;
    }
}

void PS2AudioBackend::onBankLoaded(uint32_t handle, const uint8_t *block, size_t blockBytes, const uint8_t *vag, size_t vagBytes)
{
    const bool ok = m_mixer.loadBank(handle, block, blockBytes, vag, vagBytes);
    std::cout << "[audio] 989snd bank " << std::hex << handle << std::dec << (ok ? " loaded" : " rejected") << " (block "
              << blockBytes << " B, vag " << vagBytes << " B)" << std::endl;
}

void PS2AudioBackend::onNotify(uint32_t function, const int32_t *args, size_t count)
{
    auto arg = [&](size_t i) { return i < count ? args[i] : 0; };
    switch (function)
    {
    case 0x11u:
    case 0x12u:   // snd_PlaySoundVolPanPMPB[NoReturn]: {handle, bank, sound, vol, pan, pitchMod, pitchBend}
        if (count >= 7)
            m_mixer.playWithHandle(static_cast<uint32_t>(arg(0)), static_cast<uint32_t>(arg(1)), static_cast<uint32_t>(arg(2)), arg(3), arg(4), arg(5), arg(6));
        break;
    case 0x13u: m_mixer.pause(static_cast<uint32_t>(arg(0))); break;
    case 0x14u: m_mixer.resume(static_cast<uint32_t>(arg(0))); break;
    case 0x15u: m_mixer.stop(static_cast<uint32_t>(arg(0))); break;
    case 0x18u: m_mixer.stopAll(); break;
    case 0x1Bu: m_mixer.setVolPan(static_cast<uint32_t>(arg(0)), arg(1), arg(2)); break;
    case 0x21u:   // snd_SetSoundParams {handle, mask, vol, pan, pm, pb}: bit0 vol, bit1 pan
    {
        const int32_t mask = arg(1);
        m_mixer.setVolPan(static_cast<uint32_t>(arg(0)), (mask & 1) ? arg(2) : snd989::kVolDontChange, (mask & 2) ? arg(3) : snd989::kPanDontChange);
        break;
    }
    case 0x22u:   // snd_AutoVol {handle, vol, ticks, how}: -4 = fade out and stop
        if (arg(1) == -4)
            m_mixer.stop(static_cast<uint32_t>(arg(0)));
        else
            m_mixer.setVolPan(static_cast<uint32_t>(arg(0)), arg(1), snd989::kPanDontChange);
        break;
    case 0x09u: m_mixer.setMasterVolume(static_cast<uint32_t>(arg(0)), arg(1)); break;
    case 0x2Cu:   // snd_PlayVAGStreamByLoc {handle, sector1, sector2, off1, vol, off2, pan, group, flags}
        if (count >= 9)
        {
            if (m_discImagePath.empty())
                m_discImagePath = PS2Runtime::getIoPaths().cdImage.string();
            const uint64_t offset = static_cast<uint64_t>(static_cast<uint32_t>(arg(1))) * 2048ull + static_cast<uint32_t>(arg(3));
            const bool ok = m_mixer.playStream(static_cast<uint32_t>(arg(0)), m_discImagePath, offset, arg(4), arg(6), static_cast<uint8_t>(arg(7)));
            std::cout << "[audio] 989snd stream " << std::hex << static_cast<uint32_t>(arg(0)) << " sector " << static_cast<uint32_t>(arg(1))
                      << std::dec << "+" << static_cast<uint32_t>(arg(3)) << (ok ? " playing" : " not a VPK or VAGp") << std::endl;
        }
        break;
    case 0x2Du: m_mixer.pause(static_cast<uint32_t>(arg(0))); break;
    case 0x2Eu: m_mixer.resume(static_cast<uint32_t>(arg(0))); break;
    case 0x2Fu: m_mixer.stop(static_cast<uint32_t>(arg(0))); break;
    case 0x34u: m_mixer.stopAllStreams(); break;
    case 0x3Eu:   // snd_PcmStreamStart {ringBytes, freq, channels, vol, buffer}
        if (count >= 4)
        {
            m_mixer.pcmStreamStart(static_cast<uint32_t>(arg(0)), static_cast<uint32_t>(arg(1)), static_cast<uint32_t>(arg(2)), arg(3));
            std::cout << "[audio] 989snd pcm stream: ring " << arg(0) << " B at " << std::hex << static_cast<uint32_t>(arg(4)) << std::dec << ", " << (arg(1) ? arg(1) : 48000) << " Hz, " << arg(2) << " ch, vol " << arg(3) << std::endl;
        }
        break;
    case 0x3Cu:
    case 0x3Du: m_mixer.pcmStreamStop(); break;
    case 0x06u: m_mixer.unloadBank(static_cast<uint32_t>(arg(0))); break;
    default:
        break;
    }
}

void PS2AudioBackend::mixerRender(int16_t *interleaved, size_t frames)
{
    m_mixer.render(interleaved, frames);
    if (m_impl && !m_impl->dumpPath.empty())
    {
        std::lock_guard<std::mutex> lock(m_impl->dumpMutex);
        if (m_impl->dumpFile && m_impl->dumpFrames < kDumpMaxFrames)
        {
            std::fwrite(interleaved, sizeof(int16_t), frames * 2, m_impl->dumpFile);
            m_impl->dumpFrames += frames;
            if ((m_impl->dumpFrames / frames) % 64 == 0)
                std::fflush(m_impl->dumpFile);
        }
    }
}

bool PS2AudioBackend::isPlaying(uint32_t handle, bool &playing) const
{
    const uint32_t type = (handle >> 24) & 0x1Fu;
    if (type != 4u && type != 5u)
        return false;
    playing = m_mixer.isPlaying(handle);
    return true;
}

void PS2AudioBackend::onPcmWrite(uint32_t offset, const uint8_t *data, size_t bytes)
{
    m_mixer.pcmStreamWrite(offset, data, bytes);
    // PS2X_AUDIO_PCM_DUMP=<file>: the first 16 MiB the EE wrote, raw with a wall-clock stamp, to check the ring's layout and fill rate offline.
    static FILE *s_dump = nullptr;
    static size_t s_dumped = 0;
    static bool s_tried = false;
    if (!s_tried)
    {
        s_tried = true;
        if (const char *path = std::getenv("PS2X_AUDIO_PCM_DUMP"))
            s_dump = std::fopen(path, "wb");
    }
    if (s_dump && s_dumped < (16u << 20))
    {
        static const auto s_epoch = std::chrono::steady_clock::now();
        const uint32_t ms = static_cast<uint32_t>(std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - s_epoch).count());
        const uint32_t hdr[3] = {offset, static_cast<uint32_t>(bytes), ms};   // offset, bytes, wall ms since the first write
        std::fwrite(hdr, sizeof(hdr), 1, s_dump);
        std::fwrite(data, 1, bytes, s_dump);
        std::fflush(s_dump);
        s_dumped += bytes;
    }
}

bool PS2AudioBackend::pcmPosition(uint32_t &position) const
{
    if (!m_mixer.pcmStreamActive())
        return false;
    position = m_mixer.pcmStreamPosition();
    return true;
}
