#pragma once
// PS2 VAG / SPU ADPCM decoding (research/32 section 3). 16-byte blocks: byte 0 = shift | filter << 4, byte 1 =
// flags (bit0 end, bit1 repeat, bit2 loop start), 14 bytes of nibbles = 28 samples.
#include <cstddef>
#include <cstdint>
#include <vector>

namespace ps2_vag
{
    // A "VAGp"-headed file (48-byte header, sample rate at 0x10).
    bool decode(const uint8_t *data, uint32_t sizeBytes, std::vector<int16_t> &outPcm, uint32_t &outSampleRate);

    struct BlockRun
    {
        std::vector<int16_t> pcm;   // 28 samples per block decoded
        size_t bytesConsumed = 0;   // blocks read, including the end-flagged one
        bool loops = false;         // the end block carries the repeat flag
        size_t loopStartSample = 0; // sample index of the block flagged loop-start (0 when none)
    };

    // Headerless blocks (a sound bank's VAG chunk): decode from `data` until the block whose flags carry bit0,
    // or `maxBytes` (whole blocks only). Returns false when maxBytes < 16.
    bool decodeBlocks(const uint8_t *data, size_t maxBytes, BlockRun &out);
}
