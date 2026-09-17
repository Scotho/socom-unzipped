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
}

void register_socom2_audio_tests()
{
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
            std::vector<int16_t> buf(2 * 2048);
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
    });
}
