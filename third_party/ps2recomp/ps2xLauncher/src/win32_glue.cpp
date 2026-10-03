// Sprint 8 Task 1: the whole file is Windows-only. On Linux src/posix_glue.cpp defines the same
// win32glue interface, so this translation unit must contribute nothing there -- the per-function
// "#else" arms below are unreachable now and their behaviour lives in posix_glue.cpp.
#ifdef _WIN32
#include "win32_glue.h"
#include "ps2x/knobs.h"

#include <ctime>
#include <cwchar>
#include <filesystem>
#include <string>
#include <vector>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>   // Sprint 18 T4: resolveIpv4 (getaddrinfo) and listAdapters (iphlpapi) need Winsock 2 before windows.h
#include <ws2tcpip.h>
#include <windows.h>
#include <commdlg.h>
#include <iphlpapi.h>   // Sprint 18 T4: GetAdaptersAddresses, for the PCSX2 adapter (EthDevice)
#include <shellapi.h>
#include <tlhelp32.h>   // the persona-card review, finding 5: the headless creator looks for a running game
#include <winhttp.h>
#include <xinput.h>   // Sprint 10 Q4: XINPUT_STATE for the guide button (the DLL is loaded by hand, never linked)
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

    std::string browseForPcsx2()
    {
#ifdef _WIN32
        char file[MAX_PATH] = {};
        OPENFILENAMEA ofn{};
        ofn.lStructSize = sizeof(ofn);
        ofn.lpstrFilter = "PCSX2 (pcsx2-qt.exe)\0pcsx2-qt.exe\0Programs (*.exe)\0*.exe\0";
        ofn.lpstrFile = file;
        ofn.nMaxFile = MAX_PATH;
        ofn.lpstrTitle = "Choose your pcsx2-qt.exe";
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

    bool gameRunningFrom(const std::string &dir, std::string &which)
    {
        which.clear();
        std::error_code ec;
        const std::string home = fs::absolute(fs::path(dir), ec).string();
        HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if (snap == INVALID_HANDLE_VALUE)
            return false;
        PROCESSENTRY32W entry{};
        entry.dwSize = sizeof(entry);
        for (BOOL more = Process32FirstW(snap, &entry); more && which.empty(); more = Process32NextW(snap, &entry))
        {
            // A process this user cannot open is not one the launcher started from this folder.
            HANDLE p = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, entry.th32ProcessID);
            if (p == nullptr)
                continue;
            wchar_t image[MAX_PATH * 4];
            DWORD size = static_cast<DWORD>(sizeof(image) / sizeof(image[0]));
            if (QueryFullProcessImageNameW(p, 0, image, &size))
            {
                const std::string path = fs::path(std::wstring(image, size)).string();
                if (launcher::isGameImage(home, path, "socom2.exe"))
                    which = path + " (pid " + std::to_string(entry.th32ProcessID) + ")";
            }
            CloseHandle(p);
        }
        CloseHandle(snap);
        return !which.empty();
    }

    bool startGame(const std::string &dirStr, const launcher::Config &config, GameProcess &out)
    {
        out.error.clear();
#ifdef _WIN32
        const fs::path dir(dirStr);
        // Issue #69: the chosen GAME VERSION's own pair, not socom2.exe + socom2_game.elf whatever it said.
        const launcher::GameFiles files = launcher::gameFilesFor(config.gameRevision, "socom2.exe");
        const fs::path exe = dir / files.exe;
        const fs::path elf = dir / files.elf;
        if (!fs::exists(exe))
        {
            out.error = files.exe + " is not next to the launcher";
            return false;
        }
        if (!fs::exists(elf))
        {
            out.error = files.elf + " is not next to the launcher";
            return false;
        }
        std::error_code ec;
        fs::create_directories(dir / "logs", ec);
        fs::create_directories(dir / "cards", ec);
        // the environment: the current block plus our knobs (ours win). Sprint 9 Goal 3 (R156): an inherited
        // PS2X_* variable reaches the game only when this launcher was itself started in developer mode.
        const std::vector<std::string> ours = launcher::environmentFor(config);
        const bool keepInheritedKnobs = ps2x::knobs::devMode();   // R156
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
                if (!overridden && !key.empty() && key[0] != '=' && (keepInheritedKnobs || !launcher::isKnobKey(key)))
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

    // ---- Sprint 10 Q4: the window switch ------------------------------------------------------------------
    namespace
    {
        // XInputGetStateEx: ordinal 100 of xinput1_4.dll (and 1_3), the documented signature with the guide
        // bit 0x0400 in wButtons. Loaded once; a machine without it (documented as possible) reads "no".
        struct XInputGuide
        {
            bool tried = false;
            HMODULE dll = nullptr;
            DWORD(WINAPI *getStateEx)(DWORD, XINPUT_STATE *) = nullptr;
            // A user index that answered ERROR_DEVICE_NOT_CONNECTED is asked again only every 120 frames:
            // XInput's own guidance, a disconnected slot is the slow one to poll.
            unsigned skip[4] = {};
        };
        XInputGuide g_xinput;
        constexpr WORD kXInputGuideBit = 0x0400;

        void loadXInputGuide()
        {
            if (g_xinput.tried)
                return;
            g_xinput.tried = true;
            for (const wchar_t *name : {L"xinput1_4.dll", L"xinput1_3.dll"})
            {
                g_xinput.dll = LoadLibraryW(name);
                if (g_xinput.dll == nullptr)
                    continue;
                g_xinput.getStateEx = reinterpret_cast<DWORD(WINAPI *)(DWORD, XINPUT_STATE *)>(
                    reinterpret_cast<void *>(GetProcAddress(g_xinput.dll, reinterpret_cast<LPCSTR>(100))));
                if (g_xinput.getStateEx != nullptr)
                    return;
                FreeLibrary(g_xinput.dll);
                g_xinput.dll = nullptr;
            }
        }

        // The first visible, unowned, titled top-level window of a process: the game's raylib window.
        struct FindByPid
        {
            DWORD pid;
            HWND found;
        };
        BOOL CALLBACK findWindowByPid(HWND hwnd, LPARAM lParam)
        {
            FindByPid *f = reinterpret_cast<FindByPid *>(lParam);
            DWORD pid = 0;
            GetWindowThreadProcessId(hwnd, &pid);
            if (pid != f->pid || !IsWindowVisible(hwnd) || GetWindow(hwnd, GW_OWNER) != nullptr || GetWindowTextLengthW(hwnd) == 0)
                return TRUE;
            f->found = hwnd;
            return FALSE;
        }

        bool bringToFront(HWND target)
        {
            const HWND front = GetForegroundWindow();
            if (front == target)
                return true;
            // A process that is not in front may not take the foreground (SetForegroundWindow's rules) unless
            // its input queue is attached to the one that is. Attached for the call only.
            const DWORD me = GetCurrentThreadId();
            const DWORD frontThread = front != nullptr ? GetWindowThreadProcessId(front, nullptr) : 0;
            const bool attached = frontThread != 0 && frontThread != me && AttachThreadInput(frontThread, me, TRUE);
            if (IsIconic(target))
                ShowWindow(target, SW_RESTORE);
            BringWindowToTop(target);
            SetForegroundWindow(target);
            if (attached)
                AttachThreadInput(frontThread, me, FALSE);
            return GetForegroundWindow() == target;
        }
    }

    bool xinputGuideReadable()
    {
        loadXInputGuide();
        return g_xinput.getStateEx != nullptr;
    }

    bool xinputGuideDown()
    {
        loadXInputGuide();
        if (g_xinput.getStateEx == nullptr)
            return false;
        bool down = false;
        for (DWORD user = 0; user < 4; ++user)
        {
            if (g_xinput.skip[user] > 0)
            {
                --g_xinput.skip[user];
                continue;
            }
            XINPUT_STATE state{};
            const DWORD result = g_xinput.getStateEx(user, &state);
            if (result != ERROR_SUCCESS)
            {
                g_xinput.skip[user] = 120;
                continue;
            }
            down = down || (state.Gamepad.wButtons & kXInputGuideBit) != 0;
        }
        return down;
    }

    bool toggleForeground(void *launcherWindow, const GameProcess &game, std::string &why)
    {
        const HWND mine = reinterpret_cast<HWND>(launcherWindow);
        if (mine == nullptr || game.process == nullptr)
        {
            why = "no game window to switch to";
            return false;
        }
        FindByPid f{GetProcessId(static_cast<HANDLE>(game.process)), nullptr};
        EnumWindows(findWindowByPid, reinterpret_cast<LPARAM>(&f));
        if (f.found == nullptr)
        {
            why = "the game has no window yet";
            return false;
        }
        const HWND target = GetForegroundWindow() == mine ? f.found : mine;
        if (!bringToFront(target))
        {
            why = target == mine ? "Windows refused to bring the launcher forward" : "Windows refused to bring the game forward";
            return false;
        }
        return true;
    }

    // ---- Sprint 9 Goal 8: one HTTPS request (the bug report, the server's status line) ---------------------
    // WinHTTP, which ships with Windows: no vendored TLS. Certificate validation is WinHTTP's default and is
    // left alone -- nothing here sets WINHTTP_OPTION_SECURITY_FLAGS, so an expired, self-signed or
    // wrong-host certificate fails the request (ERROR_WINHTTP_SECURE_FAILURE) and the report is saved to disk.
    namespace
    {
        std::wstring widen(const std::string &s)
        {
            if (s.empty())
                return {};
            const int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), nullptr, 0);
            std::wstring out(static_cast<size_t>(n > 0 ? n : 0), L'\0');
            if (n > 0)
                MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), out.data(), n);
            return out;
        }

        struct InternetHandle
        {
            HINTERNET h = nullptr;
            ~InternetHandle()
            {
                if (h != nullptr)
                    WinHttpCloseHandle(h);
            }
        };

