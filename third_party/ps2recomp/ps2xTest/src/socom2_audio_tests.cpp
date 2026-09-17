// Task 6c Step 2 (research/32): the sound bank reader and the headerless VAG block decoder, against the HUDUI
// bank cut from the disc (tests/fixtures/audio/hudui_block.bin = chunk 0, 3472 bytes; hudui_vag.bin = chunk 1,
// 60928 bytes; sector 2010461 of the r0001 ISO).
#include "MiniTest.h"
#include "runtime/ps2_vag.h"
#include "runtime/socom2_bank.h"

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
    });
}
