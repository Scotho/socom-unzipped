#include "runtime/snd989_mixer.h"

#include "runtime/ps2_vag.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>

// The 989snd bank-sound player as OpenGOAL's re-implementation of the public API describes it and the SBlk v3
// bytes on the disc confirm (research/32 sections 1, 3): a handler walks a sound's grain list at 240 ticks a
// second; each TONE grain keys on an SPU voice whose pitch comes from sceSdNote2Pitch, whose stereo volume comes
// from MakeVolume's pan table and the group's master volume, and whose envelope is the SPU's ADSR.
namespace snd989
{
    namespace
    {
        // The disc image is over 2 GB: fseek's long is 32 bits on Windows, so every seek goes through the 64-bit call.
        int seek64(FILE *fp, uint64_t offset)
        {
#ifdef _WIN32
            return _fseeki64(fp, static_cast<long long>(offset), SEEK_SET);
#else
            return fseeko(fp, static_cast<off_t>(offset), SEEK_SET);
#endif
        }
    }
}

namespace snd989
{
    namespace
    {
        // ---- note -> pitch ---------------------------------------------------------------------------------

        // 12 semitone ratios and 128 fine-step ratios, 0x8000 = 1.0 (sceSdNote2Pitch's NotePitchTable).
        const uint32_t *notePitchTable()
        {
            static uint32_t table[140];
            static bool built = false;
            if (!built)
            {
                for (int i = 0; i < 12; ++i)
                    table[i] = static_cast<uint32_t>(std::lround(32768.0 * std::pow(2.0, i / 12.0)));
                for (int i = 0; i < 128; ++i)
                    table[12 + i] = static_cast<uint32_t>(std::lround(32768.0 * std::pow(2.0, i / 1536.0)));
                built = true;
            }
            return table;
        }

        uint16_t sceSdNote2Pitch(uint16_t centerNote, uint16_t centerFine, uint16_t note, int16_t fine)
        {
            const uint32_t *table = notePitchTable();
            int32_t _fine = fine + static_cast<uint16_t>(centerFine);
            int32_t _fine2 = _fine;
            if (_fine < 0)
                _fine2 = _fine + 127;
            _fine2 = _fine2 / 128;
            const int32_t _note = note + _fine2 - centerNote;
            int32_t val3 = _note / 6;
            if (_note < 0)
                val3--;
            const int32_t offset2 = _fine - _fine2 * 128;
            int32_t val2 = _note < 0 ? -1 : 0;
            if (val3 < 0)
                val3--;
            val2 = (val3 / 2) - val2;
            int32_t val = val2 - 2;
            int32_t offset1 = _note - (val2 * 12);
            if ((offset1 < 0) || ((offset1 == 0) && (offset2 < 0)))
            {
                offset1 = offset1 + 12;
                val = val2 - 3;
            }
            int32_t off2 = offset2;
            if (off2 < 0)
            {
                offset1 = (offset1 - 1) + _fine2;
                off2 += (_fine2 + 1) * 128;
            }
            offset1 = std::clamp(offset1, 0, 11);
            off2 = std::clamp(off2, 0, 127);
            int64_t ret = (static_cast<int64_t>(table[offset1]) * table[off2 + 12]) / 0x10000;
            if (val < 0)
                ret = (ret + (1 << (-val - 1))) >> -val;
            else if (val > 0)
                ret = ret << val;
            return static_cast<uint16_t>(std::clamp<int64_t>(ret, 0, 0xFFFF));
        }

        // ---- pan ---------------------------------------------------------------------------------------------

        struct VolPair
        {
            int16_t left, right;
        };

        // The 181-entry quarter-wave pan table (0x3fff at full): left = cos, right = sin over 0..180 degrees.
        const VolPair *panTable()
        {
            static VolPair table[181];
            static bool built = false;
            if (!built)
            {
                for (int i = 0; i <= 180; ++i)
                {
                    const double a = (i / 180.0) * (3.14159265358979323846 / 2.0);
                    table[i].left = static_cast<int16_t>(std::lround(0x3fff * std::cos(a)));
                    table[i].right = static_cast<int16_t>(std::lround(0x3fff * std::sin(a)));
                }
                built = true;
            }
            return table;
        }

        // VoiceManager::MakeVolume(127, 0, playVol, playPan, toneVol, tonePan): stereo volumes 0..0x7FFE.
        VolPair makeVolume(int32_t vol1, int32_t pan1, int32_t vol2, int32_t pan2, int32_t vol3, int32_t pan3)
        {
            int32_t vol = vol1 * 258;
            vol = (vol * vol2) / 0x7f;
            vol = (vol * vol3) / 0x7f;
            if (vol <= 0)
                return {0, 0};
            int total = pan1 + pan3 + pan2;
            while (total >= 360)
                total -= 360;
            while (total < 0)
                total += 360;
            if (total >= 270)
                total -= 270;
            else
                total += 90;
            const VolPair *table = panTable();
            VolPair out{};
            if (total < 180)
            {
                out.left = static_cast<int16_t>((table[total].left * vol) / 0x3fff);
                out.right = static_cast<int16_t>((table[total].right * vol) / 0x3fff);
            }
            else
            {
                out.right = static_cast<int16_t>((table[total - 180].left * vol) / 0x3fff);
                out.left = static_cast<int16_t>((table[total - 180].right * vol) / 0x3fff);
            }
            return out;
        }

