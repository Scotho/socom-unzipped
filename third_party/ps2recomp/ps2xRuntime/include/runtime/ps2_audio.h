#ifndef PS2_AUDIO_H
#define PS2_AUDIO_H

#include "runtime/snd989_mixer.h"

#include <cstddef>
#include <cstdint>
#include <memory>
#include <mutex>
#include <unordered_map>
#include <vector>

class PS2AudioBackend
{
public:
    PS2AudioBackend();
    ~PS2AudioBackend();

    void onVagTransfer(const uint8_t *rdram, uint32_t srcAddr, uint32_t sizeBytes);
    void onVagTransferFromBuffer(const uint8_t *data, uint32_t sizeBytes, uint32_t keyAddr);
    void onSoundCommand(uint32_t sid, uint32_t rpcNum,
                        const uint8_t *sendBuf, uint32_t sendSize,
                        uint8_t *recvBuf, uint32_t recvSize);

    void play(uint32_t sampleAddr, float pitch = 1.0f, float volume = 1.0f,
              uint32_t voiceIndex = 0xFFFFFFFFu);
    void stop(uint32_t voiceId);
    void stopAll();
    void setAudioReady(bool ready);

    // 989snd (research/32): a bank's bytes from the IOP module, and the play family in host words
    // (fno 0x11/0x12 = {handle, bank, sound, vol, pan, pitchMod, pitchBend}; the rest = the command's argument words).
    void onBankLoaded(uint32_t handle, const uint8_t *block, size_t blockBytes, const uint8_t *vag, size_t vagBytes);
    void onNotify(uint32_t function, const int32_t *args, size_t count);
    size_t mixerActiveVoices() const { return m_mixer.activeVoices(); }
    bool mixerIsPlaying(uint32_t handle) const { return m_mixer.isPlaying(handle); }
    void mixerRender(int16_t *interleaved, size_t frames);

private:
    struct DecodedSample
    {
        std::vector<int16_t> pcm;
        uint32_t sampleRate = 44100;
    };

    struct Impl;
    std::unique_ptr<Impl> m_impl;
    bool m_audioReady = false;
    snd989::Mixer m_mixer;
    void openMixerStream();
    void closeMixerStream();
    uint32_t m_mostRecentSampleKey = 0;
    std::vector<DecodedSample> m_loadOrderSamples;
    std::vector<uint32_t> m_loadOrderSampleKeys;
    std::unordered_map<uint32_t, DecodedSample> m_sampleBank;
    std::mutex m_mutex;

    void playDecodedSample(uint32_t sampleKey, DecodedSample &sample, float pitch, float volume,
                          bool isBgm = false);
    void pruneFinishedSounds();
};

#endif
