#pragma once

#include <string_view>
#include <string>

#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WINAPI
#define WINAPI __stdcall
#endif

extern "C"
{
    typedef void *HANDLE;
    typedef void *HMODULE;
    typedef const wchar_t *PCWSTR;
    typedef long HRESULT;

    __declspec(dllimport) HMODULE WINAPI GetModuleHandleW(const wchar_t *lpModuleName);
    __declspec(dllimport) void *WINAPI GetProcAddress(HMODULE hModule, const char *lpProcName);
    __declspec(dllimport) HANDLE WINAPI GetCurrentThread(void);
}
#elif defined(__APPLE__) || defined(__linux__)
#include <pthread.h>
#endif

#if defined(__linux__)
#include <atomic>
#include <sys/syscall.h>
#include <unistd.h>
#endif

namespace ThreadNaming
{
#if defined(__linux__)
    // Sprint 8 Goal 1 design item 3: the Linux host sampler arms its timer with
    // timer_create(SIGEV_THREAD_ID), which needs the EE thread's KERNEL task id -- and
    // std::thread::native_handle() is a pthread_t, which is not one and cannot be turned into one.
    // The id is therefore recorded here, on the thread itself, when the game thread names itself
    // "GameThread" (ps2_runtime.cpp's first statement on that thread), which is the Linux mirror of
    // the Windows path's DuplicateHandle of the thread handle.
    inline std::atomic<int> g_gameThreadTid{0};

    // 0 until the game thread has named itself.
    inline int gameThreadTid()
    {
        return g_gameThreadTid.load(std::memory_order_acquire);
    }

    inline int currentThreadTid()
    {
        return static_cast<int>(::syscall(SYS_gettid));
    }
#endif

    inline void SetCurrentThreadName(std::string_view name)
    {
#if defined(_WIN32) 
        using SetThreadDescriptionFn = HRESULT(WINAPI*)(HANDLE, PCWSTR);

        HMODULE kernel32 = ::GetModuleHandleW(L"Kernel32.dll");
        auto setThreadDescription =
            reinterpret_cast<SetThreadDescriptionFn>(::GetProcAddress(kernel32, "SetThreadDescription"));

        if (setThreadDescription)
        {
            std::wstring wname(name.begin(), name.end());
            setThreadDescription(::GetCurrentThread(), wname.c_str());
        }

#elif defined(__APPLE__)
        pthread_setname_np(name.data());

#elif defined(__linux__)
        pthread_setname_np(pthread_self(), name.data());
        if (name == "GameThread")
            g_gameThreadTid.store(currentThreadTid(), std::memory_order_release);
#endif
    }
}