        // ---- the SPU ADSR envelope (psx-spx) ---------------------------------------------------------------

        struct Envelope
        {
            enum Phase { Attack, Decay, Sustain, Release, Off };
            Phase phase = Off;
            int32_t level = 0;   // 0..0x7FFF
            uint16_t adsr1 = 0, adsr2 = 0;
            int32_t cycles = 0;  // samples until the next step

            void keyOn(uint16_t a1, uint16_t a2)
            {
                adsr1 = a1;
                adsr2 = a2;
                level = 0;
                phase = Attack;
                cycles = 0;
            }
            void keyOff()
            {
                if (phase != Off)
                    phase = Release;
                cycles = 0;
            }
            // One step of the phase's rate: returns the level step and the cycles it takes.
            void rate(int shift, int stepValue, bool exponential, bool decrease, int32_t &step, int32_t &cyc) const
            {
                cyc = 1 << std::max(0, shift - 11);
                step = stepValue * (1 << std::max(0, 11 - shift));   // a shift of a negative step is undefined; multiply
                if (exponential && !decrease && level > 0x6000)
                    cyc *= 4;
                if (exponential && decrease)
                    step = (step * level) / 0x8000;
            }
            // Advance by one sample; returns false once the voice is off.
            bool tick()
            {
                if (phase == Off)
                    return false;
                if (cycles > 0)
                {
                    --cycles;
                    return true;
                }
                int32_t step = 0, cyc = 1;
                switch (phase)
                {
                case Attack:
                {
                    const int shift = (adsr1 >> 10) & 0x1F;
                    const int stepValue = 7 - ((adsr1 >> 8) & 3);
                    rate(shift, stepValue, (adsr1 & 0x8000) != 0, false, step, cyc);
                    level += step;
                    if (level >= 0x7FFF)
                    {
                        level = 0x7FFF;
                        phase = Decay;
                    }
                    break;
                }
                case Decay:
                {
                    const int shift = (adsr1 >> 4) & 0x0F;
                    rate(shift, -8, true, true, step, cyc);
                    level += step;
                    const int32_t sustainLevel = ((adsr1 & 0x0F) + 1) * 0x800;
                    if (level <= sustainLevel)
                    {
                        level = std::max(level, 0);
                        phase = Sustain;
                    }
                    break;
                }
                case Sustain:
                {
                    const int shift = (adsr2 >> 8) & 0x1F;
                    const bool decrease = (adsr2 & 0x4000) != 0;
                    const int stepValue = decrease ? -(8 - ((adsr2 >> 6) & 3)) : 7 - ((adsr2 >> 6) & 3);
                    rate(shift, stepValue, (adsr2 & 0x8000) != 0, decrease, step, cyc);
                    level += step;
                    level = std::clamp(level, 0, 0x7FFF);
                    break;
                }
                case Release:
                {
                    const int shift = adsr2 & 0x1F;
                    rate(shift, -8, (adsr2 & 0x20) != 0, true, step, cyc);
                    level += step;
                    if (level <= 0)
                    {
                        level = 0;
                        phase = Off;
                    }
                    break;
                }
                default:
                    break;
                }
                cycles = std::max(0, cyc - 1);
                return phase != Off;
            }
        };

        // ---- data --------------------------------------------------------------------------------------------

        struct DecodedSample
        {
            std::vector<int16_t> pcm;
            bool loops = false;
            size_t loopStart = 0;
        };

        struct BankData
        {
            socom2_bank::Bank bank;
            std::vector<uint8_t> vag;
            std::map<uint32_t, DecodedSample> samples;   // by VAG offset

            const DecodedSample *sample(uint32_t offset)
            {
                auto it = samples.find(offset);
                if (it != samples.end())
                    return &it->second;
                if (offset >= vag.size())
                    return nullptr;
                ps2_vag::BlockRun run;
                if (!ps2_vag::decodeBlocks(vag.data() + offset, vag.size() - offset, run))
                    return nullptr;
                DecodedSample s;
                s.pcm = std::move(run.pcm);
                s.loops = run.loops;
                s.loopStart = run.loopStartSample;
                return &(samples[offset] = std::move(s));
            }
        };

        struct Voice
        {
            uint32_t handler = 0;
            uint32_t bank = 0;
            const DecodedSample *sample = nullptr;
            double pos = 0.0;
            double step = 1.0;
            socom2_bank::Tone tone;
            uint8_t group = 0;
            VolPair base{};   // MakeVolume result before the group modifier
            Envelope env;
            bool paused = false;
        };

        struct Handler
        {
            uint32_t handle = 0;
            uint32_t bank = 0;
            uint32_t sound = 0;
            int32_t curVolume = 0;   // 0..127
            int32_t curPan = 0;
            int32_t curPb = 0;
            int32_t curPm = 0;
            uint8_t group = 0;
            int32_t countdown = 0;
            size_t nextGrain = 0;
            bool done = false;
            bool paused = false;
            uint8_t note = 60, fine = 0;
        };

