// Task 6c Step 2 (research/32): the sound bank reader and the headerless VAG block decoder, against the HUDUI
// bank cut from the disc (tests/fixtures/audio/hudui_block.bin = chunk 0, 3472 bytes; hudui_vag.bin = chunk 1,
// 60928 bytes; sector 2010461 of the r0001 ISO).
#include "MiniTest.h"
#include "runtime/ps2_vag.h"
#include "runtime/socom2_bank.h"
#include "runtime/snd989_mixer.h"
#include "runtime/ps2_audio.h"

#include <cmath>

#include <algorithm>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <string>
#include <vector>

namespace
{
    std::vector<uint8_t> readFixture(const char *name)
    {
        const char *roots[] = {"../../../../tests/fixtures/audio/", "tests/fixtures/audio/", "../../../tests/fixtures/audio/"};
        for (const char *root : roots)
        {
            const std::string path = std::string(root) + name;
            if (FILE *fp = std::fopen(path.c_str(), "rb"))
            {
                std::vector<uint8_t> bytes;
                uint8_t buf[4096];
                size_t n;
                while ((n = std::fread(buf, 1, sizeof(buf), fp)) > 0)
                    bytes.insert(bytes.end(), buf, buf + n);
                std::fclose(fp);
                return bytes;
            }
        }
        return {};
    }

    // One ADPCM block: shift, filter, flags, 28 4-bit samples (-8..7).
    std::vector<uint8_t> block(uint8_t shift, uint8_t filter, uint8_t flags, const int8_t (&nibbles)[28])
    {
        std::vector<uint8_t> b(16, 0u);
        b[0] = static_cast<uint8_t>((shift & 0x0F) | (filter << 4));
        b[1] = flags;
        for (int i = 0; i < 28; ++i)
        {
            const uint8_t n = static_cast<uint8_t>(nibbles[i] & 0x0F);
            if (i & 1)
                b[2 + i / 2] |= static_cast<uint8_t>(n << 4);
            else
                b[2 + i / 2] |= n;
        }
        return b;
    }

    // A stereo VPK on disk: 0xB0-byte header {"VPK ", dataSize, interleave 0x800, headerSize 0xB0, rate 32000,
    // channels 2}, then `chunkPairs` pairs of 0x800-byte chunks (left ramp up, right ramp down); the very last
    // block carries the data's end flag. Task 1e's ring cases need a file longer than the ring holds.
    bool writeVpk(const std::string &path, int chunkPairs)
    {
        int8_t up[28], down[28];
        for (int i = 0; i < 28; ++i)
        {
            up[i] = static_cast<int8_t>(i % 8);
            down[i] = static_cast<int8_t>(-(i % 8));
        }
        std::vector<uint8_t> file(0xB0, 0u);
        auto put32 = [&](size_t at, uint32_t v) { file[at] = static_cast<uint8_t>(v); file[at + 1] = static_cast<uint8_t>(v >> 8); file[at + 2] = static_cast<uint8_t>(v >> 16); file[at + 3] = static_cast<uint8_t>(v >> 24); };
        std::memcpy(file.data(), " KPV", 4);
        put32(4, static_cast<uint32_t>(chunkPairs * 2 * 0x800));
        put32(8, 0x800);
        put32(12, 0xB0);
        put32(16, 32000);
        put32(20, 2);
        for (int c = 0; c < chunkPairs; ++c)
            for (int ch = 0; ch < 2; ++ch)
                for (int b = 0; b < 0x800 / 16; ++b)
                {
                    const bool last = c == chunkPairs - 1 && b == 0x800 / 16 - 1;
                    const std::vector<uint8_t> blk = block(12, 0, last ? 0x01 : 0x00, ch == 0 ? up : down);
                    file.insert(file.end(), blk.begin(), blk.end());
                }
        FILE *fp = std::fopen(path.c_str(), "wb");
        if (!fp)
            return false;
        std::fwrite(file.data(), 1, file.size(), fp);
        std::fclose(fp);
        return true;
    }
}

