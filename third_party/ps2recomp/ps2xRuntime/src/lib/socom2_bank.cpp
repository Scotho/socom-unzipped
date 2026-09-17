#include "runtime/socom2_bank.h"

#include <cstring>

// The "SBlk" version 3 block SOCOM II ships (research/32 section 1, read off the disc): the header below, a
// 12-byte sound table at FirstSound, 8-byte compact grains at FirstGrain (opcode = type << 24 | arg24, delay),
// the TONE parameters (24 bytes) in the GrainData pool, and the block name at BlockNames.
namespace socom2_bank
{
    namespace
    {
        constexpr uint32_t kMagicSBlk = 0x6B6C4253u;
        constexpr size_t kHeaderBytes = 0x40;
        constexpr size_t kSoundBytes = 12;
        constexpr size_t kGrainBytes = 8;
        constexpr size_t kToneBytes = 24;

        uint32_t u32(const uint8_t *p) { uint32_t v; std::memcpy(&v, p, 4); return v; }
        int32_t s32(const uint8_t *p) { int32_t v; std::memcpy(&v, p, 4); return v; }
        int16_t s16(const uint8_t *p) { int16_t v; std::memcpy(&v, p, 2); return v; }
        uint16_t u16(const uint8_t *p) { uint16_t v; std::memcpy(&v, p, 2); return v; }
    }

    bool Bank::tone(const Grain &grain, Tone &out) const
    {
        if (grain.type != kTone && grain.type != kTone2)
            return false;
        if (static_cast<size_t>(grain.arg) + kToneBytes > grainData.size())
            return false;
        const uint8_t *p = grainData.data() + grain.arg;
        out.priority = static_cast<int8_t>(p[0]);
        out.vol = static_cast<int8_t>(p[1]);
        out.centerNote = static_cast<int8_t>(p[2]);
        out.centerFine = static_cast<int8_t>(p[3]);
        out.pan = s16(p + 4);
        out.mapLow = static_cast<int8_t>(p[6]);
        out.mapHigh = static_cast<int8_t>(p[7]);
        out.pbLow = static_cast<int8_t>(p[8]);
        out.pbHigh = static_cast<int8_t>(p[9]);
        out.adsr1 = u16(p + 10);
        out.adsr2 = u16(p + 12);
        out.flags = u16(p + 14);
        out.sampleOffset = u32(p + 16);
        return true;
    }

    bool parse(const uint8_t *block, size_t bytes, Bank &out)
    {
        if (!block || bytes < kHeaderBytes)
            return false;
        if (u32(block + 0x00) != kMagicSBlk || u32(block + 0x04) != 3u)
            return false;
        Bank bank;
        bank.version = u32(block + 0x04);
        bank.bankId = u32(block + 0x0C);
        const int16_t numSounds = s16(block + 0x16);
        const int16_t numGrains = s16(block + 0x18);
        const uint32_t firstSound = u32(block + 0x1C);
        const uint32_t firstGrain = u32(block + 0x20);
        const uint32_t grainData = u32(block + 0x34);
        const uint32_t blockNames = u32(block + 0x38);
        if (numSounds < 0 || numGrains < 0)
            return false;
        if (static_cast<size_t>(firstSound) + static_cast<size_t>(numSounds) * kSoundBytes > bytes)
            return false;
        if (static_cast<size_t>(firstGrain) + static_cast<size_t>(numGrains) * kGrainBytes > bytes)
            return false;
        if (grainData > bytes)
            return false;
        // The grain pool runs from GrainData to the names table (or the block end).
        const size_t poolEnd = (blockNames > grainData && blockNames <= bytes) ? blockNames : bytes;
        bank.grainData.assign(block + grainData, block + poolEnd);
        if (blockNames < bytes)
        {
            const uint8_t *n = block + blockNames;
            size_t len = 0;
            while (blockNames + len < bytes && len < 16 && n[len] != 0)
                ++len;
            bank.name.assign(reinterpret_cast<const char *>(n), len);
        }
        bank.sounds.resize(static_cast<size_t>(numSounds));
        for (int16_t i = 0; i < numSounds; ++i)
        {
            const uint8_t *p = block + firstSound + static_cast<size_t>(i) * kSoundBytes;
            Sound &s = bank.sounds[static_cast<size_t>(i)];
            s.vol = static_cast<int8_t>(p[0]);
            s.volGroup = static_cast<int8_t>(p[1]);
            s.pan = s16(p + 2);
            const int8_t numGrainsOfSound = static_cast<int8_t>(p[4]);
            s.instanceLimit = static_cast<int8_t>(p[5]);
            s.flags = u16(p + 6);
            const int32_t firstSfxGrain = s32(p + 8);
            if (numGrainsOfSound <= 0 || firstSfxGrain < 0)
                continue;
            const size_t start = static_cast<size_t>(firstGrain) + static_cast<size_t>(firstSfxGrain);
            if (start + static_cast<size_t>(numGrainsOfSound) * kGrainBytes > bytes)
                return false;
            s.grains.resize(static_cast<size_t>(numGrainsOfSound));
            for (int8_t g = 0; g < numGrainsOfSound; ++g)
            {
                const uint8_t *q = block + start + static_cast<size_t>(g) * kGrainBytes;
                const uint32_t opcode = u32(q);
                Grain &grain = s.grains[static_cast<size_t>(g)];
                grain.type = static_cast<uint8_t>(opcode >> 24);
                grain.arg = opcode & 0xFFFFFFu;
                grain.delay = s32(q + 4);
            }
        }
        out = std::move(bank);
        return true;
    }
}