        // A VPK stream (research/32 section 5): interleaved 0x800-byte ADPCM chunks per channel, read from the disc
        // image as it plays and resampled from the file's rate to kSampleRate.
        struct Stream
        {
            uint32_t handle = 0;
            FILE *file = nullptr;
            uint64_t dataStart = 0;      // file offset of the first chunk
            uint32_t dataSize = 0;       // bytes of chunk data
            uint32_t interleave = 0x800;
            uint32_t rate = 32000;
            uint32_t channels = 1;
            uint32_t consumed = 0;       // chunk bytes read so far
            bool ended = false;          // no more chunks
            bool paused = false;
            bool done = false;           // played out (or stopped)
            uint8_t group = 0;
            VolPair base{};
            std::vector<std::vector<int16_t>> pcm;   // per channel: the current chunk's samples
            std::vector<int16_t> s1, s2;             // per channel ADPCM history
            double pos = 0.0;                        // sample position inside the current chunk
            double step = 1.0;                       // file rate / output rate

            bool readChunkPair()
            {
                if (ended || !file)
                    return false;
                const size_t chunkBytes = static_cast<size_t>(interleave);
                std::vector<uint8_t> raw(chunkBytes);
                bool any = false;
                for (uint32_t ch = 0; ch < channels; ++ch)
                {
                    pcm[ch].clear();
                    if (consumed >= dataSize)
                    {
                        ended = true;
                        continue;
                    }
                    const size_t want = std::min(chunkBytes, static_cast<size_t>(dataSize - consumed));
                    if (seek64(file, dataStart + consumed) != 0)
                    {
                        ended = true;
                        continue;
                    }
                    const size_t got = std::fread(raw.data(), 1, want, file);
                    consumed += static_cast<uint32_t>(want);
                    if (got < 16)
                    {
                        ended = true;
                        continue;
                    }
                    any = true;
                    int16_t h1 = s1[ch], h2 = s2[ch];
                    for (size_t off = 0; off + 16 <= got; off += 16)
                    {
                        const uint8_t *block = raw.data() + off;
                        uint8_t shift = block[0] & 0x0F;
                        if (shift > 12)
                            shift = 9;
                        uint8_t filter = (block[0] >> 4) & 0x07;
                        if (filter > 4)
                            filter = 0;
                        for (int i = 0; i < 28; ++i)
                        {
                            const uint8_t byte = block[2 + i / 2];
                            const uint8_t nibble = (i & 1) ? (byte >> 4) : (byte & 0x0F);
                            const int8_t raw4 = static_cast<int8_t>((nibble & 8) ? (nibble | 0xF0) : nibble);
                            const int32_t shifted = raw4 << (12 - shift);
                            const int32_t old = h1, older = h2;
                            int32_t filtered;
                            switch (filter)
                            {
                            case 1: filtered = shifted + (60 * old + 32) / 64; break;
                            case 2: filtered = shifted + (115 * old - 52 * older + 32) / 64; break;
                            case 3: filtered = shifted + (98 * old - 55 * older + 32) / 64; break;
                            case 4: filtered = shifted + (122 * old - 60 * older + 32) / 64; break;
                            default: filtered = shifted; break;
                            }
                            const int16_t v = static_cast<int16_t>(std::clamp(filtered, -32768, 32767));
                            h2 = h1;
                            h1 = v;
                            pcm[ch].push_back(v);
                        }
                        if (block[1] & 0x01)
                        {
                            ended = true;   // the end flag inside the data: the last chunk
                            break;
                        }
                    }
                    s1[ch] = h1;
                    s2[ch] = h2;
                }
                pos = 0.0;
                return any;
            }
        };

        constexpr double kTickHz = 240.0;
    }

    uint16_t note2Pitch(int8_t centerNote, int8_t centerFine, int note, int fine)
    {
        bool ps1 = false;
        int center = centerNote;
        if (center >= 0)
            ps1 = true;
        else
            center = -center;
        uint16_t pitch = sceSdNote2Pitch(static_cast<uint16_t>(center), static_cast<uint16_t>(static_cast<uint8_t>(centerFine)),
                                         static_cast<uint16_t>(note), static_cast<int16_t>(fine));
        if (ps1)
            pitch = static_cast<uint16_t>(44100u * pitch / 48000u);
        return pitch;
    }

