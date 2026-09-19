// The launcher's Unix half of the win32glue interface (Sprint 8 Tasks 1 and 4).
//
// The same interface win32_glue.cpp implements on Windows, with the POSIX pieces: /proc/self/exe for the
// executable's directory, posix_spawn with file actions for the game (the log on fd 1 and 2, the working
// directory the launcher's own), waitpid on the pid for running/exitCode/close/terminate, zenity for the
// file dialog and xdg-open for the folder.
//
// The name win32glue stays: one header, one interface, two implementations.
//
// glibc note: posix_spawn_file_actions_addchdir_np is a GNU extension present since glibc 2.29. Ubuntu 24.04
// (the CI image and the VM) ships glibc 2.39, so it is used directly rather than through a fork/chdir/exec
// hand-rolled spawn. A libc without it will not compile this file; that is deliberate and visible.
#ifndef _WIN32

#include "win32_glue.h"

#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <string>
#include <vector>

#include <fcntl.h>
#include <signal.h>
#include <spawn.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

namespace fs = std::filesystem;

namespace
{
    // Is `name` an executable file in one of PATH's directories? access(2) over the entries, so no shell
    // is started merely to find out whether a program exists.
    bool onPath(const char *name)
    {
        const char *path = std::getenv("PATH");
        if (path == nullptr || *path == '\0')
            return false;
        const std::string all(path);
        size_t at = 0;
        while (at <= all.size())
        {
            const size_t sep = all.find(':', at);
            const std::string dir = all.substr(at, sep == std::string::npos ? std::string::npos : sep - at);
            // An empty PATH entry means the current directory, as the shell reads it.
            const std::string candidate = (dir.empty() ? std::string(".") : dir) + "/" + name;
            if (::access(candidate.c_str(), X_OK) == 0)
                return true;
            if (sep == std::string::npos)
                break;
            at = sep + 1;
        }
        return false;
    }

    std::string trimmed(std::string s)
    {
        const char *ws = " \t\r\n";
        const size_t first = s.find_first_not_of(ws);
        if (first == std::string::npos)
            return {};
        const size_t last = s.find_last_not_of(ws);
        return s.substr(first, last - first + 1);
    }

    // waitpid(WNOHANG) once, caching the status the first time it is reaped. True while the child is still
    // running. Safe to call after the child is gone (ECHILD reads as "not running").
    bool pollChild(int pid, bool &exited, int &status)
    {
        if (pid <= 0 || exited)
            return false;
        int raw = 0;
        const pid_t r = ::waitpid(static_cast<pid_t>(pid), &raw, WNOHANG);
        if (r == 0)
            return true;   // still alive
        if (r > 0)
            status = raw;
        // r < 0 (ECHILD, or an interrupted call that will not come back better): nothing left to wait for.
        exited = true;
        return false;
    }

    void sleepMs(long ms)
    {
        struct timespec ts;
        ts.tv_sec = ms / 1000;
        ts.tv_nsec = (ms % 1000) * 1000000L;
        while (::nanosleep(&ts, &ts) == -1 && errno == EINTR)
        {
        }
    }
}

namespace win32glue
{
    std::string exeDirectory()
    {
        char buf[4096];
        const ssize_t n = ::readlink("/proc/self/exe", buf, sizeof(buf) - 1);
        if (n > 0 && static_cast<size_t>(n) < sizeof(buf))
        {
            buf[n] = '\0';
            return fs::path(buf).parent_path().string();
        }
        // No /proc (a container without it, a BSD): the same fallback the Windows file uses when
        // GetModuleFileNameW fails.
        return fs::current_path().string();
    }

    std::string browseForIso()
    {
        // Empty means "keep what was typed" -- so a desktop without zenity is not a dead end: the ISO field
        // accepts a typed path, which is what the empty return leaves in place.
        if (!onPath("zenity"))
            return {};
        // zenity prints the chosen path on stdout and exits 1 on Cancel. The whole command is a literal:
        // nothing the player typed reaches it, so there is nothing here for the shell to expand.
        FILE *pipe = ::popen("zenity --file-selection --title='Choose the SOCOM II ISO' "
                             "--file-filter='Disc images | *.iso *.ISO' --file-filter='All files | *' 2>/dev/null",
                             "r");
        if (pipe == nullptr)
            return {};
        char line[4096] = {};
        const char *got = std::fgets(line, sizeof(line), pipe);
        const int rc = ::pclose(pipe);
        if (got == nullptr || rc != 0)
            return {};   // Cancel, or zenity could not open a display
        return trimmed(line);
    }

    void openFolder(const std::string &path)
    {
        if (path.empty())
            return;
        // Detached, so the launcher never collects a zombie and never blocks: fork once, spawn xdg-open from
        // the intermediate child and let it exit immediately, which reparents xdg-open to init. The parent
        // reaps only the intermediate, which is already gone.
        const pid_t middle = ::fork();
        if (middle < 0)
            return;
        if (middle == 0)
        {
            pid_t child = 0;
            char *argv[] = {const_cast<char *>("xdg-open"), const_cast<char *>(path.c_str()), nullptr};
            ::posix_spawnp(&child, "xdg-open", nullptr, nullptr, argv, environ);
            ::_exit(0);
        }
        int ignored = 0;
        ::waitpid(middle, &ignored, 0);
    }

