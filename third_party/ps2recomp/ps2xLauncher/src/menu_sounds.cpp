#include "launcher/menu_sounds.h"

#include "launcher/sha256.h"
#include "runtime/snd989_mixer.h"
#include "runtime/socom2_bank.h"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>

namespace fs = std::filesystem;

namespace launcher::menusounds
{
    namespace
    {
        constexpr uint32_t kBankHandle = 0x00a00000u;   // the handle the game's own HUDUI load answers with
        constexpr size_t kBlockMax = 1u << 20;           // a menu bank is a few KB; anything bigger is not one
        constexpr size_t kVagMax = 4u << 20;
        constexpr size_t kRenderChunk = 480;             // 10 ms at 48 kHz
        constexpr size_t kRenderMaxFrames = 3u * snd989::kSampleRate;

        uint32_t le32(const uint8_t *p)
        {
            return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) | (static_cast<uint32_t>(p[2]) << 16) |
                   (static_cast<uint32_t>(p[3]) << 24);
        }

        void put32(std::vector<uint8_t> &out, uint32_t v)
        {
            out.push_back(static_cast<uint8_t>(v));
            out.push_back(static_cast<uint8_t>(v >> 8));
            out.push_back(static_cast<uint8_t>(v >> 16));
            out.push_back(static_cast<uint8_t>(v >> 24));
        }