    struct Mixer::Impl
    {
        mutable std::mutex mutex;
        std::unordered_map<uint32_t, BankData> banks;
        std::vector<Voice> voices;
        std::vector<Handler> handlers;
        std::vector<Stream> streams;
        // The PCM ring (research/32 section 7): 16-bit PCM the EE DMAs in, played from offset 0 at `rate`;
        // stereo is 512 bytes of left then 512 of right (the movie audio's SShd interleave 0x200; a first cut read the
        // capture as sample-interleaved and was wrong -- research/32 section 7).
        struct PcmRing
        {
            bool active = false;
            std::vector<uint8_t> bytes;
            uint32_t rate = 48000;
            uint32_t channels = 2;
            int32_t gain = 0;        // per-channel volume 0..0x3fff after the SPU's >> 1
            double pos = 0.0;        // frames into the ring
            uint32_t frames() const { return channels == 0 || bytes.empty() ? 0u : static_cast<uint32_t>(bytes.size() / (2u * channels)); }
            int16_t sample(uint32_t frame, uint32_t channel) const
            {
                size_t at;
                // 512-byte blocks, L then R (the SShd interleave 0x200 of the movie audio, research/32 section 7):
                // frame f sits in block pair f / 256 at sample f % 256.
                if (channels >= 2)
                    at = static_cast<size_t>(frame / 256u) * 1024u + channel * 512u + static_cast<size_t>(frame % 256u) * 2u;
                else
                    at = static_cast<size_t>(frame) * 2u;
                if (at + 1 >= bytes.size())
                    return 0;
                return static_cast<int16_t>(bytes[at] | (bytes[at + 1] << 8));
            }
        } pcm;
        int32_t masterVol[17] = {};
        uint32_t nextUid = 1;
        uint32_t nextSlot = 0;
        double tickAccumulator = 0.0;

        Impl()
        {
            for (int32_t &v : masterVol)
                v = 0x400;
        }

        Handler *find(uint32_t handle)
        {
            for (Handler &h : handlers)
                if (h.handle == handle)
                    return &h;
            return nullptr;
        }

        int32_t groupModifier(uint8_t group) const
        {
            const int32_t g = std::min<int>(group, 15);
            return masterVol[g] * masterVol[16] / 0x400;   // both 0..0x400
        }

        void applyVoiceVolume(Voice &v, int32_t &left, int32_t &right) const
        {
            const int32_t modifier = groupModifier(v.group);
            // The SPU voice takes (left >> 1, right >> 1): full volume is half of full scale (StartTone, research/32 section 3).
            left = ((v.base.left * modifier) / 0x400) >> 1;
            right = ((v.base.right * modifier) / 0x400) >> 1;
        }

        void startTone(Handler &h, BankData &bd, const socom2_bank::Tone &tone)
        {
            const DecodedSample *sample = bd.sample(tone.sampleOffset);
            if (!sample || sample->pcm.empty())
                return;
            Voice v;
            v.handler = h.handle;
            v.bank = h.bank;
            v.sample = sample;
            v.tone = tone;
            v.group = h.group;
            // PitchBend(tone, pb, pm, note, fine) then PS1Note2Pitch
            int32_t v9 = (h.note << 7) + h.fine + h.curPm;
            int32_t v7;
            if (h.curPb >= 0)
                v7 = tone.pbHigh * (h.curPb << 7) / 0x7fff + v9;
            else
                v7 = tone.pbLow * (h.curPb << 7) / 0x8000 + v9;
            const int note = v7 / 128;
            const int fine = v7 % 128;
            const uint16_t pitch = note2Pitch(tone.centerNote, tone.centerFine, note, fine);
            v.step = pitch / 4096.0;
            v.base = makeVolume(127, 0, h.curVolume, h.curPan, tone.vol, tone.pan);
            v.env.keyOn(tone.adsr1, tone.adsr2);
            voices.push_back(v);
        }

        void keyOffHandler(uint32_t handle)
        {
            for (Voice &v : voices)
                if (v.handler == handle)
                    v.env.keyOff();
        }

        void updateHandlerVoices(const Handler &h)
        {
            for (Voice &v : voices)
                if (v.handler == h.handle)
                    v.base = makeVolume(127, 0, h.curVolume, h.curPan, v.tone.vol, v.tone.pan);
        }

