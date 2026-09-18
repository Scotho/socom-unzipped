#pragma once
// A host 989snd: bank sounds as the IRX plays them (research/32 sections 3-4), mixed to 48 kHz stereo.
// The IOP module (ps2xIOP snd989.cpp) owns the RPC protocol and forwards the play family here through
// PS2AudioBackend; this class is plain C++ so the tests can run it without an audio device.
#include "runtime/socom2_bank.h"

#include <cstddef>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace snd989
{
    constexpr uint32_t kSampleRate = 48000;     // SPU2: pitch 0x1000 plays one sample per output frame
    // How far ahead pumpStreams() decodes each stream (audit 2026-09-17 section 2.3): four 0x800-byte chunk pairs
    // is 4 x 112 ms of a 32 kHz VPK, so a worker tick that loses a second of wall time to a slow disc still has
    // audio in hand, and the worst case a stream holds is 4 x 2 x 3584 samples (56 KB) of decoded PCM.
    constexpr size_t kStreamRingChunks = 4;
    constexpr int32_t kVolDontChange = 0x7FFFFFFF;
    constexpr int32_t kPanDontChange = -2;
    constexpr int32_t kPanReset = -1;

    // sceSdNote2Pitch / PS1Note2Pitch (research/32 section 3): the SPU pitch (0x1000 = unity at 48 kHz) of
    // `note`/`fine` against a tone's center note; a non-negative center note is a PS1 (44.1 kHz) sample.
    uint16_t note2Pitch(int8_t centerNote, int8_t centerFine, int note, int fine);

    class Mixer
    {
    public:
        Mixer();
        ~Mixer();

        // The bank's block chunk and VAG chunk, as read from the disc. Replaces an earlier bank with the handle.
        bool loadBank(uint32_t handle, const uint8_t *block, size_t blockBytes, const uint8_t *vag, size_t vagBytes);
        void unloadBank(uint32_t handle);
        size_t bankCount() const;

        // snd_PlaySoundVolPanPMPB: vol 0..0x400 (0x400 = the sound's own volume), pan -1 = the sound's own,
        // pitchMod in 1/128 semitones, pitchBend -0x8000..0x7fff. Returns the handle (5 << 24 | slot << 16 | uid), 0 if not playable.
        uint32_t play(uint32_t bank, uint32_t sound, int32_t vol, int32_t pan, int32_t pitchMod, int32_t pitchBend);
        // The same under a handle the caller chose (the IOP module's): false if not playable.
        bool playWithHandle(uint32_t handle, uint32_t bank, uint32_t sound, int32_t vol, int32_t pan, int32_t pitchMod, int32_t pitchBend);
        bool isPlaying(uint32_t handle) const;
        void stop(uint32_t handle);      // key off: the voices release
        void pause(uint32_t handle);
        void resume(uint32_t handle);
        void setVolPan(uint32_t handle, int32_t vol, int32_t pan);   // kVolDontChange / kPanDontChange leave a value
        void setMasterVolume(uint32_t group, int32_t vol);           // 0..0x400; group 16 = every group
        void stopAll();

        // snd_PlayVAGStreamByLoc: a VPK file in the disc image ("VPK " header: data size, 0x800-byte interleave, header size,
        // sample rate, channels; research/32 section 5) at `byteOffset` of `path`, read as it plays. vol 0..0x400, pan as play().
        bool playStream(uint32_t handle, const std::string &path, uint64_t byteOffset, int32_t vol, int32_t pan, uint8_t group);
        void stopAllStreams();

        // The decode-ahead half of the streams (audit 2026-09-17 section 2.3): reads and decodes the next chunk
        // pair of every live stream until its ring holds kStreamRingChunks, so render() never touches the disc.
        // Owns the file handles under its own I/O mutex and never holds the render mutex while reading. A worker
        // thread started on the first playStream calls it every 10 ms; PS2X_SND_STREAM_WORKER=0 disables that
        // thread and leaves pumpStreams() to the caller (what the tests do). Joined in the destructor.
        void pumpStreams();
        // Closes every stream's file handle and keeps its ring: the seam the "plays with the handle closed" test needs.
        void closeStreamFilesForTest();

        // The PCM stream (snd_PcmStreamOpen/Start/Position/Stop, research/32 section 7): the EE DMAs 16-bit PCM into a
        // ring the IRX plays through sceSdBlockTrans; stereo data is 512 bytes of left then 512 of right (the movie
        // audio's SShd interleave). The mixer plays the ring at `rate` from offset 0 and reports the play position in bytes.
        void pcmStreamStart(uint32_t ringBytes, uint32_t rate, uint32_t channels, int32_t vol);
        void pcmStreamWrite(uint32_t offset, const uint8_t *data, size_t bytes);
        uint32_t pcmStreamPosition() const;   // bytes into the ring, 0 when stopped
        void pcmStreamStop();
        bool pcmStreamActive() const;
        size_t activeStreams() const;

        // Mix `frames` stereo frames (interleaved L R) at kSampleRate; advances the grain sequencers.
        void render(int16_t *interleaved, size_t frames);
        size_t activeVoices() const;
        size_t activeHandlers() const;

    private:
        void startStreamWorker();   // idempotent; a Mixer that never streams never starts a thread

        struct Impl;
        std::unique_ptr<Impl> m_impl;
    };
}
