#include "ps2x/preflight.h"

#include "launcher/iso9660.h"
#include "launcher/sha256.h"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <fstream>
#include <system_error>
#include <vector>

namespace Preflight
{
    namespace fs = std::filesystem;

    fs::path findDisc(const fs::path &elfPath, const std::string &cdImageEnv)
    {
        if (!cdImageEnv.empty())
            return fs::path(cdImageEnv);
        std::error_code ec;
        fs::path absolute = fs::absolute(elfPath, ec);
        if (ec)
            absolute = elfPath;
        const fs::path elfDir = absolute.parent_path();
        for (const fs::path &dir : {elfDir, elfDir.parent_path()})
        {
            if (dir.empty())
                continue;
            std::error_code iterEc;
            for (fs::directory_iterator it(dir, iterEc), end; !iterEc && it != end; it.increment(iterEc))
            {
                std::string ext = it->path().extension().string();
                std::transform(ext.begin(), ext.end(), ext.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
                if (ext == ".iso")
                    return it->path();
            }
        }
        return {};
    }

    bool directoryWritable(const fs::path &dir, std::string &why)
    {
        std::error_code ec;
        fs::create_directories(dir, ec);
        if (ec || !fs::is_directory(dir, ec))
        {
            why = "cannot create " + dir.string();
            return false;
        }
        const fs::path probe = dir / ".ps2x_write_probe";
        {
            std::ofstream out(probe, std::ios::binary | std::ios::trunc);
            out << 'x';
            out.flush();
            if (!out)
            {
                why = "cannot write in " + dir.string();
                return false;
            }
        }
        fs::remove(probe, ec);
        return true;
    }

    Result run(const Input &input)
    {
        Result r;
        std::error_code ec;
        if (!fs::is_regular_file(input.elfPath, ec))
        {
            r.code = ExitCodes::kElfMissing;
            r.detail = input.elfPath.string();
            return r;
        }
        std::string why;
        if (!directoryWritable(input.cardDir, why))
        {
            r.code = ExitCodes::kCardDirUnwritable;
            r.detail = why;
            return r;
        }
        if (!input.checkDisc)
            return r;

        r.disc = findDisc(input.elfPath, input.cdImageEnv);
        if (r.disc.empty())
        {
            r.code = ExitCodes::kDiscNotFound;
            r.detail = "no .iso beside " + input.elfPath.filename().string() + " or one folder up, and PS2X_CD_IMAGE is not set";
            return r;
        }
        if (!fs::is_regular_file(r.disc, ec))
        {
            r.code = ExitCodes::kDiscNotFound;
            r.detail = r.disc.string();
            return r;
        }
        const iso9660::Reader read = iso9660::fileReader(r.disc.string());
        if (!read)
        {
            r.code = ExitCodes::kDiscNotFound;
            r.detail = "cannot open " + r.disc.string();
            return r;
        }
        iso9660::FileEntry entry;
        std::vector<uint8_t> bytes;
        if (!iso9660::findRootFile(read, input.discElfName, entry) || !iso9660::readFile(read, entry, bytes))
        {
            r.code = ExitCodes::kDiscNotR0001;
            r.detail = "no readable " + input.discElfName + " in " + r.disc.string();
            return r;
        }
        const std::string digest = sha256::hex(bytes.data(), bytes.size());
        if (digest != input.expectedElfSha256)
        {
            r.code = ExitCodes::kDiscNotR0001;
            r.detail = input.discElfName + " in " + r.disc.string() + " hashes to " + digest;
            return r;
        }
        return r;
    }

    std::string logLine(const Result &result)
    {
        const ExitCodes::Entry *e = ExitCodes::find(result.code);
        return "[preflight] exit " + std::to_string(result.code) + " " + (e ? e->slug : "unknown") + ": " +
               (e ? e->sentence : "") + " (" + result.detail + ")";
    }
}