        // One grain; returns the delay to add to the next grain's countdown.
        int32_t doGrain(Handler &h)
        {
            auto bit = banks.find(h.bank);
            if (bit == banks.end())
            {
                h.done = true;
                return 0;
            }
            BankData &bd = bit->second;
            const socom2_bank::Sound &snd = bd.bank.sounds[h.sound];
            if (h.nextGrain >= snd.grains.size())
            {
                h.done = true;
                return 0;
            }
            const socom2_bank::Grain &g = snd.grains[h.nextGrain];
            int32_t ret = 0;
            switch (g.type)
            {
            case socom2_bank::kTone:
            case socom2_bank::kTone2:
            {
                socom2_bank::Tone tone;
                if (bd.bank.tone(g, tone))
                    startTone(h, bd, tone);
                break;
            }
            case socom2_bank::kRandDelay:
            {
                const int32_t amount = static_cast<int32_t>(g.arg);
                if (amount > 0)
                    ret = std::rand() % amount;
                break;
            }
            case socom2_bank::kRandPb:
            {
                const int32_t pb = static_cast<int8_t>(g.arg & 0xFF);
                const int32_t rnd = std::rand();
                h.curPb = pb * ((0xffff * (rnd % 0x7fff)) / 0x7fff - 0x8000) / 100;
                break;
            }
            case socom2_bank::kPb:
            {
                const int32_t pb = static_cast<int8_t>(g.arg & 0xFF);
                h.curPb = pb >= 0 ? 0x7fff * pb / 127 : -0x8000 * pb / -128;
                break;
            }
            case socom2_bank::kAddPb:
            {
                const int32_t pb = static_cast<int8_t>(g.arg & 0xFF);
                h.curPb = std::clamp(h.curPb + 0x7fff * pb / 127, -32768, 32767);
                break;
            }
            case socom2_bank::kLoopEnd:
            {
                for (size_t i = h.nextGrain; i-- > 0;)
                    if (snd.grains[i].type == socom2_bank::kLoopStart)
                    {
                        h.nextGrain = i;   // ++ below lands on the grain after LOOP_START
                        break;
                    }
                break;
            }
            case socom2_bank::kLoopContinue:
            {
                for (size_t i = h.nextGrain + 1; i < snd.grains.size(); ++i)
                    if (snd.grains[i].type == socom2_bank::kLoopEnd)
                    {
                        h.nextGrain = i;
                        break;
                    }
                break;
            }
            case socom2_bank::kStop:
                h.done = true;
                break;
            case socom2_bank::kKeyOffVoices:
                keyOffHandler(h.handle);
                break;
            case socom2_bank::kKillVoices:
                for (Voice &v : voices)
                    if (v.handler == h.handle)
                        v.env.phase = Envelope::Off;
                break;
            default:
                break;   // LFO, registers, markers, children, plugins: not modelled (research/32 section 4)
            }
            ++h.nextGrain;
            if (h.nextGrain >= snd.grains.size())
                h.done = true;
            return ret;
        }

        void runGrains(Handler &h)
        {
            auto bit = banks.find(h.bank);
            if (bit == banks.end())
            {
                h.done = true;
                return;
            }
            const socom2_bank::Sound &snd = bit->second.bank.sounds[h.sound];
            int guard = 0;
            while (h.countdown <= 0 && !h.done && guard++ < 256)
            {
                const int32_t ret = doGrain(h);
                if (!h.done && h.nextGrain < snd.grains.size())
                    h.countdown = snd.grains[h.nextGrain].delay + ret;
            }
        }

        void tick()
        {
            for (Handler &h : handlers)
            {
                if (h.done || h.paused)
                    continue;
                --h.countdown;
                runGrains(h);
            }
        }

        Stream *findStream(uint32_t handle)
        {
            for (Stream &st : streams)
                if (st.handle == handle)
                    return &st;
            return nullptr;
        }

        void closeStream(Stream &st)
        {
            if (st.file)
                std::fclose(st.file);
            st.file = nullptr;
            st.done = true;
        }

        bool handlerAlive(const Handler &h) const
        {
            if (!h.done)
                return true;
            for (const Voice &v : voices)
                if (v.handler == h.handle && v.env.phase != Envelope::Off)
                    return true;
            return false;
        }

        void reap()
        {
            voices.erase(std::remove_if(voices.begin(), voices.end(), [](const Voice &v) { return v.env.phase == Envelope::Off; }), voices.end());
            handlers.erase(std::remove_if(handlers.begin(), handlers.end(), [this](const Handler &h) { return !handlerAlive(h); }), handlers.end());
            for (Stream &st : streams)
                if (st.done && st.file)
                    closeStream(st);
            streams.erase(std::remove_if(streams.begin(), streams.end(), [](const Stream &st) { return st.done; }), streams.end());
        }
    };

    Mixer::Mixer() : m_impl(std::make_unique<Impl>()) {}
    Mixer::~Mixer()
    {
        for (Stream &st : m_impl->streams)
            m_impl->closeStream(st);
    }

    bool Mixer::loadBank(uint32_t handle, const uint8_t *block, size_t blockBytes, const uint8_t *vag, size_t vagBytes)
    {
        BankData bd;
        if (!socom2_bank::parse(block, blockBytes, bd.bank))
            return false;
        bd.vag.assign(vag, vag + vagBytes);
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        {
            auto it = m_impl->banks.find(handle);
            if (it != m_impl->banks.end())
            {
                m_impl->voices.erase(std::remove_if(m_impl->voices.begin(), m_impl->voices.end(), [&](const Voice &v) { return v.bank == handle; }), m_impl->voices.end());
                m_impl->handlers.erase(std::remove_if(m_impl->handlers.begin(), m_impl->handlers.end(), [&](const Handler &h) { return h.bank == handle; }), m_impl->handlers.end());
                m_impl->banks.erase(it);
            }
        }
        m_impl->banks[handle] = std::move(bd);
        return true;
    }

