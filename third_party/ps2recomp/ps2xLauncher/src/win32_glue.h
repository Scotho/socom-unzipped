#pragma once
// The launcher's Win32 pieces, kept away from raylib.h (windows.h redefines Rectangle, CloseWindow, ShowCursor,
// DrawText): the executable's directory, the file dialog, starting socom2.exe with an environment and a log,
// opening a folder in Explorer.
#include "launcher/launcher_config.h"

#include <string>

namespace win32glue
{
    std::string exeDirectory();
    std::string browseForIso();
    void openFolder(const std::string &path);

    struct GameProcess
    {
        void *process = nullptr;   // HANDLE on Windows; the pid, cast, on POSIX (main.cpp tests it for "a game was started")
        void *log = nullptr;       // HANDLE
        std::string logPath;
        std::string error;
#ifndef _WIN32
        // Sprint 8 Task 4: POSIX has a pid and a file descriptor where Windows has two handles, and
        // running()/exitCode() are const -- so the one reap that can be done is cached here.
        int pid = 0;               // pid_t; 0 = nothing started
        int logFd = -1;
        mutable bool exited = false;
        mutable int status = 0;    // the raw wait(2) status, valid once `exited`
#endif
        bool running() const;
        int exitCode() const;   // Task 1a: the code the game left with (0 while it is still running)
        void close();
    };

    // Starts <dir>/socom2.exe <dir>/socom2_game.elf with the config's environment on top of the current one,
    // stdout+stderr to <dir>/logs/run_<stamp>.log. False with `error` set when it cannot.
    bool startGame(const std::string &dir, const launcher::Config &config, GameProcess &out);


    // Sprint 8 Goal 9, third pass: the custom title bar. The window keeps the system's borders, snap and
    // shadow -- only the caption is removed (WM_NCCALCSIZE), and WM_NCHITTEST is answered from the launcher's
    // own ui::chromeHitTest through this callback, so the system and the drawing agree by construction.
    //   `hitTest` takes client-area pixels and the client size and returns a ui::ChromeHit as an int.
    using ChromeHitFn = int (*)(int x, int y, int w, int h);
    // True when native chrome was installed (Windows). False elsewhere: the caller then asks raylib for an
    // undecorated window and drags it itself.
    bool installCustomChrome(void *windowHandle, ChromeHitFn hitTest);
    void minimizeWindow();
    void maximizeToggleWindow();
    bool isWindowMaximized();

    std::string stamp();
    void terminate(GameProcess &game);   // kills the game (the launch test)

    // Sprint 9 Goal 8: one blocking HTTP(S) request, for the bug report and the server's status line. Call it
    // off the UI thread. Windows: WinHTTP, certificate validation ON (no SECURITY_FLAG_IGNORE_* is ever set).
    // POSIX: a `curl` subprocess started with an argv (no shell), the body on its stdin; no curl = `error`.
    // Plain http:// is refused unless the host is 127.0.0.1 or localhost (the tests' loopback server).
    struct HttpResult
    {
        int status = 0;          // the HTTP status; 0 when there was no answer
        std::string body;        // the response body, at most 1 MB
        int retryAfter = 0;      // the Retry-After header in seconds, 0 when absent
        std::string error;       // why there was no answer, for the log; empty when status != 0
    };
    HttpResult httpRequest(const std::string &method, const std::string &url, const std::string &body, int timeoutMs);
}
