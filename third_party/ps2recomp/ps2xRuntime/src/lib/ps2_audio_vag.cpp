#include "runtime/ps2_memory.h"
#include "runtime/ps2_vag.h"
#include <algorithm>
#include <cstdint>
#include <cstring>

namespace
{
    inline int16_t clamp16(int32_t v)
    {
        if (v < -32768)
            return -32768;
        if (v > 32767)
            return 32767;
        return static_cast<int16_t>(v);
    }

    inline int8_t signExtend4(uint8_t nibble)
    {
        uint8_t s = nibble & 0x0F;
        return static_cast<int8_t>((s & 8) ? static_cast<int8_t>(s | 0xF0) : static_cast<int8_t>(s));
    }
}

namespace ps2_vag
{
    bool decode(const uint8_t *data, uint32_t sizeBytes,
                std::vector<int16_t> &outPcm, uint32_t &outSampleRate)
    {
        if (!data || sizeBytes < 48)
            return false;

        const uint32_t magic = (static_cast<uint32_t>(data[0]) << 24) |
                               (static_cast<uint32_t>(data[1]) << 16) |
                               (static_cast<uint32_t>(data[2]) << 8) |
                               static_cast<uint32_t>(data[3]);
        if (magic != 0x56414770u)
        {
            const uint32_t magicLE = (static_cast<uint32_t>(data[3]) << 24) |
                                     (static_cast<uint32_t>(data[2]) << 16) |
                                     (static_cast<uint32_t>(data[1]) << 8) |
                                     static_cast<uint32_t>(data[0]);
            if (magicLE != 0x56414770u)
                return false;
        }

        uint32_t dataSize = (static_cast<uint32_t>(data[0x0c]) << 24) |
                            (static_cast<uint32_t>(data[0x0d]) << 16) |
                            (static_cast<uint32_t>(data[0x0e]) << 8) |
                            static_cast<uint32_t>(data[0x0f]);
        outSampleRate = (static_cast<uint32_t>(data[0x10]) << 24) |
                        (static_cast<uint32_t>(data[0x11]) << 16) |
                        (static_cast<uint32_t>(data[0x12]) << 8) |
                        static_cast<uint32_t>(data[0x13]);
        if (outSampleRate == 0)
            outSampleRate = 44100;

        const uint32_t numBlocks = (dataSize + 15) / 16;
        outPcm.clear();
        outPcm.reserve(numBlocks * 28);

        int16_t s1 = 0, s2 = 0;
        const uint8_t *block = data + 48;

        for (uint32_t b = 0; b < numBlocks && (block + 16) <= data + sizeBytes; ++b, block += 16)
        {
            uint8_t shift = block[0] & 0x0F;
            if (shift > 12)
                shift = 9;
            uint8_t filter = (block[0] >> 4) & 0x07;
            if (filter > 4)
                filter = 0;

            for (int sampleIdx = 0; sampleIdx < 28; ++sampleIdx)
            {
                const uint8_t byte = block[2 + sampleIdx / 2];
                const uint8_t nibble = (sampleIdx & 1) ? (byte >> 4) : (byte & 0x0F);
                const int8_t rawSample = signExtend4(nibble);
                const int32_t shiftedSample = rawSample << (12 - shift);

                int32_t filteredSample;
                const int32_t old = s1;
                const int32_t older = s2;
                switch (filter)
                {
                case 0:
                    filteredSample = shiftedSample;
                    break;
                case 1:
                    filteredSample = shiftedSample + (60 * old + 32) / 64;
                    break;
                case 2:
                    filteredSample = shiftedSample + (115 * old - 52 * older + 32) / 64;
                    break;
                case 3:
                    filteredSample = shiftedSample + (98 * old - 55 * older + 32) / 64;
                    break;
                case 4:
                    filteredSample = shiftedSample + (122 * old - 60 * older + 32) / 64;
                    break;
                default:
                    filteredSample = shiftedSample;
                    break;
                }

                const int16_t clamped = clamp16(filteredSample);
                s2 = s1;
                s1 = clamped;
                outPcm.push_back(clamped);
            }
        }

        return true;
    }
}

namespace ps2_vag
{
    // Headerless SPU ADPCM blocks (a sound bank's VAG chunk, research/32 section 3). The same recurrence as
    // decode() above; the run ends at the block flagged end (bit0), whose repeat bit (bit1) says whether the
    // sample loops back to the block flagged loop-start (bit2).
    bool decodeBlocks(const uint8_t *data, size_t maxBytes, BlockRun &out)
    {
        if (!data || maxBytes < 16)
            return false;
        out.pcm.clear();
        out.bytesConsumed = 0;
        out.loops = false;
        out.loopStartSample = 0;
        int16_t s1 = 0, s2 = 0;
        for (size_t off = 0; off + 16 <= maxBytes; off += 16)
        {
            const uint8_t *block = data + off;
            uint8_t shift = block[0] & 0x0F;
            if (shift > 12)
                shift = 9;
            uint8_t filter = (block[0] >> 4) & 0x07;
            if (filter > 4)
                filter = 0;
            const uint8_t flags = block[1];
            if (flags & 0x04)
                out.loopStartSample = out.pcm.size();
            for (int sampleIdx = 0; sampleIdx < 28; ++sampleIdx)
            {
                const uint8_t byte = block[2 + sampleIdx / 2];
                const uint8_t nibble = (sampleIdx & 1) ? (byte >> 4) : (byte & 0x0F);
                const int8_t rawSample = signExtend4(nibble);
                const int32_t shifted = rawSample << (12 - shift);
                const int32_t old = s1;
                const int32_t older = s2;
                int32_t filtered;
                switch (filter)
                {
                case 1: filtered = shifted + (60 * old + 32) / 64; break;
                case 2: filtered = shifted + (115 * old - 52 * older + 32) / 64; break;
                case 3: filtered = shifted + (98 * old - 55 * older + 32) / 64; break;
                case 4: filtered = shifted + (122 * old - 60 * older + 32) / 64; break;
                default: filtered = shifted; break;
                }
                const int16_t clamped = clamp16(filtered);
                s2 = s1;
                s1 = clamped;
                out.pcm.push_back(clamped);
            }
            out.bytesConsumed = off + 16;
            if (flags & 0x01)
            {
                out.loops = (flags & 0x02) != 0;
                break;
            }
        }
        return true;
    }
}