    void Mixer::unloadBank(uint32_t handle)
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        m_impl->voices.erase(std::remove_if(m_impl->voices.begin(), m_impl->voices.end(), [&](const Voice &v) { return v.bank == handle; }), m_impl->voices.end());
        m_impl->handlers.erase(std::remove_if(m_impl->handlers.begin(), m_impl->handlers.end(), [&](const Handler &h) { return h.bank == handle; }), m_impl->handlers.end());
        m_impl->banks.erase(handle);
    }

    size_t Mixer::bankCount() const
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        return m_impl->banks.size();
    }

    uint32_t Mixer::play(uint32_t bank, uint32_t sound, int32_t vol, int32_t pan, int32_t pitchMod, int32_t pitchBend)
    {
        uint32_t handle;
        {
            std::lock_guard<std::mutex> lock(m_impl->mutex);
            uint32_t uid = m_impl->nextUid++ & 0xFFFFu;
            if (uid == 0u)
                uid = m_impl->nextUid++ & 0xFFFFu;
            const uint32_t slot = m_impl->nextSlot++ & 0xFFu;
            handle = (5u << 24) | (slot << 16) | uid;
        }
        return playWithHandle(handle, bank, sound, vol, pan, pitchMod, pitchBend) ? handle : 0u;
    }

    bool Mixer::playWithHandle(uint32_t handle, uint32_t bank, uint32_t sound, int32_t vol, int32_t pan, int32_t pitchMod, int32_t pitchBend)
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        auto it = m_impl->banks.find(bank);
        if (it == m_impl->banks.end() || handle == 0u)
            return false;
        BankData &bd = it->second;
        if (sound >= bd.bank.sounds.size() || bd.bank.sounds[sound].grains.empty())
            return false;
        const socom2_bank::Sound &snd = bd.bank.sounds[sound];
        // A re-used handle (the module's slot came round) ends the earlier sound under it.
        for (Handler &old : m_impl->handlers)
            if (old.handle == handle)
            {
                old.done = true;
                m_impl->keyOffHandler(handle);
            }
        Handler h;
        h.handle = handle;
        h.bank = bank;
        h.sound = sound;
        h.group = static_cast<uint8_t>(snd.volGroup);
        int32_t playVol = (snd.vol * std::clamp(vol, 0, 0x400)) >> 10;
        if (playVol >= 128)
            playVol = 127;
        h.curVolume = std::max(0, playVol);
        h.curPan = (pan == kPanReset || pan == kPanDontChange) ? snd.pan : pan;
        h.curPm = pitchMod;
        h.curPb = pitchBend;
        h.countdown = snd.grains[0].delay;
        m_impl->handlers.push_back(h);
        m_impl->runGrains(m_impl->handlers.back());
        return true;
    }

    bool Mixer::isPlaying(uint32_t handle) const
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        for (const Stream &st : m_impl->streams)
            if (st.handle == handle)
                return !st.done;
        for (const Handler &h : m_impl->handlers)
            if (h.handle == handle)
                return m_impl->handlerAlive(h);
        return false;
    }

    void Mixer::stop(uint32_t handle)
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        if (Stream *st = m_impl->findStream(handle))
        {
            m_impl->closeStream(*st);
            return;
        }
        if (Handler *h = m_impl->find(handle))
        {
            h->done = true;
            m_impl->keyOffHandler(handle);
        }
    }

    void Mixer::pause(uint32_t handle)
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        if (Stream *st = m_impl->findStream(handle))
            st->paused = true;
        if (Handler *h = m_impl->find(handle))
            h->paused = true;
        for (Voice &v : m_impl->voices)
            if (v.handler == handle)
                v.paused = true;
    }

    void Mixer::resume(uint32_t handle)
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        if (Stream *st = m_impl->findStream(handle))
            st->paused = false;
        if (Handler *h = m_impl->find(handle))
            h->paused = false;
        for (Voice &v : m_impl->voices)
            if (v.handler == handle)
                v.paused = false;
    }

    void Mixer::setVolPan(uint32_t handle, int32_t vol, int32_t pan)
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        Handler *h = m_impl->find(handle);
        if (!h)
            return;
        auto bit = m_impl->banks.find(h->bank);
        if (bit == m_impl->banks.end())
            return;
        const socom2_bank::Sound &snd = bit->second.bank.sounds[h->sound];
        if (vol != kVolDontChange)
        {
            int32_t playVol = (snd.vol * std::clamp(vol, 0, 0x400)) >> 10;
            h->curVolume = std::min(127, std::max(0, playVol));
        }
        if (pan == kPanReset)
            h->curPan = snd.pan;
        else if (pan != kPanDontChange)
            h->curPan = pan;
        m_impl->updateHandlerVoices(*h);
    }

    void Mixer::setMasterVolume(uint32_t group, int32_t vol)
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        const int32_t v = std::clamp(vol, 0, 0x400);
        if (group == 16u)
            m_impl->masterVol[16] = v;
        else if (group < 16u)
            m_impl->masterVol[group] = v;
    }

    void Mixer::stopAll()
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        for (Handler &h : m_impl->handlers)
            h.done = true;
        for (Voice &v : m_impl->voices)
            v.env.keyOff();
    }

    void Mixer::render(int16_t *interleaved, size_t frames)
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        std::memset(interleaved, 0, frames * 2 * sizeof(int16_t));
        std::vector<int32_t> mix(frames * 2, 0);
        const double framesPerTick = kSampleRate / kTickHz;
        size_t frame = 0;
        while (frame < frames)
        {
            // Frames until the next grain tick.
            const double untilTick = framesPerTick - m_impl->tickAccumulator;
            size_t chunk = static_cast<size_t>(std::max(1.0, std::ceil(untilTick)));
            chunk = std::min(chunk, frames - frame);
            for (Voice &v : m_impl->voices)
            {
                if (v.paused || v.env.phase == Envelope::Off || !v.sample)
                    continue;
                int32_t left = 0, right = 0;
                m_impl->applyVoiceVolume(v, left, right);
                const std::vector<int16_t> &pcm = v.sample->pcm;
                for (size_t i = 0; i < chunk; ++i)
                {
                    if (!v.env.tick())
                        break;
                    const size_t idx = static_cast<size_t>(v.pos);
                    if (idx >= pcm.size())
                    {
                        if (v.sample->loops && v.sample->loopStart < pcm.size())
                            v.pos = static_cast<double>(v.sample->loopStart) + (v.pos - static_cast<double>(pcm.size()));
                        else
                        {
                            v.env.phase = Envelope::Off;
                            break;
                        }
                    }
                    const size_t i0 = static_cast<size_t>(v.pos);
                    const size_t i1 = std::min(i0 + 1, pcm.size() - 1);
                    const double frac = v.pos - static_cast<double>(i0);
                    const double s = pcm[i0] * (1.0 - frac) + pcm[i1] * frac;
                    const double g = static_cast<double>(v.env.level) / 32767.0 / 0x7FFE;
                    mix[(frame + i) * 2] += static_cast<int32_t>(s * g * left);
                    mix[(frame + i) * 2 + 1] += static_cast<int32_t>(s * g * right);
                    v.pos += v.step;
                }
            }
            for (Stream &st : m_impl->streams)
            {
                if (st.paused || st.done)
                    continue;
                int32_t left = 0, right = 0;
                {
                    const int32_t modifier = m_impl->groupModifier(st.group);
                    left = ((st.base.left * modifier) / 0x400) >> 1;   // the SPU's half scale, as for the voices
                    right = ((st.base.right * modifier) / 0x400) >> 1;
                }
                for (size_t i = 0; i < chunk; ++i)
                {
                    if (st.pcm.empty() || st.pcm[0].empty() || st.pos >= static_cast<double>(st.pcm[0].size()))
                    {
                        const double carry = st.pcm.empty() || st.pcm[0].empty() ? 0.0 : st.pos - static_cast<double>(st.pcm[0].size());
                        if (!st.readChunkPair() || st.pcm[0].empty())
                        {
                            st.done = true;
                            break;
                        }
                        st.pos = std::max(0.0, carry);
                    }
                    const std::vector<int16_t> &l = st.pcm[0];
                    const std::vector<int16_t> &r = st.pcm[st.channels > 1 ? 1 : 0];
                    const size_t i0 = static_cast<size_t>(st.pos);
                    const size_t i1 = std::min(i0 + 1, l.size() - 1);
                    const double frac = st.pos - static_cast<double>(i0);
                    const double sl = l[i0] * (1.0 - frac) + l[i1] * frac;
                    const double sr = (i0 < r.size() ? r[i0] : 0) * (1.0 - frac) + (i1 < r.size() ? r[i1] : 0) * frac;
                    mix[(frame + i) * 2] += static_cast<int32_t>(sl / 0x7FFE * left);
                    mix[(frame + i) * 2 + 1] += static_cast<int32_t>(sr / 0x7FFE * right);
                    st.pos += st.step;
                }
            }
            if (m_impl->pcm.active && m_impl->pcm.frames() > 0)
            {
                Impl::PcmRing &ring = m_impl->pcm;
                const int32_t gain = (ring.gain * m_impl->masterVol[16]) / 0x400;
                const double step = static_cast<double>(ring.rate) / static_cast<double>(kSampleRate);
                const uint32_t total = ring.frames();
                for (size_t i = 0; i < chunk; ++i)
                {
                    const uint32_t f = static_cast<uint32_t>(ring.pos) % total;
                    const int32_t l = ring.sample(f, 0);
                    const int32_t r = ring.channels >= 2 ? ring.sample(f, 1) : l;
                    mix[(frame + i) * 2] += (l * gain) / 0x7fff;   // the SPU voice volume is 15-bit: 0x3fff (the >> 1 of full) is half scale
                    mix[(frame + i) * 2 + 1] += (r * gain) / 0x7fff;
                    ring.pos += step;
                    if (ring.pos >= static_cast<double>(total))
                        ring.pos -= static_cast<double>(total);
                }
            }
            frame += chunk;
            m_impl->tickAccumulator += static_cast<double>(chunk);
            if (m_impl->tickAccumulator >= framesPerTick)
            {
                m_impl->tickAccumulator -= framesPerTick;
                m_impl->tick();
            }
        }
        for (size_t i = 0; i < frames * 2; ++i)
            interleaved[i] = static_cast<int16_t>(std::clamp<int32_t>(mix[i], -32768, 32767));
        m_impl->reap();
    }

    size_t Mixer::activeVoices() const
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        size_t n = 0;
        for (const Voice &v : m_impl->voices)
            if (v.env.phase != Envelope::Off)
                ++n;
        return n;
    }

    size_t Mixer::activeHandlers() const
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        size_t n = 0;
        for (const Handler &h : m_impl->handlers)
            if (m_impl->handlerAlive(h))
                ++n;
        return n;
    }
}

