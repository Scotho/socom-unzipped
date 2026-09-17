#pragma once
// A 989snd sound bank block ("SBlk" version 3, the layout SOCOM II ships -- research/32 section 1), parsed from the
// block chunk's bytes. The VAG chunk is separate; Tone::sampleOffset indexes it.
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace socom2_bank
{
    enum GrainType : uint8_t
    {
        kTone = 1, kXrefId = 2, kXrefNum = 3, kLfo = 4, kStartChild = 5, kStopChild = 6, kPlugin = 7, kBranch = 8,
        kTone2 = 9, kControlNull = 20, kLoopStart = 21, kLoopEnd = 22, kLoopContinue = 23, kStop = 24, kRandPlay = 25,
        kRandDelay = 26, kRandPb = 27, kPb = 28, kAddPb = 29, kSetRegister = 30, kSetRegisterRand = 31, kIncRegister = 32,
        kDecRegister = 33, kTestRegister = 34, kMarker = 35, kGotoMarker = 36, kGotoRandomMarker = 37,
        kWaitForAllVoices = 38, kPlayCycle = 39, kAddRegister = 40, kKeyOffVoices = 41, kKillVoices = 42,
        kOnStopMarker = 43, kCopyRegister = 44,
    };

    struct Tone
    {
        int8_t priority = 0, vol = 0, centerNote = 0, centerFine = 0;
        int16_t pan = 0;
        int8_t mapLow = 0, mapHigh = 0, pbLow = 0, pbHigh = 0;
        uint16_t adsr1 = 0, adsr2 = 0, flags = 0;
        uint32_t sampleOffset = 0;   // into the VAG chunk
    };

    struct Grain
    {
        uint8_t type = 0;
        uint32_t arg = 0;   // the 24-bit operand: a GrainData offset for TONE, a value for the control grains
        int32_t delay = 0;  // ticks
    };

    struct Sound
    {
        int8_t vol = 0, volGroup = 0;
        int16_t pan = 0;
        int8_t instanceLimit = 0;
        uint16_t flags = 0;
        std::vector<Grain> grains;
    };

    struct Bank
    {
        uint32_t version = 0, bankId = 0;
        std::string name;
        std::vector<Sound> sounds;
        std::vector<uint8_t> grainData;   // the parameter pool the TONE grains index

        // The Tone a TONE / TONE2 grain names; false for another grain type or an out-of-range operand.
        bool tone(const Grain &grain, Tone &out) const;
    };

    // Parses the block chunk. False when the magic is not "SBlk", the version is not 3, or a table runs off the end.
    bool parse(const uint8_t *block, size_t bytes, Bank &out);
}
