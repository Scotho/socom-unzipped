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
        void *process = nullptr;   // HANDLE
        void *log = nullptr;       // HANDLE
        std::string logPath;
        std::string error;
        bool running() const;
        int exitCode() const;   // Task 1a: the code the game left with (0 while it is still running)
        void close();
    };

    // Starts <dir>/socom2.exe <dir>/socom2_game.elf with the config's environment on top of the current one,
    // stdout+stderr to <dir>/logs/run_<stamp>.log. False with `error` set when it cannot.
    bool startGame(const std::string &dir, const launcher::Config &config, GameProcess &out);

    std::string stamp();
    void terminate(GameProcess &game);   // kills the game (the launch test)
}