namespace snd989
{
    bool Mixer::playStream(uint32_t handle, const std::string &path, uint64_t byteOffset, int32_t vol, int32_t pan, uint8_t group)
    {
        FILE *fp = std::fopen(path.c_str(), "rb");
        if (!fp)
            return false;
        // Two file shapes on the disc (research/32 section 5): a VPK (magic stored as the little-endian word "VPK ",
        // so the bytes read " KPV"; data size, interleave, header size, rate, channels as little-endian words) for the
        // music, and a "VAGp" (48-byte big-endian header: data size at 0x0c, rate at 0x10; mono) for the voice-overs.
        uint8_t header[0x30] = {};
        if (seek64(fp, byteOffset) != 0 || std::fread(header, 1, sizeof(header), fp) != sizeof(header))
        {
            std::fclose(fp);
            return false;
        }
        auto u32 = [&](size_t at) { uint32_t v; std::memcpy(&v, header + at, 4); return v; };
        auto be32 = [&](size_t at) { return (static_cast<uint32_t>(header[at]) << 24) | (static_cast<uint32_t>(header[at + 1]) << 16) | (static_cast<uint32_t>(header[at + 2]) << 8) | header[at + 3]; };
        Stream st;
        st.handle = handle;
        st.file = fp;
        if (std::memcmp(header, " KPV", 4) == 0)
        {
            st.dataSize = u32(4);
            st.interleave = std::max<uint32_t>(16u, u32(8));
            st.rate = u32(16) ? u32(16) : 32000u;
            st.channels = std::clamp<uint32_t>(u32(20), 1u, 2u);
            st.dataStart = byteOffset + u32(12);
        }
        else if (std::memcmp(header, "VAGp", 4) == 0)
        {
            st.dataSize = be32(12);
            st.interleave = 0x800;
            st.rate = be32(16) ? be32(16) : 44100u;
            st.channels = 1;
            st.dataStart = byteOffset + 48;
        }
        else
        {
            std::fclose(fp);
            return false;
        }
        st.group = group;
        st.step = static_cast<double>(st.rate) / static_cast<double>(kSampleRate);
        st.pcm.assign(st.channels, {});
        st.s1.assign(st.channels, 0);
        st.s2.assign(st.channels, 0);
        const int32_t playVol = std::min(127, (127 * std::clamp(vol, 0, 0x400)) >> 10);
        const int32_t playPan = (pan == kPanReset || pan == kPanDontChange) ? 0 : pan;
        st.base = makeVolume(127, 0, playVol, playPan, 127, 0);
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        if (Stream *old = m_impl->findStream(handle))
            m_impl->closeStream(*old);
        m_impl->streams.push_back(std::move(st));
        return true;
    }