// The system's proxy settings where WinHTTP can read them itself (Windows 8.1 and later).
#ifdef WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY
        constexpr DWORD kProxyAccess = WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY;
#else
        constexpr DWORD kProxyAccess = WINHTTP_ACCESS_TYPE_DEFAULT_PROXY;
#endif

        std::string winHttpError(const char *what)
        {
            return std::string(what) + " failed (WinHTTP error " + std::to_string(GetLastError()) + ")";
        }
    }

    HttpResult httpRequest(const std::string &method, const std::string &url, const std::string &body, int timeoutMs)
    {
        HttpResult out;
        const std::wstring wideUrl = widen(url);
        wchar_t host[256] = {};
        wchar_t path[2048] = {};
        URL_COMPONENTS parts{};
        parts.dwStructSize = sizeof(parts);
        parts.lpszHostName = host;
        parts.dwHostNameLength = static_cast<DWORD>(sizeof(host) / sizeof(host[0]));
        parts.lpszUrlPath = path;
        parts.dwUrlPathLength = static_cast<DWORD>(sizeof(path) / sizeof(path[0]));
        if (!WinHttpCrackUrl(wideUrl.c_str(), static_cast<DWORD>(wideUrl.size()), 0, &parts))
        {
            out.error = "not a URL: " + url;
            return out;
        }
        const bool secure = parts.nScheme == INTERNET_SCHEME_HTTPS;
        const std::wstring hostName = host;
        if (!secure && hostName != L"127.0.0.1" && hostName != L"localhost")
        {
            out.error = "plain http is refused for anything but a loopback test server";
            return out;
        }

        InternetHandle session, connection, request;
        session.h = WinHttpOpen(L"SOCOM-Unzipped-Launcher/1.0", kProxyAccess, WINHTTP_NO_PROXY_NAME,
                                WINHTTP_NO_PROXY_BYPASS, 0);
        if (session.h == nullptr)
        {
            out.error = winHttpError("WinHttpOpen");
            return out;
        }
        const int each = timeoutMs > 0 ? timeoutMs : 15000;
        WinHttpSetTimeouts(session.h, each, each, each, each);
        connection.h = WinHttpConnect(session.h, host, parts.nPort, 0);
        if (connection.h == nullptr)
        {
            out.error = winHttpError("WinHttpConnect");
            return out;
        }
        request.h = WinHttpOpenRequest(connection.h, widen(method).c_str(), path[0] != L'\0' ? path : L"/", nullptr,
                                       WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, secure ? WINHTTP_FLAG_SECURE : 0);
        if (request.h == nullptr)
        {
            out.error = winHttpError("WinHttpOpenRequest");
            return out;
        }
        const wchar_t *headers = body.empty() ? WINHTTP_NO_ADDITIONAL_HEADERS : L"Content-Type: application/json\r\n";
        const DWORD headersLength = body.empty() ? 0 : static_cast<DWORD>(-1L);
        if (!WinHttpSendRequest(request.h, headers, headersLength,
                                body.empty() ? WINHTTP_NO_REQUEST_DATA : const_cast<char *>(body.data()),
                                static_cast<DWORD>(body.size()), static_cast<DWORD>(body.size()), 0) ||
            !WinHttpReceiveResponse(request.h, nullptr))
        {
            out.error = winHttpError("the request");
            return out;
        }

        DWORD status = 0, size = sizeof(status);
        if (!WinHttpQueryHeaders(request.h, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, WINHTTP_HEADER_NAME_BY_INDEX,
                                 &status, &size, WINHTTP_NO_HEADER_INDEX))
        {
            out.error = winHttpError("reading the status");
            return out;
        }
        wchar_t retry[32] = {};
        DWORD retrySize = sizeof(retry) - sizeof(wchar_t);
        if (WinHttpQueryHeaders(request.h, WINHTTP_QUERY_CUSTOM, L"Retry-After", retry, &retrySize, WINHTTP_NO_HEADER_INDEX))
        {
            const long seconds = std::wcstol(retry, nullptr, 10);
            out.retryAfter = seconds > 0 && seconds < 7 * 24 * 3600 ? static_cast<int>(seconds) : 0;
        }

        constexpr size_t kMaxBody = 1024u * 1024u;
        const ULONGLONG deadline = GetTickCount64() + static_cast<ULONGLONG>(each);
        for (;;)
        {
            DWORD available = 0;
            if (!WinHttpQueryDataAvailable(request.h, &available) || available == 0)
                break;
            std::string chunk(available, '\0');
            DWORD got = 0;
            if (!WinHttpReadData(request.h, chunk.data(), available, &got) || got == 0)
                break;
            out.body.append(chunk.data(), got);
            if (out.body.size() > kMaxBody || GetTickCount64() > deadline)
                break;
        }
        out.status = static_cast<int>(status);
        return out;
    }

    namespace
    {
        std::string narrow(const wchar_t *w, int length = -1)
        {
            if (w == nullptr || length == 0)
                return {};
            const int n = WideCharToMultiByte(CP_UTF8, 0, w, length, nullptr, 0, nullptr, nullptr);
            if (n <= 0)
                return {};
            std::string out(static_cast<size_t>(n), '\0');
            WideCharToMultiByte(CP_UTF8, 0, w, length, out.data(), n, nullptr, nullptr);
            if (length < 0 && !out.empty() && out.back() == '\0')
                out.pop_back();
            return out;
        }
    }

    // Sprint 16 R2a (#71): the same WinHTTP calls as httpRequest, streamed to a file in 64 KiB chunks with no
    // cap, the caller's User-Agent, a GET only, and Content-Length honoured. Sprint 18 T4: one request of
    // httpDownloadFollowing's loop -- a 3xx comes back as redirectRefusal with its Location in `location`, and the
    // path buffer is sized to the URL (a githubusercontent asset URL carries a query well past 2 KB of signature).
    static DownloadResult downloadOnce(const std::string &url, const std::filesystem::path &dest, const std::string &userAgent,
                                       int timeoutMs, const DownloadProgress &progress, std::string &location)
    {
        DownloadResult out;
        location.clear();
        const std::wstring wideUrl = widen(url);
        wchar_t host[256] = {};
        std::vector<wchar_t> path(wideUrl.size() + 1, L'\0');
        std::vector<wchar_t> extra(wideUrl.size() + 1, L'\0');
        URL_COMPONENTS parts{};
        parts.dwStructSize = sizeof(parts);
        parts.lpszHostName = host;
        parts.dwHostNameLength = static_cast<DWORD>(sizeof(host) / sizeof(host[0]));
        parts.lpszUrlPath = path.data();
        parts.dwUrlPathLength = static_cast<DWORD>(path.size());
        parts.lpszExtraInfo = extra.data();
        parts.dwExtraInfoLength = static_cast<DWORD>(extra.size());
        if (!WinHttpCrackUrl(wideUrl.c_str(), static_cast<DWORD>(wideUrl.size()), 0, &parts) ||
            (parts.nScheme != INTERNET_SCHEME_HTTPS && parts.nScheme != INTERNET_SCHEME_HTTP))
        {
            out.error = "not an http(s) URL: " + url;
            return out;
        }
        const bool secure = parts.nScheme == INTERNET_SCHEME_HTTPS;
        // The object requested: the path and its query (?...), which the crack hands back separately.
        std::wstring object = path[0] != L'\0' ? std::wstring(path.data()) : std::wstring(L"/");
        object += extra.data();

        InternetHandle session, connection, request;
        session.h = WinHttpOpen(widen(userAgent).c_str(), kProxyAccess, WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
        if (session.h == nullptr)
        {
            out.error = winHttpError("WinHttpOpen");
            return out;
        }
        const int each = timeoutMs > 0 ? timeoutMs : 300000;
        WinHttpSetTimeouts(session.h, each, each, each, each);
        connection.h = WinHttpConnect(session.h, host, parts.nPort, 0);
        if (connection.h == nullptr)
        {
            out.error = winHttpError("WinHttpConnect");
            return out;
        }
        request.h = WinHttpOpenRequest(connection.h, L"GET", object.c_str(), nullptr, WINHTTP_NO_REFERER,
                                       WINHTTP_DEFAULT_ACCEPT_TYPES, secure ? WINHTTP_FLAG_SECURE : 0);
        if (request.h == nullptr)
        {
            out.error = winHttpError("WinHttpOpenRequest");
            return out;
        }
        // WinHTTP follows a 3xx to any host by default; curl on POSIX runs without --location. Both refuse it the
        // same way (#88 review): with redirects disabled the 3xx surfaces as its own status, refused below.
        DWORD noRedirects = WINHTTP_DISABLE_REDIRECTS;
        if (!WinHttpSetOption(request.h, WINHTTP_OPTION_DISABLE_FEATURE, &noRedirects, static_cast<DWORD>(sizeof(noRedirects))))
        {
            out.error = winHttpError("disabling redirects");
            return out;
        }
        if (!WinHttpSendRequest(request.h, WINHTTP_NO_ADDITIONAL_HEADERS, 0, WINHTTP_NO_REQUEST_DATA, 0, 0, 0) ||
            !WinHttpReceiveResponse(request.h, nullptr))
        {
            out.error = winHttpError("the request");
            return out;
        }
        DWORD status = 0, size = sizeof(status);
        if (!WinHttpQueryHeaders(request.h, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, WINHTTP_HEADER_NAME_BY_INDEX,
                                 &status, &size, WINHTTP_NO_HEADER_INDEX))
        {
            out.error = winHttpError("reading the status");
            return out;
        }
        out.status = static_cast<int>(status);
        if (status >= 300 && status < 400)
        {
            // The Location, for httpDownloadFollowing to put to its policy; nothing here follows it.
            DWORD bytes = 0;
            WinHttpQueryHeaders(request.h, WINHTTP_QUERY_LOCATION, WINHTTP_HEADER_NAME_BY_INDEX, WINHTTP_NO_OUTPUT_BUFFER,
                                &bytes, WINHTTP_NO_HEADER_INDEX);
            if (GetLastError() == ERROR_INSUFFICIENT_BUFFER && bytes > 0)
            {
                std::vector<wchar_t> buf(bytes / sizeof(wchar_t) + 1, L'\0');
                if (WinHttpQueryHeaders(request.h, WINHTTP_QUERY_LOCATION, WINHTTP_HEADER_NAME_BY_INDEX, buf.data(), &bytes,
                                        WINHTTP_NO_HEADER_INDEX))
                    location = narrow(buf.data(), static_cast<int>(bytes / sizeof(wchar_t)));
            }
            out.error = redirectRefusal(out.status);
            return out;
        }
        if (status != 200)
        {
            out.error = "the server answered HTTP " + std::to_string(status);
            return out;
        }
        int64_t total = -1;
        DWORD length = 0;
        size = sizeof(length);
        if (WinHttpQueryHeaders(request.h, WINHTTP_QUERY_CONTENT_LENGTH | WINHTTP_QUERY_FLAG_NUMBER, WINHTTP_HEADER_NAME_BY_INDEX,
                                &length, &size, WINHTTP_NO_HEADER_INDEX))
            total = static_cast<int64_t>(length);

        const std::filesystem::path temp = downloadTempPath(dest);
        std::error_code ec;
        std::filesystem::remove(temp, ec);
        HANDLE file = CreateFileW(temp.wstring().c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (file == INVALID_HANDLE_VALUE)
        {
            out.error = "could not create " + temp.string() + " (error " + std::to_string(GetLastError()) + ")";
            return out;
        }
        std::vector<char> chunk(64u * 1024u);
        const ULONGLONG deadline = GetTickCount64() + static_cast<ULONGLONG>(each);
        bool failed = false;
        for (;;)
        {
            DWORD available = 0;
            if (!WinHttpQueryDataAvailable(request.h, &available))
            {
                out.error = winHttpError("reading the body");
                failed = true;
                break;
            }
            if (available == 0)
                break;
            const DWORD want = available < chunk.size() ? available : static_cast<DWORD>(chunk.size());
            DWORD got = 0;
            if (!WinHttpReadData(request.h, chunk.data(), want, &got))
            {
                out.error = winHttpError("reading the body");
                failed = true;
                break;
            }
            if (got == 0)
                break;
            DWORD written = 0;
            if (!WriteFile(file, chunk.data(), got, &written, nullptr) || written != got)
            {
                out.error = "could not write " + temp.string() + " (error " + std::to_string(GetLastError()) + ")";
                failed = true;
                break;
            }
            out.bytes += got;
            if (progress)
                progress(out.bytes, total);
            if (GetTickCount64() > deadline)
            {
                out.error = "the download took longer than " + std::to_string(each / 1000) + " s";
                failed = true;
                break;
            }
        }
        CloseHandle(file);
        if (!failed && total >= 0 && out.bytes != static_cast<uint64_t>(total))
        {
            out.error = "the body was " + std::to_string(out.bytes) + " bytes, shorter than its Content-Length " +
                        std::to_string(total);
            failed = true;
        }
        if (failed)
        {
            std::filesystem::remove(temp, ec);
            return out;
        }
        if (!MoveFileExW(temp.wstring().c_str(), dest.wstring().c_str(), MOVEFILE_REPLACE_EXISTING))
        {
            out.error = "could not move the download to " + dest.string() + " (error " + std::to_string(GetLastError()) + ")";
            std::filesystem::remove(temp, ec);
            return out;
        }
        return out;
    }

    // ---- Sprint 18 T4 (R341): INSTALL's glue -- the redirect-following download, runAndWait, the resolver, adapters --
    namespace
    {
        constexpr int kMostRedirects = 3;

        bool isFollowedRedirect(int status)
        {
            return status == 301 || status == 302 || status == 303 || status == 307 || status == 308;
        }

        // "scheme://authority" of an absolute URL ("" when it is not one): what a refusal names, never the whole
        // signed URL a CDN redirect carries.
        std::string origin(const std::string &url)
        {
            const size_t sep = url.find("://");
            if (sep == std::string::npos)
                return {};
            return url.substr(0, url.find_first_of("/?#", sep + 3));
        }

        // A Location, made absolute against the URL that answered it: absolute stays, "//host/..." takes the scheme,
        // "/path" takes the scheme and authority. Anything else is returned as given, for the policy to refuse.
        std::string resolveLocation(const std::string &current, const std::string &location)
        {
            if (location.find("://") != std::string::npos)
                return location;
            const std::string from = origin(current);
            if (location.rfind("//", 0) == 0)
                return from.substr(0, from.find("://") + 1) + location;
            if (!location.empty() && location[0] == '/' && !from.empty())
                return from + location;
            return location;
        }

        // An argument quoted the way CommandLineToArgvW (and the CRT) read it back: backslashes doubled only before
        // a quote or the closing quote, every quote escaped.
        std::wstring quoteArg(const std::wstring &arg)
        {
            if (!arg.empty() && arg.find_first_of(L" \t\n\v\"") == std::wstring::npos)
                return arg;
            std::wstring out = L"\"";
            for (auto it = arg.begin();; ++it)
            {
                size_t slashes = 0;
                while (it != arg.end() && *it == L'\\')
                {
                    ++it;
                    ++slashes;
                }
                if (it == arg.end())
                {
                    out.append(slashes * 2, L'\\');
                    break;
                }
                if (*it == L'"')
                {
                    out.append(slashes * 2 + 1, L'\\');
                    out.push_back(L'"');
                }
                else
                {
                    out.append(slashes, L'\\');
                    out.push_back(*it);
                }
            }
            out.push_back(L'"');
            return out;
        }

        // CreateProcessW with stdout+stderr on `log`, stdin on NUL, and ONLY those two handles inherited
        // (PROC_THREAD_ATTRIBUTE_HANDLE_LIST): the launcher's own pipes and files never leak into the child. The
        // environment is this process's. `app` null = found by the command line's first token (the search
        // CreateProcess does); `cwd` null = this process's directory. False with `error` set.
        bool spawnLogged(const std::wstring *app, std::wstring commandLine, const std::wstring *cwd, HANDLE log,
                         PROCESS_INFORMATION &pi, std::string &error)
        {
            SECURITY_ATTRIBUTES sa{};
            sa.nLength = sizeof(sa);
            sa.bInheritHandle = TRUE;
            HANDLE nul = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, &sa, OPEN_EXISTING,
                                     FILE_ATTRIBUTE_NORMAL, nullptr);
            HANDLE inherit[2] = {log, nul};
            const DWORD inheritCount = nul != INVALID_HANDLE_VALUE ? 2 : 1;
            SIZE_T attrSize = 0;
            InitializeProcThreadAttributeList(nullptr, 1, 0, &attrSize);
            std::vector<unsigned char> attrBuf(attrSize);
            auto *attrs = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(attrBuf.data());
            const bool listMade = attrSize > 0 && InitializeProcThreadAttributeList(attrs, 1, 0, &attrSize);
            const bool listSet = listMade && UpdateProcThreadAttribute(attrs, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, inherit,
                                                                       inheritCount * sizeof(HANDLE), nullptr, nullptr);
            if (!listSet)
            {
                // T4 review 5: without the list, inheritance on would hand the child every inheritable handle this
                // process holds -- so the start fails instead.
                const DWORD why = GetLastError();
                if (listMade)
                    DeleteProcThreadAttributeList(attrs);
                if (nul != INVALID_HANDLE_VALUE)
                    CloseHandle(nul);
                error = "the handles the child may inherit could not be restricted (error " + std::to_string(why) + ")";
                return false;
            }
            STARTUPINFOEXW si{};
            si.StartupInfo.cb = sizeof(si);
            si.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
            si.StartupInfo.hStdOutput = log;
            si.StartupInfo.hStdError = log;
            si.StartupInfo.hStdInput = nul != INVALID_HANDLE_VALUE ? nul : nullptr;
            si.lpAttributeList = attrs;
            commandLine.push_back(L'\0');
            const BOOL ok = CreateProcessW(app != nullptr ? app->c_str() : nullptr, commandLine.data(), nullptr, nullptr, TRUE,
                                           CREATE_NO_WINDOW | EXTENDED_STARTUPINFO_PRESENT,
                                           nullptr, cwd != nullptr ? cwd->c_str() : nullptr, &si.StartupInfo, &pi);
            const DWORD lastError = GetLastError();
            DeleteProcThreadAttributeList(attrs);
            if (nul != INVALID_HANDLE_VALUE)
                CloseHandle(nul);
            if (!ok)
            {
                error = "CreateProcess failed (" + std::to_string(lastError) + ")";
                return false;
            }
            return true;
        }

        // The last component of a UTF-8 path, bytes as given (no round trip through the ANSI code page).
        std::string leafOf(const std::string &utf8Path)
        {
            const size_t slash = utf8Path.find_last_of("\\/");
            return slash == std::string::npos ? utf8Path : utf8Path.substr(slash + 1);
        }

        std::wstring commandLineOf(const std::wstring &exe, const std::vector<std::string> &args)
        {
            std::wstring cmd = quoteArg(exe);
            for (const std::string &a : args)
            {
                cmd.push_back(L' ');
                cmd += quoteArg(widen(a));
            }
            return cmd;
        }

        HANDLE createLog(const fs::path &path)
        {
            SECURITY_ATTRIBUTES sa{};
            sa.nLength = sizeof(sa);
            sa.bInheritHandle = TRUE;
            return CreateFileW(path.wstring().c_str(), GENERIC_WRITE, FILE_SHARE_READ, &sa, CREATE_ALWAYS,
                               FILE_ATTRIBUTE_NORMAL, nullptr);
        }
    }

    DownloadResult httpDownload(const std::string &url, const std::filesystem::path &dest, const std::string &userAgent,
                                int timeoutMs, const DownloadProgress &progress)
    {
        return httpDownloadFollowing(url, dest, userAgent, timeoutMs, progress, nullptr);
    }

    DownloadResult httpDownloadFollowing(const std::string &url, const std::filesystem::path &dest, const std::string &userAgent,
                                         int timeoutMs, const DownloadProgress &progress, const RedirectPolicy &follow)
    {
        std::string current = url;
        for (int hop = 0;; ++hop)
        {
            std::string location;
            DownloadResult out = downloadOnce(current, dest, userAgent, timeoutMs, progress, location);
            // Not a redirect (a success or any other failure), or no policy: as httpDownload always answered.
            if (!isFollowedRedirect(out.status) || !follow)
                return out;
            const std::string status = std::to_string(out.status);
            if (location.empty())
            {
                out.error = "the server answered HTTP " + status + " with no Location: the redirect is refused";
                return out;
            }
            const std::string next = resolveLocation(current, location);
            if (hop >= kMostRedirects)
            {
                out.error = "the server answered HTTP " + status + " after " + std::to_string(kMostRedirects) +
                            " redirects: more are refused";
                return out;
            }
            if (!follow(current, next))
            {
                const std::string where = origin(next);
                out.error = "the server answered HTTP " + status + ": the redirect from " + origin(current) + " to " +
                            (where.empty() ? std::string("a relative location") : where) + " is refused";
                return out;
            }
            current = next;
        }
    }

    int runAndWait(const std::vector<std::string> &argv, const std::filesystem::path &log, int timeoutMs, std::string &error)
    {
        error.clear();
        if (argv.empty() || argv[0].empty())
        {
            error = "nothing to run";
            return -1;
        }
        std::error_code ec;
        if (log.has_parent_path())
            fs::create_directories(log.parent_path(), ec);
        HANDLE logHandle = createLog(log);
        if (logHandle == INVALID_HANDLE_VALUE)
        {
            error = "cannot create " + log.string() + " (error " + std::to_string(GetLastError()) + ")";
            return -1;
        }
        const std::wstring exe = widen(argv[0]);
        // A path is run as named (no search); a bare name ("tar.exe") is found the way CreateProcess finds it.
        const bool hasPath = argv[0].find_first_of("\\/") != std::string::npos;
        const std::vector<std::string> rest(argv.begin() + 1, argv.end());
        PROCESS_INFORMATION pi{};
        const bool started = spawnLogged(hasPath ? &exe : nullptr, commandLineOf(exe, rest), nullptr, logHandle, pi, error);
        CloseHandle(logHandle);   // the child holds its own copy
        if (!started)
        {
            error = leafOf(argv[0]) + " could not be started: " + error;
            return -1;
        }
        CloseHandle(pi.hThread);
        const DWORD wait = WaitForSingleObject(pi.hProcess, timeoutMs > 0 ? static_cast<DWORD>(timeoutMs) : INFINITE);
        if (wait != WAIT_OBJECT_0)
        {
            TerminateProcess(pi.hProcess, 1);
            WaitForSingleObject(pi.hProcess, 5000);
            CloseHandle(pi.hProcess);
            error = leafOf(argv[0]) + " did not finish within " + std::to_string(timeoutMs / 1000) +
                    " s and was stopped";
            return -1;
        }
        DWORD code = 0;
        GetExitCodeProcess(pi.hProcess, &code);
        CloseHandle(pi.hProcess);
        return static_cast<int>(code);
    }

    std::string resolveIpv4(const std::string &host)
    {
        if (host.empty())
            return {};
        static const bool wsaUp = [] {
            WSADATA wsa;
            return WSAStartup(MAKEWORD(2, 2), &wsa) == 0;   // once per process; getaddrinfo needs Winsock up
        }();
        if (!wsaUp)
            return {};
        addrinfo hints{};
        hints.ai_family = AF_INET;
        hints.ai_socktype = SOCK_STREAM;
        addrinfo *res = nullptr;
        if (getaddrinfo(host.c_str(), nullptr, &hints, &res) != 0 || res == nullptr)
            return {};
        std::string out;
        for (addrinfo *a = res; a != nullptr && out.empty(); a = a->ai_next)
        {
            if (a->ai_family != AF_INET || a->ai_addr == nullptr)
                continue;
            const auto *in = reinterpret_cast<const sockaddr_in *>(a->ai_addr);
            const uint32_t ip = ntohl(in->sin_addr.s_addr);
            out = std::to_string((ip >> 24) & 0xFF) + "." + std::to_string((ip >> 16) & 0xFF) + "." +
                  std::to_string((ip >> 8) & 0xFF) + "." + std::to_string(ip & 0xFF);
        }
        freeaddrinfo(res);
        return out;
    }

    std::vector<launcher::pcsx2install::Adapter> listAdapters()
    {
        std::vector<launcher::pcsx2install::Adapter> out;
        const ULONG flags = GAA_FLAG_INCLUDE_GATEWAYS | GAA_FLAG_SKIP_ANYCAST | GAA_FLAG_SKIP_MULTICAST | GAA_FLAG_SKIP_DNS_SERVER;
        ULONG size = 16u * 1024u;
        std::vector<unsigned char> buf;
        ULONG rc = ERROR_BUFFER_OVERFLOW;
        // The documented pattern: the size the call asks for, retried (an adapter may appear between two calls).
        for (int attempt = 0; attempt < 3 && rc == ERROR_BUFFER_OVERFLOW; ++attempt)
        {
            buf.assign(size, 0);
            rc = GetAdaptersAddresses(AF_INET, flags, nullptr, reinterpret_cast<PIP_ADAPTER_ADDRESSES>(buf.data()), &size);
        }
        if (rc != NO_ERROR)
            return out;
        for (auto *a = reinterpret_cast<PIP_ADAPTER_ADDRESSES>(buf.data()); a != nullptr; a = a->Next)
        {
            if (a->IfType == IF_TYPE_SOFTWARE_LOOPBACK || a->IfType == IF_TYPE_TUNNEL || a->AdapterName == nullptr)
                continue;
            launcher::pcsx2install::Adapter adapter;
            adapter.guid = a->AdapterName;   // "{GUID}": the name PCSX2 writes as [DEV9/Eth] EthDevice
            adapter.name = narrow(a->FriendlyName);
            adapter.hasGateway = a->FirstGatewayAddress != nullptr;
            out.push_back(adapter);
        }
        return out;
    }

    bool startProcess(const std::string &exe, const std::vector<std::string> &args, const std::string &workingDir,
                      const std::string &logDir, GameProcess &out)
    {
        out.error.clear();
        // T4 review 3: every string here is UTF-8 (as runAndWait's argv is), so each path is widened from UTF-8 and
        // never narrowed through the ANSI code page.
        const fs::path exePath(widen(exe));
        std::error_code ec;
        if (exe.empty() || !fs::is_regular_file(exePath, ec))
        {
            out.error = (exe.empty() ? std::string("no program") : leafOf(exe)) + " is not there";
            return false;
        }
        const fs::path logFolder(widen(logDir));
        fs::create_directories(logFolder, ec);
        const fs::path logFile = logFolder / ("pcsx2_" + stamp() + ".log");
        out.logPath = narrow(logFile.wstring().c_str());
        HANDLE logHandle = createLog(logFile);
        if (logHandle == INVALID_HANDLE_VALUE)
        {
            out.error = "cannot create the log file";
            return false;
        }
        const std::wstring app = exePath.wstring();
        const std::wstring cwd = workingDir.empty() ? exePath.parent_path().wstring() : widen(workingDir);
        PROCESS_INFORMATION pi{};
        if (!spawnLogged(&app, commandLineOf(app, args), &cwd, logHandle, pi, out.error))
        {
            CloseHandle(logHandle);
            return false;
        }
        CloseHandle(pi.hThread);
        out.process = pi.hProcess;
        out.log = logHandle;
        return true;
    }
}
#endif // _WIN32