    // Sprint 8 Goal 9, third pass: X11/Wayland have no equivalent of the Windows caption trick, and this
    // file must stay free of raylib (the tests link it without one). So: no native chrome here -- main.cpp
    // asks raylib for an undecorated window and moves it itself when the drag region is held.
    bool installCustomChrome(void *, ChromeHitFn) { return false; }
    void minimizeWindow() {}
    void maximizeToggleWindow() {}
    bool isWindowMaximized() { return false; }

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
        return pollChild(pid, exited, status);
    }

    int GameProcess::exitCode() const
    {
        if (pid <= 0)
            return 0;
        if (!exited && pollChild(pid, exited, status))
            return 0;   // still running: 0, as the Windows side answers for STILL_ACTIVE
        if (!exited)
            return 0;
        if (WIFEXITED(status))
            return WEXITSTATUS(status);
        if (WIFSIGNALED(status))
            return 128 + WTERMSIG(status);   // the shell's convention, so a SIGSEGV reads as 139
        return 0;
    }

    void GameProcess::close()
    {
        // F9: this used to poll once with WNOHANG and then clear the pid, which ABANDONS a game that
        // is still running -- the launcher drops the only handle it has, so nothing can stop the
        // child, its exit status is never collected (a zombie until the launcher itself exits), and
        // the player is left with an idle launcher while the game still owns the screen and the pad.
        // A child that has not exited is ended the way terminate() ends one -- SIGTERM, two seconds
        // to flush its log, then SIGKILL -- and reaped before the pid is dropped.
        if (pollChild(pid, exited, status))
            terminate(*this);
        if (logFd >= 0)
            ::close(logFd);
        logFd = -1;
        pid = 0;
        exited = false;
        status = 0;
        process = nullptr;
        log = nullptr;
    }

    bool startGame(const std::string &dirStr, const launcher::Config &config, GameProcess &out)
    {
        out.error.clear();
        const fs::path dir(dirStr);
        const fs::path exe = dir / "socom2";           // no .exe here
        const fs::path elf = dir / "socom2_game.elf";
        if (!fs::exists(exe))
        {
            out.error = "socom2 is not next to the launcher (" + exe.string() + ")";
            return false;
        }
        if (!fs::exists(elf))
        {
            out.error = "socom2_game.elf is not next to the launcher (" + elf.string() + ")";
            return false;
        }
        std::error_code ec;
        fs::create_directories(dir / "logs", ec);
        fs::create_directories(dir / "cards", ec);

        // The environment: this process's block plus our knobs, ours winning by key -- the same pure rule
        // the Windows glue applies to its own block.
        const std::vector<std::string> merged = launcher::mergeEnvironment(environ, launcher::environmentFor(config));
        std::vector<char *> envp;
        envp.reserve(merged.size() + 1);
        for (const std::string &kv : merged)
            envp.push_back(const_cast<char *>(kv.c_str()));
        envp.push_back(nullptr);

        out.logPath = (dir / "logs" / ("run_" + stamp() + ".log")).string();
        // F9: O_CLOEXEC. The spawn dup2s this descriptor onto the child's 1 and 2, and dup2 clears
        // close-on-exec on the copies, so the game still writes its log -- but the descriptor itself
        // no longer leaks into every other process the launcher starts, where it would pin the log
        // file open long after close().
        const int logFd = ::open(out.logPath.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
        if (logFd < 0)
        {
            out.error = "cannot create the log file (" + std::string(std::strerror(errno)) + ")";
            return false;
        }

        posix_spawn_file_actions_t actions;
        if (::posix_spawn_file_actions_init(&actions) != 0)
        {
            ::close(logFd);
            out.error = "cannot prepare the child's file actions";
            return false;
        }
        // stdout and stderr to the log, stdin left as the launcher's; then the child's working directory is
        // the launcher's folder, which is what makes the runner's relative paths (cards/, the ISO beside it)
        // resolve the way they do on Windows. addchdir_np is glibc >= 2.29; Ubuntu 24.04 has 2.39.
        ::posix_spawn_file_actions_adddup2(&actions, logFd, STDOUT_FILENO);
        ::posix_spawn_file_actions_adddup2(&actions, logFd, STDERR_FILENO);
        ::posix_spawn_file_actions_addchdir_np(&actions, dir.c_str());

        const std::string exePath = exe.string();
        const std::string elfPath = elf.string();
        char *argv[] = {const_cast<char *>(exePath.c_str()), const_cast<char *>(elfPath.c_str()), nullptr};

        pid_t child = 0;
        const int rc = ::posix_spawn(&child, exePath.c_str(), &actions, nullptr, argv, envp.data());
        ::posix_spawn_file_actions_destroy(&actions);
        if (rc != 0)
        {
            ::close(logFd);
            out.error = "posix_spawn failed (" + std::string(std::strerror(rc)) + ")";
            return false;
        }

        out.pid = static_cast<int>(child);
        out.logFd = logFd;
        out.exited = false;
        out.status = 0;
        // main.cpp reads `process` as "a game was started"; on POSIX the pid carries that.
        out.process = reinterpret_cast<void *>(static_cast<std::intptr_t>(child));
        out.log = reinterpret_cast<void *>(static_cast<std::intptr_t>(logFd + 1));
        return true;
    }

    void terminate(GameProcess &game)
    {
        if (game.pid <= 0 || game.exited)
            return;
        ::kill(static_cast<pid_t>(game.pid), SIGTERM);
        // Two seconds to leave on its own terms (the runner flushes its log on SIGTERM), then SIGKILL.
        for (int i = 0; i < 20; ++i)
        {
            if (!pollChild(game.pid, game.exited, game.status))
                return;
            sleepMs(100);
        }
        ::kill(static_cast<pid_t>(game.pid), SIGKILL);
        int raw = 0;
        if (::waitpid(static_cast<pid_t>(game.pid), &raw, 0) > 0)
            game.status = raw;
        game.exited = true;
    }
}

#endif // !_WIN32