    void Mixer::stopAllStreams()
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        for (Stream &st : m_impl->streams)
            m_impl->closeStream(st);
    }

    size_t Mixer::activeStreams() const
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        size_t n = 0;
        for (const Stream &st : m_impl->streams)
            if (!st.done)
                ++n;
        return n;
    }
}

namespace snd989
{
    void Mixer::pcmStreamStart(uint32_t ringBytes, uint32_t rate, uint32_t channels, int32_t vol)
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        Impl::PcmRing &ring = m_impl->pcm;
        ring.bytes.assign(std::min<uint32_t>(ringBytes, 4u << 20), 0u);
        ring.rate = rate ? rate : 48000u;
        ring.channels = std::clamp<uint32_t>(channels ? channels : 2u, 1u, 2u);
        // vol 0..0x400 -> 0..0x7ffe (MakeVolume's scale) then the SPU's >> 1: 0..0x3fff
        ring.gain = static_cast<int32_t>((static_cast<int64_t>(0x7ffe) * std::clamp(vol, 0, 0x400)) / 0x400) >> 1;
        ring.pos = 0.0;
        ring.active = !ring.bytes.empty();
    }

    void Mixer::pcmStreamWrite(uint32_t offset, const uint8_t *data, size_t bytes)
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        Impl::PcmRing &ring = m_impl->pcm;
        if (!data || ring.bytes.empty() || offset >= ring.bytes.size())
            return;
        const size_t n = std::min(bytes, ring.bytes.size() - offset);
        std::memcpy(ring.bytes.data() + offset, data, n);
    }

    uint32_t Mixer::pcmStreamPosition() const
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        const Impl::PcmRing &ring = m_impl->pcm;
        if (!ring.active || ring.frames() == 0)
            return 0u;
        return (static_cast<uint32_t>(ring.pos) % ring.frames()) * 2u * ring.channels;
    }

    void Mixer::pcmStreamStop()
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        m_impl->pcm.active = false;
        m_impl->pcm.pos = 0.0;
    }

    bool Mixer::pcmStreamActive() const
    {
        std::lock_guard<std::mutex> lock(m_impl->mutex);
        return m_impl->pcm.active;
    }
}