        void put16(std::vector<uint8_t> &out, uint16_t v)
        {
            out.push_back(static_cast<uint8_t>(v));
            out.push_back(static_cast<uint8_t>(v >> 8));
        }
    }

    int cueSound(Cue cue)
    {
        // The bank's own names, read off its name table (menu_sounds.h has the whole list).
        switch (cue)
        {
        case Cue::Move: return 3;      // .SLIDE
        case Cue::Select: return 8;    // .METAL
        case Cue::Back: return 1;      // .BACK
        case Cue::Refuse: return 4;    // .NEG
        default: return -1;
        }
    }

    const char *cueFile(Cue cue)
    {
        switch (cue)
        {
        case Cue::Move: return "move.wav";
        case Cue::Select: return "select.wav";
        case Cue::Back: return "back.wav";
        case Cue::Refuse: return "refuse.wav";
        default: return "";
        }
    }

    bool readBank(const iso9660::Reader &read, uint32_t sector, Bank &out, std::string &why)
    {
        const uint64_t base = static_cast<uint64_t>(sector) * iso9660::kSectorBytes;
        uint8_t header[32];
        if (!read || !read(base, header, sizeof(header)))
        {
            why = "the image cannot be read at the bank's sector";
            return false;
        }
        // FileAttributes, as ps2xIOP's snd989.cpp reads it: type (1 = bank, 3 = bank + MIDI), chunk count,
        // then (offset, size) for chunk 0 and chunk 1.
        const uint32_t type = le32(header), chunks = le32(header + 4);
        const uint32_t blockOffset = le32(header + 8), blockBytes = le32(header + 12);
        const uint32_t vagOffset = le32(header + 16), vagBytes = le32(header + 20);
        if ((type != 1u && type != 3u) || chunks < 2u)
        {
            why = "no sound bank at that sector (not this disc, or not r0001)";
            return false;
        }
        if (blockBytes < 0x40u || blockBytes > kBlockMax || vagBytes == 0u || vagBytes > kVagMax)
        {
            why = "the bank's chunk sizes are not a menu bank's";
            return false;
        }
        out.block.assign(blockBytes, 0u);
        out.vag.assign(vagBytes, 0u);
        if (!read(base + blockOffset, out.block.data(), out.block.size()) || !read(base + vagOffset, out.vag.data(), out.vag.size()))
        {
            why = "the bank's chunks run past the end of the image";
            return false;
        }
        socom2_bank::Bank parsed;
        if (!socom2_bank::parse(out.block.data(), out.block.size(), parsed))
        {
            why = "the block at that sector is not an SBlk v3 bank";
            return false;
        }
        if (parsed.name != kBankName)
        {
            why = "the bank at that sector is " + (parsed.name.empty() ? std::string("unnamed") : parsed.name) + ", not HUDUI";
            return false;
        }
        return true;
    }

    std::string isoKey(const iso9660::Reader &read)
    {
        std::vector<uint8_t> bytes(2u * iso9660::kSectorBytes);
        if (!read || !read(16u * iso9660::kSectorBytes, bytes.data(), iso9660::kSectorBytes) ||
            !read(static_cast<uint64_t>(kHudUiSector) * iso9660::kSectorBytes, bytes.data() + iso9660::kSectorBytes, iso9660::kSectorBytes))
            return std::string();
        return sha256::hex(bytes.data(), bytes.size()).substr(0, 16);
    }

    bool renderCue(const Bank &bank, int sound, std::vector<int16_t> &pcm, std::string &why)
    {
        pcm.clear();
        snd989::Mixer mixer;
        if (!mixer.loadBank(kBankHandle, bank.block.data(), bank.block.size(), bank.vag.data(), bank.vag.size()))
        {
            why = "the mixer refused the bank";
            return false;
        }
        // As the game asks for a HUD click: full volume (0x400 = the sound's own), pan -1 = the sound's own.
        const uint32_t handle = mixer.play(kBankHandle, static_cast<uint32_t>(sound), 0x400, -1, 0, 0);
        if (handle == 0u)
        {
            why = "sound " + std::to_string(sound) + " would not play";
            return false;
        }
        std::vector<int16_t> chunk(2u * kRenderChunk);
        size_t frames = 0;
        while (frames < kRenderMaxFrames)
        {
            mixer.render(chunk.data(), kRenderChunk);
            pcm.insert(pcm.end(), chunk.begin(), chunk.end());
            frames += kRenderChunk;
            if (!mixer.isPlaying(handle) && mixer.activeVoices() == 0u)
                break;
        }
        // Trim the silence the last chunks carried past the sound's end, so the file is the cue and no tail.
        size_t lastLoud = 0;
        for (size_t i = 0; i < pcm.size(); ++i)
            if (pcm[i] > 8 || pcm[i] < -8)
                lastLoud = i;
        if (lastLoud == 0)
        {
            why = "sound " + std::to_string(sound) + " rendered silence";
            return false;
        }
        const size_t keepFrames = std::min(pcm.size() / 2u, lastLoud / 2u + snd989::kSampleRate / 100u);   // + 10 ms
        pcm.resize(keepFrames * 2u);
        return true;
    }

    std::vector<uint8_t> wavBytes(const std::vector<int16_t> &pcm)
    {
        const uint32_t dataBytes = static_cast<uint32_t>(pcm.size() * sizeof(int16_t));
        std::vector<uint8_t> out;
        out.reserve(44u + dataBytes);
        const char *riff = "RIFF";
        out.insert(out.end(), riff, riff + 4);
        put32(out, 36u + dataBytes);
        const char *wavefmt = "WAVEfmt ";
        out.insert(out.end(), wavefmt, wavefmt + 8);
        put32(out, 16u);                            // fmt chunk size
        put16(out, 1u);                             // PCM
        put16(out, 2u);                             // channels
        put32(out, snd989::kSampleRate);
        put32(out, snd989::kSampleRate * 4u);       // bytes per second
        put16(out, 4u);                             // block align
        put16(out, 16u);                            // bits per sample
        const char *data = "data";
        out.insert(out.end(), data, data + 4);
        put32(out, dataBytes);
        for (const int16_t s : pcm)
            put16(out, static_cast<uint16_t>(s));
        return out;
    }

    std::string cacheDir(const std::string &home, const std::string &key)
    {
        return (fs::path(home) / "cache" / "menu_sounds" / key).string();
    }

    bool cacheComplete(const std::string &dir)
    {
        std::error_code ec;
        for (int i = 0; i < static_cast<int>(Cue::Count); ++i)
        {
            const fs::path file = fs::path(dir) / cueFile(static_cast<Cue>(i));
            if (!fs::is_regular_file(file, ec) || fs::file_size(file, ec) <= 44u)
                return false;
        }
        return true;
    }

    bool buildCache(const iso9660::Reader &read, const std::string &dir, std::string &why)
    {
        Bank bank;
        if (!readBank(read, kHudUiSector, bank, why))
            return false;
        std::error_code ec;
        fs::create_directories(dir, ec);
        for (int i = 0; i < static_cast<int>(Cue::Count); ++i)
        {
            const Cue cue = static_cast<Cue>(i);
            std::vector<int16_t> pcm;
            if (!renderCue(bank, cueSound(cue), pcm, why))
                return false;
            const std::vector<uint8_t> wav = wavBytes(pcm);
            const fs::path file = fs::path(dir) / cueFile(cue);
            std::ofstream out(file, std::ios::binary | std::ios::trunc);
            out.write(reinterpret_cast<const char *>(wav.data()), static_cast<std::streamsize>(wav.size()));
            if (!out)
            {
                why = "cannot write " + file.string();
                return false;
            }
        }
        return true;
    }
}
