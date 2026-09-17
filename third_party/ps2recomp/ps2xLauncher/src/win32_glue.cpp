#include "win32_glue.h"

#include <ctime>
#include <filesystem>
#include <vector>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <commdlg.h>
#include <shellapi.h>
#endif

namespace fs = std::filesystem;

namespace win32glue
{
    std::string exeDirectory()
    {
#ifdef _WIN32
        wchar_t buf[MAX_PATH];
        const DWORD n = GetModuleFileNameW(nullptr, buf, MAX_PATH);
        if (n > 0 && n < MAX_PATH)
            return fs::path(buf).parent_path().string();
#endif
        return fs::current_path().string();
    }

    std::string browseForIso()
    {
#ifdef _WIN32
        char file[MAX_PATH] = {};
        OPENFILENAMEA ofn{};
        ofn.lStructSize = sizeof(ofn);
        ofn.lpstrFilter = "Disc images (*.iso;*.bin)\0*.iso;*.bin\0All files\0*.*\0";
        ofn.lpstrFile = file;
        ofn.nMaxFile = MAX_PATH;
        ofn.lpstrTitle = "Choose the SOCOM II ISO";
        ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR;
        if (GetOpenFileNameA(&ofn))
            return file;
#endif
        return {};
    }

    void openFolder(const std::string &path)
    {
#ifdef _WIN32
        ShellExecuteA(nullptr, "open", path.c_str(), nullptr, nullptr, SW_SHOWNORMAL);
#else
        (void)path;
#endif
    }

    std::string stamp()
    {
        char buf[32];
        const std::time_t t = std::time(nullptr);
        std::tm tm{};
#ifdef _WIN32
        localtime_s(&tm, &t);
#else
        localtime_r(&t, &tm);
#endif
        std::strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", &tm);
        return buf;
    }

    bool GameProcess::running() const
    {
#ifdef _WIN32
        if (!process)
            return false;
        return WaitForSingleObject(static_cast<HANDLE>(process), 0) == WAIT_TIMEOUT;
#else
        return false;
#endif
    }

    int GameProcess::exitCode() const
    {
#ifdef _WIN32
        if (!process)
            return 0;
        DWORD code = 0;
        if (!GetExitCodeProcess(static_cast<HANDLE>(process), &code) || code == STILL_ACTIVE)
            return 0;
        return static_cast<int>(code);
#else
        return 0;
#endif
    }

    void GameProcess::close()
    {
#ifdef _WIN32
        if (process)
            CloseHandle(static_cast<HANDLE>(process));
        if (log)
            CloseHandle(static_cast<HANDLE>(log));
#endif
        process = nullptr;
        log = nullptr;
    }

    bool startGame(const std::string &dirStr, const launcher::Config &config, GameProcess &out)
    {
        out.error.clear();
#ifdef _WIN32
        const fs::path dir(dirStr);
        const fs::path exe = dir / "socom2.exe";
        const fs::path elf = dir / "socom2_game.elf";
        if (!fs::exists(exe))
        {
            out.error = "socom2.exe is not next to the launcher";
            return false;
        }
        if (!fs::exists(elf))
        {
            out.error = "socom2_game.elf is not next to the launcher";
            return false;
        }
        std::error_code ec;
        fs::create_directories(dir / "logs", ec);
        fs::create_directories(dir / "cards", ec);
        // the environment: the current block plus our knobs (ours win)
        const std::vector<std::string> ours = launcher::environmentFor(config);
        std::string block;
        {
            std::vector<std::string> merged;
            LPWCH env = GetEnvironmentStringsW();
            for (LPWCH p = env; p && *p;)
            {
                const std::wstring w(p);
                p += w.size() + 1;
                const int n = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), -1, nullptr, 0, nullptr, nullptr);
                std::string s(static_cast<size_t>(n > 0 ? n - 1 : 0), '\0');
                if (n > 1)
                    WideCharToMultiByte(CP_UTF8, 0, w.c_str(), -1, s.data(), n, nullptr, nullptr);
                const size_t eq = s.find('=');
                const std::string key = eq == std::string::npos ? s : s.substr(0, eq);
                bool overridden = false;
                for (const std::string &o : ours)
                    if (o.rfind(key + "=", 0) == 0)
                        overridden = true;
                if (!overridden && !key.empty() && key[0] != '=')
                    merged.push_back(s);
            }
            if (env)
                FreeEnvironmentStringsW(env);
            for (const std::string &o : ours)
                merged.push_back(o);
            for (const std::string &m : merged)
            {
                block += m;
                block.push_back('\0');
            }
            block.push_back('\0');
        }
        out.logPath = (dir / "logs" / ("run_" + stamp() + ".log")).string();
        SECURITY_ATTRIBUTES sa{};
        sa.nLength = sizeof(sa);
        sa.bInheritHandle = TRUE;
        HANDLE log = CreateFileA(out.logPath.c_str(), GENERIC_WRITE, FILE_SHARE_READ, &sa, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (log == INVALID_HANDLE_VALUE)
        {
            out.error = "cannot create the log file";
            return false;
        }
        STARTUPINFOA si{};
        si.cb = sizeof(si);
        si.dwFlags = STARTF_USESTDHANDLES;
        si.hStdOutput = log;
        si.hStdError = log;
        si.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
        PROCESS_INFORMATION pi{};
        std::string cmd = "\"" + exe.string() + "\" \"" + elf.string() + "\"";
        std::vector<char> cmdBuf(cmd.begin(), cmd.end());
        cmdBuf.push_back('\0');
        const BOOL ok = CreateProcessA(exe.string().c_str(), cmdBuf.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW,
                                       block.data(), dir.string().c_str(), &si, &pi);
        if (!ok)
        {
            CloseHandle(log);
            out.error = "CreateProcess failed (" + std::to_string(GetLastError()) + ")";
            return false;
        }
        CloseHandle(pi.hThread);
        out.process = pi.hProcess;
        out.log = log;
        return true;
#else
        (void)dirStr; (void)config;
        out.error = "launching is Windows-only in this build";
        return false;
#endif
    }

    void terminate(GameProcess &game)
    {
#ifdef _WIN32
        if (game.process)
            TerminateProcess(static_cast<HANDLE>(game.process), 0);
#else
        (void)game;
#endif
    }
}