void register_socom2_audio_tests()
{
    // Task 1e: the mixer's stream worker is a thread; the tests drive pumpStreams() themselves so a case's audio
    // is a function of its calls and not of a 10 ms tick (the interface's PS2X_SND_STREAM_WORKER=0 path).
#ifdef _WIN32
    _putenv_s("PS2X_SND_STREAM_WORKER", "0");
#else
    setenv("PS2X_SND_STREAM_WORKER", "0", 1);
#endif

    MiniTest::Case("SOCOM2Audio", [](TestCase &tc)
    {
        tc.Run("the HUDUI bank parses: 24 sounds, sound 0's four tones, sound 16's grain script, the bank name", [](TestCase &t)
        {
            const std::vector<uint8_t> blk = readFixture("hudui_block.bin");
            t.Equals(blk.size(), static_cast<size_t>(3472u), "fixture hudui_block.bin is present (3472 bytes)");
            socom2_bank::Bank bank;
            t.IsTrue(socom2_bank::parse(blk.data(), blk.size(), bank), "parse accepts the SBlk v3 block");
            t.Equals(bank.version, 3u, "version 3");
            t.Equals(bank.sounds.size(), static_cast<size_t>(24u), "NumSounds sits at 0x16: 24 sounds (the first cut read 0 at 0x14)");
            t.Equals(bank.name, std::string("HUDUI"), "the block name");
            if (bank.sounds.size() < 24u)
                return;
            const socom2_bank::Sound &s0 = bank.sounds[0];
            t.Equals(static_cast<int>(s0.vol), 98, "sound 0 vol");
            t.Equals(static_cast<int>(s0.volGroup), 14, "sound 0 group");
            t.Equals(static_cast<int>(s0.pan), 0, "sound 0 pan");
            t.Equals(s0.grains.size(), static_cast<size_t>(4u), "sound 0 has four grains");
            t.Equals(static_cast<unsigned>(s0.flags), 2u, "sound 0 flags");
            if (s0.grains.size() == 4u)
            {
                socom2_bank::Tone tone;
                t.Equals(static_cast<int>(s0.grains[0].type), 1, "grain 0 is a TONE");
                t.IsTrue(bank.tone(s0.grains[0], tone), "the TONE grain resolves its parameters in GrainData");
                t.Equals(static_cast<int>(tone.priority), 99, "tone 0 priority");
                t.Equals(static_cast<int>(tone.vol), 90, "tone 0 vol");
                t.Equals(static_cast<int>(tone.centerNote), -58, "tone 0 center note (negative: a PS1 note)");
                t.Equals(static_cast<int>(tone.centerFine), 66, "tone 0 center fine");
                t.Equals(static_cast<unsigned>(tone.adsr1), 0x80ffu, "tone 0 ADSR1");
                t.Equals(static_cast<unsigned>(tone.adsr2), 0x9fe8u, "tone 0 ADSR2");
                t.Equals(tone.sampleOffset, 0x3940u, "tone 0 sample offset into the VAG chunk");
                t.IsTrue(bank.tone(s0.grains[3], tone) && tone.vol == 120 && tone.priority == 88 && tone.sampleOffset == 0x3030u, "tone 3: prio 88, vol 120, sample 0x3030");
                t.Equals(static_cast<int>(s0.grains[1].type), 1, "grain 1 is a TONE");
                t.IsTrue(bank.tone(s0.grains[1], tone) && tone.pan == 300 && tone.sampleOffset == 0xa820u, "tone 1: pan 300, sample 0xa820");
            }
            const socom2_bank::Sound &s5 = bank.sounds[5];
            t.Equals(s5.grains.size(), static_cast<size_t>(0u), "sound 5 has no grains (FirstSFXGrain -8)");
            const socom2_bank::Sound &s8 = bank.sounds[8];
            t.Equals(static_cast<int>(s8.vol), 115, "sound 8 vol");
            t.Equals(s8.grains.size(), static_cast<size_t>(1u), "sound 8 has one grain");
            const socom2_bank::Sound &s16 = bank.sounds[16];
            t.Equals(s16.grains.size(), static_cast<size_t>(5u), "sound 16 has five grains");
            if (s16.grains.size() == 5u)
            {
                const int types[5] = {4, 1, 1, 26, 41};
                for (int i = 0; i < 5; ++i)
                    t.Equals(static_cast<int>(s16.grains[i].type), types[i], "sound 16 grain " + std::to_string(i) + " type (LFO, TONE, TONE, RAND_DELAY, KEY_OFF_VOICES)");
                t.Equals(s16.grains[3].delay, 444, "the RAND_DELAY grain's delay");
                socom2_bank::Tone tone;
                t.IsTrue(bank.tone(s16.grains[1], tone) && tone.centerNote == -99 && tone.pbLow == 12 && tone.pbHigh == 12 && tone.sampleOffset == 0x6950u, "sound 16 tone 1: note -99, PB 12/12, sample 0x6950");
                t.IsTrue(bank.tone(s16.grains[2], tone) && tone.centerNote == -106 && tone.sampleOffset == 0x6950u, "sound 16 tone 2: the same sample at note -106");
                t.IsTrue(!bank.tone(s16.grains[3], tone), "a RAND_DELAY grain has no tone");
            }
        });

        tc.Run("parse rejects a block that is not SBlk v3 or runs off the end", [](TestCase &t)
        {
            const std::vector<uint8_t> blk = readFixture("hudui_block.bin");
            socom2_bank::Bank bank;
            std::vector<uint8_t> bad = blk;
            bad[0] ^= 0xFFu;
            t.IsTrue(!socom2_bank::parse(bad.data(), bad.size(), bank), "wrong magic");
            std::vector<uint8_t> wrongVersion = blk;
            wrongVersion[4] = 1u;
            t.IsTrue(!socom2_bank::parse(wrongVersion.data(), wrongVersion.size(), bank), "version 1 (the 0x28-byte grain layout) is not this reader's");
            t.IsTrue(!socom2_bank::parse(blk.data(), 0x100u, bank), "a block cut before its sound table");
            t.IsTrue(!socom2_bank::parse(blk.data(), 0x40u, bank), "a block cut at the header");
        });

        tc.Run("decodeBlocks: shift 12 filter 0 reproduces the nibbles; the end flag stops the run; loop flags are reported", [](TestCase &t)
        {
            int8_t ramp[28];
            for (int i = 0; i < 28; ++i)
                ramp[i] = static_cast<int8_t>((i % 16) - 8);   // -8..7
            std::vector<uint8_t> data = block(12, 0, 0, ramp);
            const std::vector<uint8_t> second = block(12, 0, 0x01, ramp);   // end
            data.insert(data.end(), second.begin(), second.end());
            const std::vector<uint8_t> third = block(12, 0, 0, ramp);       // past the end: not decoded
            data.insert(data.end(), third.begin(), third.end());
            ps2_vag::BlockRun run;
            t.IsTrue(ps2_vag::decodeBlocks(data.data(), data.size(), run), "decodes");
            t.Equals(run.bytesConsumed, static_cast<size_t>(32u), "two blocks consumed: the end-flagged block is the last");
            t.Equals(run.pcm.size(), static_cast<size_t>(56u), "28 samples per block");
            bool same = run.pcm.size() == 56u;
            for (size_t i = 0; same && i < 56u; ++i)
                same = run.pcm[i] == static_cast<int16_t>(ramp[i % 28]);
            t.IsTrue(same, "shift 12, filter 0: each sample is its sign-extended nibble");
            t.IsTrue(!run.loops, "an end block without the repeat flag does not loop");

            std::vector<uint8_t> looped = block(12, 0, 0, ramp);
            const std::vector<uint8_t> loopStart = block(12, 0, 0x04, ramp);   // loop start
            looped.insert(looped.end(), loopStart.begin(), loopStart.end());
            const std::vector<uint8_t> loopEnd = block(12, 0, 0x03, ramp);     // end + repeat
            looped.insert(looped.end(), loopEnd.begin(), loopEnd.end());
            ps2_vag::BlockRun run2;
            t.IsTrue(ps2_vag::decodeBlocks(looped.data(), looped.size(), run2), "decodes the looped sample");
            t.IsTrue(run2.loops, "end + repeat: the sample loops");
            t.Equals(run2.loopStartSample, static_cast<size_t>(28u), "the loop starts at the flagged block's first sample");
            t.Equals(run2.bytesConsumed, static_cast<size_t>(48u), "three blocks");

            ps2_vag::BlockRun run3;
            t.IsTrue(!ps2_vag::decodeBlocks(data.data(), 15u, run3), "fewer than 16 bytes is not a block");
            ps2_vag::BlockRun run4;
            t.IsTrue(ps2_vag::decodeBlocks(third.data(), third.size(), run4) && run4.pcm.size() == 28u && !run4.loops, "no end flag inside maxBytes: decode what is there, no loop");
        });

        tc.Run("decodeBlocks: filter 1 accumulates the previous sample (the reference filter table)", [](TestCase &t)
        {
            int8_t ones[28];
            for (int i = 0; i < 28; ++i)
                ones[i] = 1;
            const std::vector<uint8_t> data = block(12, 1, 0x01, ones);
            ps2_vag::BlockRun run;
            t.IsTrue(ps2_vag::decodeBlocks(data.data(), data.size(), run), "decodes");
            // s[n] = 1 + (60 * s[n-1] + 32) / 64: 1, 2, 3, 4, 5, 6, 7, 8 for the first eight samples
            const int16_t expect[8] = {1, 2, 3, 4, 5, 6, 7, 8};
            bool ok = run.pcm.size() == 28u;
            for (int i = 0; ok && i < 8; ++i)
                ok = run.pcm[static_cast<size_t>(i)] == expect[i];
            t.IsTrue(ok, "the first eight samples follow the filter-1 recurrence");
        });

        tc.Run("the HUDUI VAG chunk: sound 0's first sample decodes to 158 blocks ending on the end flag, non-looping, audible", [](TestCase &t)
        {
            const std::vector<uint8_t> vag = readFixture("hudui_vag.bin");
            t.Equals(vag.size(), static_cast<size_t>(60928u), "fixture hudui_vag.bin is present");
            if (vag.size() < 0x3940u + 2528u)
                return;
            ps2_vag::BlockRun run;
            t.IsTrue(ps2_vag::decodeBlocks(vag.data() + 0x3940u, vag.size() - 0x3940u, run), "decodes");
            t.Equals(run.bytesConsumed, static_cast<size_t>(2528u), "158 blocks to the end flag");
            t.Equals(run.pcm.size(), static_cast<size_t>(158u * 28u), "4424 samples");
            t.IsTrue(!run.loops, "a one-shot HUD sound");
            int32_t peak = 0;
            for (int16_t s : run.pcm)
                peak = std::max<int32_t>(peak, s < 0 ? -s : s);
            t.IsTrue(peak > 2000, "the sample has signal (peak " + std::to_string(peak) + ")");
        });

        tc.Run("note2Pitch: the SPU pitch of note 60 against HUDUI's tones matches 2^(semitones/12) to a unit, PS1 notes scaled by 44100/48000", [](TestCase &t)
        {
            auto expect = [](int centerNote, int centerFine, int note, int fine, bool ps1) -> double
            {
                // sceSdNote2Pitch adds the center fine to the played fine (a tuning offset), so the interval is
                // (note - center) semitones plus (fine + centerFine) / 128.
                const double semis = (note - centerNote) + (fine + centerFine) / 128.0;
                double p = 4096.0 * std::pow(2.0, semis / 12.0);
                if (ps1)
                    p = std::floor(44100.0 * std::floor(p) / 48000.0);
                return p;
            };
            // HUDUI sound 0 tone 0: center -58 / 66 (negative: not a PS1 note), played at note 60
            const double e0 = expect(58, 66, 60, 0, false);
            const uint16_t p0 = snd989::note2Pitch(-58, 66, 60, 0);
            t.IsTrue(std::fabs(p0 - e0) <= 1.5, "center -58/66 at note 60: " + std::to_string(p0) + " vs " + std::to_string(e0));
            t.Equals(static_cast<int>(snd989::note2Pitch(-60, 0, 60, 0)), 0x1000, "note at its own center is unity");
            const double e1 = expect(99, 104, 60, 0, false);
            const uint16_t p1 = snd989::note2Pitch(-99, 104, 60, 0);
            t.IsTrue(std::fabs(p1 - e1) <= 1.5, "sound 16 tone: center -99/104 -> " + std::to_string(p1) + " vs " + std::to_string(e1));
            const double e2 = expect(60, 0, 60, 0, true);
            const uint16_t p2 = snd989::note2Pitch(60, 0, 60, 0);
            t.IsTrue(std::fabs(p2 - e2) <= 1.5, "a PS1 note (center >= 0) is scaled by 44100/48000: " + std::to_string(p2) + " vs " + std::to_string(e2));
            const double e3 = expect(58, 66, 62, 64, false);
            const uint16_t p3 = snd989::note2Pitch(-58, 66, 62, 64);
            t.IsTrue(std::fabs(p3 - e3) <= 1.5, "note 62 fine 64 (pitch mod applied by the caller): " + std::to_string(p3) + " vs " + std::to_string(e3));
        });

        tc.Run("Mixer: a HUDUI sound plays to its end and goes quiet; stop keys it off; volume and master volume gate it", [](TestCase &t)
        {
            const std::vector<uint8_t> blk = readFixture("hudui_block.bin");
            const std::vector<uint8_t> vag = readFixture("hudui_vag.bin");
            snd989::Mixer mixer;
            t.IsTrue(mixer.loadBank(0x00a00000u, blk.data(), blk.size(), vag.data(), vag.size()), "HUDUI loads");
            t.Equals(mixer.bankCount(), static_cast<size_t>(1u), "one bank");
            t.Equals(mixer.play(0x00a00001u, 8u, 0x400, -1, 0, 0), 0u, "an unknown bank plays nothing");
            t.Equals(mixer.play(0x00a00000u, 99u, 0x400, -1, 0, 0), 0u, "an out-of-range sound plays nothing");
            const uint32_t h = mixer.play(0x00a00000u, 8u, 0x400, -1, 0, 0);   // the HUD click: one TONE, one-shot
            t.IsTrue(h != 0u && (h >> 24) == 5u, "a bank-sound handle (type 5)");
            t.IsTrue(mixer.isPlaying(h), "playing right after play()");
            t.Equals(mixer.activeVoices(), static_cast<size_t>(1u), "one voice for the one tone");
            std::vector<int16_t> buf(2 * 4096);
            mixer.render(buf.data(), 4096);
            double sum = 0.0;
            int32_t peak = 0;
            for (int16_t s : buf)
            {
                sum += static_cast<double>(s) * s;
                peak = std::max<int32_t>(peak, s < 0 ? -s : s);
            }
            const double rms = std::sqrt(sum / buf.size());
            t.IsTrue(peak > 500, "the first 4096 frames carry the click (peak " + std::to_string(peak) + ")");
            t.IsTrue(rms > 50.0, "and its RMS is above the floor (" + std::to_string(rms) + ")");
            // sound 8's sample is 4424 samples at ~1.156x: about 3830 frames; the envelope's release follows. Two seconds is plenty.
            size_t framesUntilQuiet = 0;
            for (int i = 0; i < 24 && mixer.isPlaying(h); ++i)
            {
                mixer.render(buf.data(), 4096);
                framesUntilQuiet += 4096;
            }
            t.IsTrue(!mixer.isPlaying(h), "the one-shot ends on its own (" + std::to_string(framesUntilQuiet) + " more frames)");
            t.Equals(mixer.activeVoices(), static_cast<size_t>(0u), "no voice left");
            t.Equals(mixer.activeHandlers(), static_cast<size_t>(0u), "no handler left");

            // Stop: the voice releases and the handle dies within a second.
            const uint32_t h2 = mixer.play(0x00a00000u, 8u, 0x400, -1, 0, 0);
            mixer.render(buf.data(), 512);
            mixer.stop(h2);
            size_t after = 0;
            for (int i = 0; i < 12 && mixer.isPlaying(h2); ++i)
            {
                mixer.render(buf.data(), 4096);
                after += 4096;
            }
            t.IsTrue(!mixer.isPlaying(h2) && after <= 48000u, "stopped within a second of frames (" + std::to_string(after) + ")");

            // Volume 0 is silence; so is master volume 0 on the sound's group.
            const uint32_t h3 = mixer.play(0x00a00000u, 8u, 0, -1, 0, 0);
            mixer.render(buf.data(), 4096);
            int32_t peak3 = 0;
            for (int16_t s : buf)
                peak3 = std::max<int32_t>(peak3, s < 0 ? -s : s);
            t.Equals(peak3, 0, "vol 0: silence");
            mixer.stop(h3);
            mixer.stopAll();
            for (int i = 0; i < 12; ++i)
                mixer.render(buf.data(), 4096);
            mixer.setMasterVolume(16u, 0);
            const uint32_t h4 = mixer.play(0x00a00000u, 8u, 0x400, -1, 0, 0);
            mixer.render(buf.data(), 4096);
            int32_t peak4 = 0;
            for (int16_t s : buf)
                peak4 = std::max<int32_t>(peak4, s < 0 ? -s : s);
            t.Equals(peak4, 0, "master volume 0: silence");
            t.IsTrue(mixer.isPlaying(h4), "... but the sound still runs");
            mixer.setMasterVolume(16u, 0x400);
            mixer.stopAll();
        });

        tc.Run("Mixer: pan puts the sound left or right; the sound's own pan is the default; SetVolPan moves it", [](TestCase &t)
        {
            const std::vector<uint8_t> blk = readFixture("hudui_block.bin");
            const std::vector<uint8_t> vag = readFixture("hudui_vag.bin");
            snd989::Mixer mixer;
            mixer.loadBank(0x00a00000u, blk.data(), blk.size(), vag.data(), vag.size());
            auto energy = [&](int32_t pan, double &left, double &right)
            {
                const uint32_t h = mixer.play(0x00a00000u, 8u, 0x400, pan, 0, 0);
                std::vector<int16_t> buf(2 * 2048);
                mixer.render(buf.data(), 2048);
                left = right = 0.0;
                for (size_t i = 0; i < 2048; ++i)
                {
                    left += std::fabs(static_cast<double>(buf[2 * i]));
                    right += std::fabs(static_cast<double>(buf[2 * i + 1]));
                }
                mixer.stopAll();
                for (int i = 0; i < 12; ++i)
                    mixer.render(buf.data(), 2048);
                return h;
            };
            double l = 0, r = 0;
            energy(-1, l, r);   // sound 8's own pan is 0: centre
            t.IsTrue(l > 0 && r > 0 && std::fabs(l - r) < 0.05 * (l + r), "pan reset (-1) -> the sound's own pan 0: centred");
            energy(270, l, r);
            t.IsTrue(l > 4.0 * r, "pan 270 is hard left (L " + std::to_string(l) + " R " + std::to_string(r) + ")");
            energy(90, l, r);
            t.IsTrue(r > 4.0 * l, "pan 90 is hard right (L " + std::to_string(l) + " R " + std::to_string(r) + ")");
            energy(0x167, l, r);
            t.IsTrue(l > r && l < 2.0 * r, "pan 359 (the weapon bank's) is just left of centre");

            const uint32_t h = mixer.play(0x00a00000u, 8u, 0x400, 0, 0, 0);
            mixer.setVolPan(h, snd989::kVolDontChange, 270);
            std::vector<int16_t> buf(2 * 2048);
            mixer.render(buf.data(), 2048);
            l = r = 0.0;
            for (size_t i = 0; i < 2048; ++i)
            {
                l += std::fabs(static_cast<double>(buf[2 * i]));
                r += std::fabs(static_cast<double>(buf[2 * i + 1]));
            }
            t.IsTrue(l > 4.0 * r, "SetVolPan to 270 moved the playing sound hard left");
            mixer.stopAll();
        });

        tc.Run("Mixer: a multi-tone sound starts all its tones; pitch mod raises the pitch; unloadBank silences the bank", [](TestCase &t)
        {
            const std::vector<uint8_t> blk = readFixture("hudui_block.bin");
            const std::vector<uint8_t> vag = readFixture("hudui_vag.bin");
            snd989::Mixer mixer;
            mixer.loadBank(0x00a00000u, blk.data(), blk.size(), vag.data(), vag.size());
            const uint32_t h = mixer.play(0x00a00000u, 0u, 0x400, -1, 0, 0);   // four TONE grains, delay 0
            t.IsTrue(h != 0u, "sound 0 plays");
            t.Equals(mixer.activeVoices(), static_cast<size_t>(4u), "four voices, one per tone");
            mixer.stopAll();
            std::vector<int16_t> buf(2 * 4096);
            for (int i = 0; i < 12; ++i)
                mixer.render(buf.data(), 4096);
            t.Equals(mixer.activeVoices(), static_cast<size_t>(0u), "stopAll released every voice");

            // Pitch mod +1200 (12 semitones in 1/128 units = 1536) plays the one-shot in about half the frames.
            auto framesToEnd = [&](int32_t pm)
            {
                const uint32_t hh = mixer.play(0x00a00000u, 8u, 0x400, -1, pm, 0);
                size_t frames = 0;
                while (mixer.isPlaying(hh) && frames < 48000u * 4u)
                {
                    mixer.render(buf.data(), 256);
                    frames += 256;
                }
                return frames;
            };
            const size_t f0 = framesToEnd(0);
            const size_t f1 = framesToEnd(1536);
            t.IsTrue(f1 < f0 && f1 > f0 / 4, "an octave up ends in about half the frames (" + std::to_string(f1) + " vs " + std::to_string(f0) + ")");

            const uint32_t h5 = mixer.play(0x00a00000u, 8u, 0x400, -1, 0, 0);
            mixer.unloadBank(0x00a00000u);
            t.Equals(mixer.bankCount(), static_cast<size_t>(0u), "bank gone");
            t.IsTrue(!mixer.isPlaying(h5), "its sounds stop with it");
            t.Equals(mixer.play(0x00a00000u, 8u, 0x400, -1, 0, 0), 0u, "and it no longer plays");
        });

        tc.Run("PS2AudioBackend routes a bank and the play family from the IOP module into the mixer", [](TestCase &t)
        {
            const std::vector<uint8_t> blk = readFixture("hudui_block.bin");
            const std::vector<uint8_t> vag = readFixture("hudui_vag.bin");
            PS2AudioBackend backend;   // no audio device: the mix stream stays closed, the mixer still runs
            backend.onBankLoaded(0x00a00000u, blk.data(), blk.size(), vag.data(), vag.size());
            const int32_t play[7] = {0x05010001, 0x00a00000, 8, 0x400, -1, 0, 0};   // the module's handle first
            backend.onNotify(0x12u, play, 7u);
            t.Equals(backend.mixerActiveVoices(), static_cast<size_t>(1u), "snd_PlaySoundVolPanPMPBNoReturn started the tone");
            t.IsTrue(backend.mixerIsPlaying(0x05010001u), "under the module's handle");
            std::vector<int16_t> buf(2 * 4096);   // sized for the largest render below (a 2048 buffer overflowed the heap, 2026-09-17)
            backend.mixerRender(buf.data(), 2048);
            int32_t peak = 0;
            for (int16_t v : buf)
                peak = std::max<int32_t>(peak, v < 0 ? -v : v);
            t.IsTrue(peak > 500, "the mix has signal");
            const int32_t stop[1] = {0x05010001};
            backend.onNotify(0x15u, stop, 1u);
            for (int i = 0; i < 12; ++i)
                backend.mixerRender(buf.data(), 4096);
            t.IsTrue(!backend.mixerIsPlaying(0x05010001u), "snd_StopSound keyed it off");
            const int32_t unload[1] = {0x00a00000};
            backend.onNotify(0x06u, unload, 1u);
            backend.onNotify(0x12u, play, 7u);
            t.Equals(backend.mixerActiveVoices(), static_cast<size_t>(0u), "after snd_UnloadBank the bank plays nothing");
        });

        tc.Run("Mixer: a VPK stream plays its interleaved channels left and right at its own rate, then ends", [](TestCase &t)
        {
            // A VPK: 0xB0-byte header {"VPK ", dataSize, interleave 0x800, headerSize 0xB0, rate 32000, channels 2}, then
            // 0x800-byte chunks alternating L, R. Left carries a positive ramp, right a negative one.
            int8_t up[28], down[28];
            for (int i = 0; i < 28; ++i)
            {
                up[i] = static_cast<int8_t>(i % 8);        // 0..7
                down[i] = static_cast<int8_t>(-(i % 8));   // 0..-7
            }
            const int chunksPerChannel = 3;
            std::vector<uint8_t> file(0xB0, 0u);
            auto put32 = [&](size_t at, uint32_t v) { file[at] = static_cast<uint8_t>(v); file[at + 1] = static_cast<uint8_t>(v >> 8); file[at + 2] = static_cast<uint8_t>(v >> 16); file[at + 3] = static_cast<uint8_t>(v >> 24); };
            std::memcpy(file.data(), " KPV", 4);   // the disc stores the magic as the little-endian word "VPK "
            put32(4, static_cast<uint32_t>(chunksPerChannel * 2 * 0x800));
            put32(8, 0x800);
            put32(12, 0xB0);
            put32(16, 32000);
            put32(20, 2);
            for (int c = 0; c < chunksPerChannel; ++c)
                for (int ch = 0; ch < 2; ++ch)
                    for (int b = 0; b < 0x800 / 16; ++b)
                    {
                        const bool last = c == chunksPerChannel - 1 && b == 0x800 / 16 - 1;
                        const std::vector<uint8_t> blk = block(12, 0, last ? 0x01 : 0x00, ch == 0 ? up : down);
                        file.insert(file.end(), blk.begin(), blk.end());
                    }
            const std::string path = "socom2_audio_test_stream.vpk";
            {
                FILE *fp = std::fopen(path.c_str(), "wb");
                t.IsTrue(fp != nullptr, "the temporary VPK can be written");
                if (!fp)
                    return;
                std::fwrite(file.data(), 1, file.size(), fp);
                std::fclose(fp);
            }
            snd989::Mixer mixer;
            t.IsTrue(!mixer.playStream(0x04000001u, path, 4u, 0x400, -1, 1u), "an offset that is not a VPK header is refused");
            t.IsTrue(mixer.playStream(0x04000001u, path, 0u, 0x400, -1, 1u), "the stream starts");
            mixer.pumpStreams();   // the worker's job, driven by hand: the whole file fits the ring
            t.Equals(mixer.activeStreams(), static_cast<size_t>(1u), "one stream");
            t.IsTrue(mixer.isPlaying(0x04000001u), "playing under the module's handle");
            std::vector<int16_t> buf(2 * 4800);
            mixer.render(buf.data(), 4800);   // 100 ms
            double left = 0, right = 0;
            for (size_t i = 0; i < 4800; ++i)
            {
                left += buf[2 * i];
                right += buf[2 * i + 1];
            }
            t.IsTrue(left > 0 && right < 0, "left carries the positive ramp, right the negative (L " + std::to_string(left) + " R " + std::to_string(right) + ")");
            t.IsTrue(std::fabs(left + right) < 0.05 * (std::fabs(left) + std::fabs(right)), "and they are equal in size (pan reset = centre)");
            // 3 chunks x 128 blocks x 28 samples = 10752 samples at 32 kHz = 336 ms = 16128 output frames at 48 kHz.
            size_t frames = 4800;
            while (mixer.isPlaying(0x04000001u) && frames < 48000u)
            {
                mixer.render(buf.data(), 4800);
                frames += 4800;
            }
            t.IsTrue(!mixer.isPlaying(0x04000001u), "the stream ends after its data (" + std::to_string(frames) + " frames)");
            t.IsTrue(frames >= 14400u && frames <= 24000u, "about 16128 frames of output: 336 ms at 32 kHz resampled to 48 kHz");
            t.Equals(mixer.activeStreams(), static_cast<size_t>(0u), "no stream left");

            t.IsTrue(mixer.playStream(0x04000002u, path, 0u, 0x400, 90, 1u), "again, panned right");
            mixer.pumpStreams();
            mixer.render(buf.data(), 2400);
            left = right = 0;
            for (size_t i = 0; i < 2400; ++i)
            {
                left += std::fabs(static_cast<double>(buf[2 * i]));
                right += std::fabs(static_cast<double>(buf[2 * i + 1]));
            }
            t.IsTrue(right > 4.0 * left, "pan 90: hard right");
            mixer.stop(0x04000002u);
            t.IsTrue(!mixer.isPlaying(0x04000002u), "stop ends a stream at once");
            t.IsTrue(mixer.playStream(0x04000003u, path, 0u, 0x400, -1, 1u), "a third");
            mixer.stopAllStreams();
            t.Equals(mixer.activeStreams(), static_cast<size_t>(0u), "stopAllStreams");
            std::remove(path.c_str());
        });

        // Task 1e (audit 2026-09-17 section 2.3): the disc read moved off the audio callback. pumpStreams() decodes
        // ahead into each stream's ring on a worker; render() touches memory only.
        tc.Run("a stream plays out of its ring with the file handle closed", [](TestCase &t)
        {
            const std::string path = "socom2_audio_ring_stream.vpk";
            t.IsTrue(writeVpk(path, 8), "the temporary VPK can be written");
            snd989::Mixer mixer;
            t.IsTrue(mixer.playStream(1u, path, 0ull, 0x400, 0, 0u), "the stream starts");
            mixer.pumpStreams();
            t.Equals(mixer.activeStreams(), static_cast<size_t>(1u), "one live stream");
            mixer.closeStreamFilesForTest();
            std::vector<int16_t> buf(4096 * 2, 0);
            mixer.render(buf.data(), 4096);
            bool anyNonZero = false;
            for (int16_t s : buf) if (s != 0) { anyNonZero = true; break; }
            t.IsTrue(anyNonZero, "render plays the ring's contents with no file behind it");
            // And only the ring's contents: the file holds 8 chunk pairs, the ring at most kStreamRingChunks.
            // One chunk pair is 128 blocks x 28 samples = 3584 samples at 32 kHz = 5376 frames at 48 kHz.
            size_t frames = 4096;
            while (frames < 8u * 5376u)
            {
                mixer.render(buf.data(), 4096);
                frames += 4096;
            }
            bool tailNonZero = false;
            for (int16_t s : buf) if (s != 0) { tailNonZero = true; break; }
            t.IsTrue(!tailNonZero, "past the ring it goes quiet: render never read the rest of the file");
            std::remove(path.c_str());
        });

        tc.Run("render never reads the disc", [](TestCase &t)
        {
            const std::string path = "socom2_audio_ring_empty.vpk";
            t.IsTrue(writeVpk(path, 8), "the temporary VPK can be written");
            snd989::Mixer mixer;
            t.IsTrue(mixer.playStream(2u, path, 0ull, 0x400, 0, 0u), "the stream starts");
            mixer.closeStreamFilesForTest();          // nothing pumped: the ring is empty
            std::vector<int16_t> buf(4096 * 2, 0x7F);
            mixer.render(buf.data(), 4096);           // must not crash, must not read, must go quiet
            t.Equals(static_cast<int>(buf[0]), 0, "an empty ring renders silence, not a disc read");
            bool anyNonZero = false;
            for (int16_t s : buf) if (s != 0) { anyNonZero = true; break; }
            t.IsTrue(!anyNonZero, "the whole buffer is silence");
            t.Equals(mixer.activeStreams(), static_cast<size_t>(1u), "an underrun is not the end of the stream");
            std::remove(path.c_str());
        });

        tc.Run("PS2AudioBackend routes a VPK stream by sector and answers snd_SoundIsStillPlaying from the mixer", [](TestCase &t)
        {
            // A one-channel VPK in a "disc image" of three sectors: header at sector 2, so the play call's sector is 2.
            int8_t up[28];
            for (int i = 0; i < 28; ++i)
                up[i] = static_cast<int8_t>(i % 8);
            std::vector<uint8_t> image(2048u * 2u, 0u);
            std::vector<uint8_t> vpk(0xB0, 0u);
            auto put32 = [&](size_t at, uint32_t v) { vpk[at] = static_cast<uint8_t>(v); vpk[at + 1] = static_cast<uint8_t>(v >> 8); vpk[at + 2] = static_cast<uint8_t>(v >> 16); vpk[at + 3] = static_cast<uint8_t>(v >> 24); };
            std::memcpy(vpk.data(), " KPV", 4);
            put32(4, 0x800u);
            put32(8, 0x800u);
            put32(12, 0xB0u);
            put32(16, 32000u);
            put32(20, 1u);
            for (int b = 0; b < 0x800 / 16; ++b)
            {
                const std::vector<uint8_t> blk = block(12, 0, b == 0x800 / 16 - 1 ? 0x01 : 0x00, up);
                vpk.insert(vpk.end(), blk.begin(), blk.end());
            }
            image.insert(image.end(), vpk.begin(), vpk.end());
            const std::string path = "socom2_audio_test_image.bin";
            if (FILE *fp = std::fopen(path.c_str(), "wb"))
            {
                std::fwrite(image.data(), 1, image.size(), fp);
                std::fclose(fp);
            }
            PS2AudioBackend backend;
            backend.setDiscImagePath(path);
            const int32_t play[9] = {0x04000005, 2, 0, 0, 0x400, 0, -1, 1, 0};
            backend.onNotify(0x2Cu, play, 9u);
            backend.mixerPumpStreams();
            t.Equals(backend.mixerActiveStreams(), static_cast<size_t>(1u), "snd_PlayVAGStreamByLoc opened the stream at sector 2");
            bool playing = false;
            t.IsTrue(backend.isPlaying(0x04000005u, playing) && playing, "the mixer answers snd_SoundIsStillPlaying: playing");
            t.IsTrue(!backend.isPlaying(0x00a00000u, playing), "a bank handle is not a sound handle: no answer");
            std::vector<int16_t> buf(2 * 4800);
            backend.mixerRender(buf.data(), 4800);
            int32_t peak = 0;
            for (int16_t v : buf)
                peak = std::max<int32_t>(peak, v < 0 ? -v : v);
            t.IsTrue(peak > 0, "the stream is in the mix");
            const int32_t stop[1] = {0x04000005};
            backend.onNotify(0x2Fu, stop, 1u);
            t.IsTrue(backend.isPlaying(0x04000005u, playing) && !playing, "snd_StopVAGStream: the mixer says it is over");
            std::remove(path.c_str());
        });

        tc.Run("Mixer: a VAGp file (the mission voice-overs: 48-byte big-endian header, mono 22050 Hz) streams too", [](TestCase &t)
        {
            int8_t up[28];
            for (int i = 0; i < 28; ++i)
                up[i] = static_cast<int8_t>(i % 8);
            std::vector<uint8_t> file(48, 0u);
            std::memcpy(file.data(), "VAGp", 4);
            const uint32_t dataSize = 16u * 64u;   // 64 blocks
            file[12] = static_cast<uint8_t>(dataSize >> 24); file[13] = static_cast<uint8_t>(dataSize >> 16); file[14] = static_cast<uint8_t>(dataSize >> 8); file[15] = static_cast<uint8_t>(dataSize);
            const uint32_t rate = 22050u;
            file[16] = static_cast<uint8_t>(rate >> 24); file[17] = static_cast<uint8_t>(rate >> 16); file[18] = static_cast<uint8_t>(rate >> 8); file[19] = static_cast<uint8_t>(rate);
            std::memcpy(file.data() + 32, "M51_140", 7);
            for (int b = 0; b < 64; ++b)
            {
                const std::vector<uint8_t> blk = block(12, 0, b == 63 ? 0x01 : 0x00, up);
                file.insert(file.end(), blk.begin(), blk.end());
            }
            const std::string path = "socom2_audio_test_vo.vag";
            if (FILE *fp = std::fopen(path.c_str(), "wb"))
            {
                std::fwrite(file.data(), 1, file.size(), fp);
                std::fclose(fp);
            }
            snd989::Mixer mixer;
            t.IsTrue(mixer.playStream(0x04000009u, path, 0u, 0x400, -1, 1u), "the VAGp stream starts");
            mixer.pumpStreams();
            std::vector<int16_t> buf(2 * 4800);
            mixer.render(buf.data(), 4800);
            double left = 0, right = 0;
            for (size_t i = 0; i < 4800; ++i)
            {
                left += buf[2 * i];
                right += buf[2 * i + 1];
            }
            t.IsTrue(left > 0 && right > 0, "mono goes to both channels");
            // 64 blocks x 28 = 1792 samples at 22050 Hz = 81 ms = 3901 frames at 48 kHz: over in the first render.
            size_t frames = 4800;
            while (mixer.isPlaying(0x04000009u) && frames < 48000u)
            {
                mixer.render(buf.data(), 4800);
                frames += 4800;
            }
            t.IsTrue(frames <= 9600u, "ends within its 81 ms (" + std::to_string(frames) + " frames rendered)");
            std::remove(path.c_str());
        });

        tc.Run("Mixer: a full-scale stream at full volume sits at the SPU's half scale (voice volume >> 1), not at clipping", [](TestCase &t)
        {
            // shift 0: a nibble of 7 decodes to 7 << 12 = 28672. At vol 0x400 and centre pan the SPU voice volume is
            // 0x3fff * cos(45 deg) >> 1 of full scale: about 28672 * 0.707 * 0.5 = 10135 per channel.
            int8_t sevens[28];
            for (int i = 0; i < 28; ++i)
                sevens[i] = 7;
            std::vector<uint8_t> file(48, 0u);
            std::memcpy(file.data(), "VAGp", 4);
            const uint32_t dataSize = 16u * 32u;
            file[12] = static_cast<uint8_t>(dataSize >> 24); file[13] = static_cast<uint8_t>(dataSize >> 16); file[14] = static_cast<uint8_t>(dataSize >> 8); file[15] = static_cast<uint8_t>(dataSize);
            file[16] = 0; file[17] = 0; file[18] = 0xBB; file[19] = 0x80;   // 48000
            for (int b = 0; b < 32; ++b)
            {
                const std::vector<uint8_t> blk = block(0, 0, b == 31 ? 0x01 : 0x00, sevens);
                file.insert(file.end(), blk.begin(), blk.end());
            }
            const std::string path = "socom2_audio_test_loud.vag";
            if (FILE *fp = std::fopen(path.c_str(), "wb"))
            {
                std::fwrite(file.data(), 1, file.size(), fp);
                std::fclose(fp);
            }
            {   // the mixer must close the file before it can be removed (Windows)
                snd989::Mixer mixer;
                t.IsTrue(mixer.playStream(0x0400000Au, path, 0u, 0x400, -1, 1u), "starts");
                mixer.pumpStreams();
                std::vector<int16_t> buf(2 * 512);
                mixer.render(buf.data(), 512);
                int32_t peak = 0;
                for (int16_t v : buf)
                    peak = std::max<int32_t>(peak, v < 0 ? -v : v);
                t.IsTrue(peak >= 9000 && peak <= 11500, "peak " + std::to_string(peak) + " (about 10135: 28672 x 0.707 x 1/2)");
                mixer.stopAll();
            }
            std::remove(path.c_str());
        });

        tc.Run("Mixer: the PCM ring plays block-interleaved stereo (512-byte L and R blocks, as the movie audio is laid out) at its rate, reports its position, wraps, and stops", [](TestCase &t)
        {
            snd989::Mixer mixer;
            t.IsTrue(!mixer.pcmStreamActive(), "no PCM stream before start");
            t.Equals(mixer.pcmStreamPosition(), 0u, "position 0 before start");
            mixer.pcmStreamStart(0x6000u, 48000u, 2u, 0x400);
            t.IsTrue(mixer.pcmStreamActive(), "started");
            // 512-byte blocks alternating L (+8000) and R (-8000) over the whole ring: the SShd interleave of the movie audio.
            std::vector<uint8_t> ring(0x6000u);
            for (size_t i = 0; i < ring.size(); i += 2)
            {
                const int16_t v = ((i / 512) % 2 == 0) ? static_cast<int16_t>(8000) : static_cast<int16_t>(-8000);   // 512 bytes of L, 512 of R
                ring[i] = static_cast<uint8_t>(v & 0xFF);
                ring[i + 1] = static_cast<uint8_t>((v >> 8) & 0xFF);
            }
            mixer.pcmStreamWrite(0u, ring.data(), ring.size());
            std::vector<int16_t> buf(2 * 6144);   // sized for the largest render below
            mixer.render(buf.data(), 512);
            double left = 0, right = 0;
            for (size_t i = 0; i < 512; ++i)
            {
                left += buf[2 * i];
                right += buf[2 * i + 1];
            }
            t.IsTrue(left > 0 && right < 0, "left blocks to the left channel, right blocks to the right (L " + std::to_string(left) + " R " + std::to_string(right) + ")");
            t.IsTrue(std::fabs(left + right) < 0.02 * (std::fabs(left) + std::fabs(right)), "equal magnitudes");
            const int32_t sample = buf[0];
            t.IsTrue(sample >= 3600 && sample <= 4400, "vol 0x400 at half scale: 8000 -> about 4000 (got " + std::to_string(sample) + ")");
            t.Equals(mixer.pcmStreamPosition(), 512u * 4u, "512 frames of stereo 16-bit consumed 2048 bytes");
            // 0x6000 bytes = 6144 frames; 6144 - 512 more frames reach the end, then it wraps to 0.
            mixer.render(buf.data(), 6144u - 512u);
            t.Equals(mixer.pcmStreamPosition(), 0u, "the ring wraps");
            mixer.render(buf.data(), 100u);
            t.Equals(mixer.pcmStreamPosition(), 400u, "and continues from the start");
            // A rate below the output rate stretches: 24000 Hz consumes half the bytes per frame.
            mixer.pcmStreamStop();
            t.IsTrue(!mixer.pcmStreamActive() && mixer.pcmStreamPosition() == 0u, "stopped: inactive, position 0");
            mixer.render(buf.data(), 512);
            int32_t peak = 0;
            for (size_t i = 0; i < 2u * 512u; ++i)   // only the frames this render wrote
                peak = std::max<int32_t>(peak, buf[i] < 0 ? -buf[i] : buf[i]);
            t.Equals(peak, 0, "silence after stop");
            mixer.pcmStreamStart(0x6000u, 24000u, 2u, 0x400);
            mixer.pcmStreamWrite(0u, ring.data(), ring.size());
            mixer.render(buf.data(), 512);
            t.Equals(mixer.pcmStreamPosition(), 256u * 4u, "24 kHz: 512 output frames consume 256 ring frames");
            mixer.pcmStreamStop();
        });

        tc.Run("PS2AudioBackend routes the PCM stream: start, the EE's ring writes, the position the module reports, stop", [](TestCase &t)
        {
            PS2AudioBackend backend;
            uint32_t position = 0;
            t.IsTrue(!backend.pcmPosition(position), "no PCM stream: the module answers 0 itself");
            const int32_t start[5] = {0x6000, 0, 2, 0x366, 0x01a00000};
            backend.onNotify(0x3Eu, start, 5u);
            t.IsTrue(backend.pcmPosition(position) && position == 0u, "started at position 0");
            std::vector<uint8_t> half(0x3000u);
            for (size_t i = 0; i < half.size(); i += 2)
            {
                const int16_t v = ((i / 512) % 2 == 0) ? 6000 : -6000;   // 512 bytes of L, 512 of R
                half[i] = static_cast<uint8_t>(v & 0xFF);
                half[i + 1] = static_cast<uint8_t>((v >> 8) & 0xFF);
            }
            backend.onPcmWrite(0u, half.data(), half.size());
            std::vector<int16_t> buf(2 * 1024);
            backend.mixerRender(buf.data(), 1024);
            double left = 0, right = 0;
            for (size_t i = 0; i < 1024; ++i)
            {
                left += buf[2 * i];
                right += buf[2 * i + 1];
            }
            t.IsTrue(left > 0 && right < 0, "the ring's left blocks play left, right blocks right");
            t.IsTrue(backend.pcmPosition(position) && position == 1024u * 4u, "position after 1024 frames: 4096 bytes");
            const int32_t none[1] = {0};
            backend.onNotify(0x3Du, none, 1u);
            t.IsTrue(!backend.pcmPosition(position), "snd_PcmStreamStop: no stream");
        });
    });
}
