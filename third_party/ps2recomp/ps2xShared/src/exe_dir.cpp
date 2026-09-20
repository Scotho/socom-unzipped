#include "ps2x/exe_dir.h"

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <unistd.h>
#endif

namespace ExeDir
{
    std::filesystem::path get()
    {
#ifdef _WIN32
        wchar_t buf[32768];
        const DWORD n = GetModuleFileNameW(nullptr, buf, static_cast<DWORD>(sizeof(buf) / sizeof(buf[0])));
        if (n > 0 && n < sizeof(buf) / sizeof(buf[0]))
            return std::filesystem::path(buf).parent_path();
#else
        char buf[4096];
        const ssize_t n = ::readlink("/proc/self/exe", buf, sizeof(buf) - 1);
        if (n > 0 && static_cast<size_t>(n) < sizeof(buf))
        {
            buf[n] = '\0';
            return std::filesystem::path(buf).parent_path();
        }
#endif
        // No answer (a container without /proc, a BSD): what win32glue::exeDirectory falls back to.
        std::error_code ec;
        return std::filesystem::current_path(ec);
    }

    const char *platformName()
    {
#if defined(_WIN32)
        return "windows";
#elif defined(__linux__)
        return "linux";
#else
        return "other";
#endif
    }
}
