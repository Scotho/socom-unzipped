// Sprint 8 Task 1: the whole file is Windows-only. On Linux src/posix_glue.cpp defines the same
// win32glue interface, so this translation unit must contribute nothing there -- the per-function
// "#else" arms below are unreachable now and their behaviour lives in posix_glue.cpp.
#ifdef _WIN32
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

    // ---- Sprint 8 Goal 9, third pass: the custom title bar -------------------------------------------------
    // The technique: keep WS_OVERLAPPEDWINDOW (so Windows keeps resize, snap, the drop shadow and the
    // animations) and take the caption away by answering WM_NCCALCSIZE with a client area that covers the
    // whole window. WM_NCHITTEST then has to say which part of our own bar the mouse is over -- that answer
    // comes from ui::chromeHitTest through the callback, the same function the drawing uses.
    namespace
    {
        HWND g_chromeWindow = nullptr;
        WNDPROC g_originalProc = nullptr;
        ChromeHitFn g_hitTest = nullptr;

        // ui::ChromeHit, as an int, without including the header here (windows.h and raylib.h do not mix,
        // and this file must stay free of both the UI and raylib).
        enum ChromeHitCode
        {
            HitClient = 0,
            HitCaption,
            HitMinimize,
            HitMaximize,
            HitClose,
            HitUnsavedPill,
            HitLeft,
            HitRight,
            HitTop,
            HitBottom,
            HitTopLeft,
            HitTopRight,
            HitBottomLeft,
            HitBottomRight
        };

        int frameThickness(HWND window)
        {
            // The maximised window hangs its frame off-screen; without this inset the top row of our bar
            // would be cut off by exactly that much.
            UINT dpi = 96;
            HMODULE user32 = GetModuleHandleW(L"user32.dll");
            if (user32 != nullptr)
            {
                using GetDpiForWindowFn = UINT(WINAPI *)(HWND);
                auto getDpi = reinterpret_cast<GetDpiForWindowFn>(
                    reinterpret_cast<void *>(GetProcAddress(user32, "GetDpiForWindow")));
                if (getDpi != nullptr)
                    dpi = getDpi(window);
                using GetMetricsFn = int(WINAPI *)(int, UINT);
                auto getMetric = reinterpret_cast<GetMetricsFn>(
                    reinterpret_cast<void *>(GetProcAddress(user32, "GetSystemMetricsForDpi")));
                if (getMetric != nullptr)
                    return getMetric(SM_CXSIZEFRAME, dpi) + getMetric(SM_CXPADDEDBORDER, dpi);
            }
            return GetSystemMetrics(SM_CXSIZEFRAME) + GetSystemMetrics(SM_CXPADDEDBORDER);
        }

        LRESULT CALLBACK chromeProc(HWND window, UINT message, WPARAM wParam, LPARAM lParam)
        {
            switch (message)
            {
            case WM_NCCALCSIZE:
                if (wParam == TRUE)
                {
                    // The client area becomes the whole window: no caption, no top border drawn by Windows.
                    if (IsZoomed(window))
                    {
                        NCCALCSIZE_PARAMS *params = reinterpret_cast<NCCALCSIZE_PARAMS *>(lParam);
                        const int inset = frameThickness(window);
                        params->rgrc[0].left += inset;
                        params->rgrc[0].top += inset;
                        params->rgrc[0].right -= inset;
                        params->rgrc[0].bottom -= inset;
                    }
                    return 0;
                }
                break;
            case WM_NCHITTEST:
            {
                if (g_hitTest != nullptr)
                {
                    POINT p{static_cast<int>(static_cast<short>(LOWORD(lParam))), static_cast<int>(static_cast<short>(HIWORD(lParam)))};
                    ScreenToClient(window, &p);
                    RECT client{};
                    GetClientRect(window, &client);
                    switch (g_hitTest(p.x, p.y, client.right - client.left, client.bottom - client.top))
                    {
                    case HitCaption: return HTCAPTION;
                    case HitLeft: return HTLEFT;
                    case HitRight: return HTRIGHT;
                    case HitTop: return HTTOP;
                    case HitBottom: return HTBOTTOM;
                    case HitTopLeft: return HTTOPLEFT;
                    case HitTopRight: return HTTOPRIGHT;
                    case HitBottomLeft: return HTBOTTOMLEFT;
                    case HitBottomRight: return HTBOTTOMRIGHT;
                    default: return HTCLIENT;   // our own buttons and the pages: raylib gets the clicks
                    }
                }
                return HTCLIENT;
            }
            default:
                break;
            }
            return CallWindowProcW(g_originalProc, window, message, wParam, lParam);
        }
    }

    bool installCustomChrome(void *windowHandle, ChromeHitFn hitTest)
    {
        HWND window = reinterpret_cast<HWND>(windowHandle);
        if (window == nullptr || g_originalProc != nullptr)
            return window != nullptr;
        g_chromeWindow = window;
        g_hitTest = hitTest;
        g_originalProc = reinterpret_cast<WNDPROC>(
            SetWindowLongPtrW(window, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(chromeProc)));
        if (g_originalProc == nullptr)
            return false;
        // Ask for the frame to be recalculated now that WM_NCCALCSIZE answers differently.
        SetWindowPos(window, nullptr, 0, 0, 0, 0,
                     SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
        return true;
    }

    void minimizeWindow()
    {
        if (g_chromeWindow != nullptr)
            ShowWindow(g_chromeWindow, SW_MINIMIZE);
    }

    void maximizeToggleWindow()
    {
        if (g_chromeWindow == nullptr)
            return;
        ShowWindow(g_chromeWindow, IsZoomed(g_chromeWindow) ? SW_RESTORE : SW_MAXIMIZE);
    }

    bool isWindowMaximized()
    {
        return g_chromeWindow != nullptr && IsZoomed(g_chromeWindow) != 0;
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
#endif // _WIN32
