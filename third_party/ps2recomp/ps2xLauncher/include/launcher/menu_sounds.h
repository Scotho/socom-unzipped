#pragma once
// Sprint 10 Q4 (owner 2026-09-20: the launcher's sounds "drawn directly from the game sound for menu sounds"):
// four HUD cues out of the game's HUDUI bank, decoded from the PLAYER'S OWN DISC IMAGE the first time the
// launcher sees it, cached as WAV under the portable folder, and never part of the download -- the project ships
// no game assets (the portable README and LICENSES say so). No ISO, or one that is not the r0001 disc: silence,
// never a substitute sound.
//
// The bank. HUDUI is loaded by the game with snd_BankLoadByLoc at sector 2010461 of the r0001 disc (research/32
// section 1): a FileAttributes header (8 u32: type, chunk count, then offset/size per chunk), chunk 0 the "SBlk"
// block, chunk 1 the raw VAG data. Its 24 sounds are named in the block (this file's cue table was read off the
// name table on 2026-09-21: 0 DINK 1 BACK 2 THUNK 3 SLIDE 4 NEG 5 COUNT 6 TYPE_1 7 TYPE 8 METAL 9 SKB_ENTER
// 10 SKB_TYPE 11 SFX_VOL_SLIDER 12 TCM_SLIDE 13 TCM_SELECT 14/15 NV_GOGGLES_ON/OFF 16 SKB_NAV 17 BOMB_BEEP
// 18 SPLASHSCROLL_1 19-23 COUNTDOWN..5). The cues are rendered by the runtime's own 989snd mixer
// (snd989::Mixer, the code that plays them in the game), at the game's unity volume and the sound's own pan.
//
// PURE: no raylib. The ISO is read through iso9660::Reader (a function), so the tests hand it a synthetic image;
// the render is tested on tests/fixtures/audio/hudui_block.bin + hudui_vag.bin (chunks 0 and 1 of the bank).
// main.cpp owns the raylib side: the audio device, LoadSound on the cached files, PlaySound on the events.
#include "launcher/iso9660.h"

#include <cstdint>
#include <string>
#include <vector>

namespace launcher::menusounds
{
    constexpr uint32_t kHudUiSector = 2010461u;   // research/32 section 1: bank handle 0x00a00000
    constexpr const char *kBankName = "HUDUI";

    enum class Cue
    {
        Move = 0,   // the focus moved: .SLIDE (3)
        Select,     // a control was activated: .METAL (8), the HUD click the game plays 515 times a match
        Back,       // Escape / B: .BACK (1)
        Refuse,     // LAUNCH pressed while blocked: .NEG (4)
        Count
    };
    int cueSound(Cue cue);           // the sound index in the bank
    const char *cueFile(Cue cue);    // "move.wav" ... the cache file's name

    struct Bank
    {
        std::vector<uint8_t> block;   // chunk 0, the SBlk block
        std::vector<uint8_t> vag;     // chunk 1
    };

    // The bank at `sector`: the FileAttributes header, both chunks, the block parsed and its name checked.
    // False with `why` when the bytes there are not a bank named HUDUI (a different disc, a different layout).
    bool readBank(const iso9660::Reader &read, uint32_t sector, Bank &out, std::string &why);

    // The identity the cache is keyed by: sixteen hex digits of SHA-256 over the primary volume descriptor
    // (sector 16: the volume's name and dates) and the first sector of the bank. Cheap to read, and two
    // different images cannot share it by accident. Empty when the image cannot be read.
    std::string isoKey(const iso9660::Reader &read);

    // One cue rendered through snd989::Mixer as the game plays it: 48 kHz stereo s16, interleaved, cut when the
    // mixer goes quiet (or at three seconds -- a cue that never ends is not a menu sound).
    bool renderCue(const Bank &bank, int sound, std::vector<int16_t> &pcm, std::string &why);

    // A RIFF/WAVE file (PCM, 48 kHz, 2 channels, 16-bit) around `pcm`.
    std::vector<uint8_t> wavBytes(const std::vector<int16_t> &pcm);

    // The cache: <home>/cache/menu_sounds/<key>/<cue>.wav. `home` is the portable folder (config.json's).
    std::string cacheDir(const std::string &home, const std::string &key);
    // Every cue's file is there.
    bool cacheComplete(const std::string &dir);
    // Decode all four from the image and write them. False with `why` on the first failure (the directory may
    // then hold a partial set, which cacheComplete reports as absent).
    bool buildCache(const iso9660::Reader &read, const std::string &dir, std::string &why);
}
