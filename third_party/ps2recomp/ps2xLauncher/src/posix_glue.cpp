// The launcher's Unix half of the win32glue interface (Sprint 8 Task 1).
//
// STUB: every function here returns exactly what win32_glue.cpp's non-Windows "#else" arm returned
// before this file existed, so the launcher links, opens its window and reads its config on Linux while
// doing nothing platform-specific. Sprint 8 Task 4 replaces these bodies with the real ones (design item
// 4: /proc/self/exe, posix_spawn with the merged environment and a redirected log, zenity, xdg-open).
//
// The name win32glue stays: one header, one interface, two implementations.
#ifndef _WIN32

#include "win32_glue.h"

#include <ctime>
#include <filesystem>

namespace fs = std::filesystem;

namespace win32glue
{
    std::string exeDirectory()
    {
        // Task 4: /proc/self/exe. Until then, the same fallback the Windows file used when
        // GetModuleFileNameW failed.
        return fs::current_path().string();
    }

    std::string browseForIso()
    {
        // Task 4: zenity --file-selection when zenity exists. Empty means "keep what was typed".
        return {};
    }

    void openFolder(const std::string &path)
    {
        // Task 4: xdg-open.
        (void)path;
    }

    std::string stamp()
    {
        char buf[32];
        const std::time_t t = std::time(nullptr);
        std::tm tm{};
        localtime_r(&t, &tm);
        std::strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", &tm);
        return buf;
    }

    bool GameProcess::running() const
    {
        return false;
    }

    int GameProcess::exitCode() const
    {
        return 0;
    }

    void GameProcess::close()
    {
        process = nullptr;
        log = nullptr;
    }

    bool startGame(const std::string &dirStr, const launcher::Config &config, GameProcess &out)
    {
        out.error.clear();
        (void)dirStr;
        (void)config;
        out.error = "launching is not implemented on this platform yet (Sprint 8 Task 4)";
        return false;
    }

    void terminate(GameProcess &game)
    {
        (void)game;
    }
}

#endif // !_WIN32
