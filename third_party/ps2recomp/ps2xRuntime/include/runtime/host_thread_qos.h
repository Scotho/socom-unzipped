#pragma once
// macOS fork: keep the game thread on Apple Silicon's performance cores.
//
// The runtime never set a thread's priority class, so macOS scheduled the game thread -- which is CPU-bound in a
// mission (the framerate spike, 2026-10-04: ~80% busy, VU1 on the same thread) -- as default-QoS work, free to run on
// the efficiency cores. QOS_CLASS_USER_INTERACTIVE asks for the performance cores. PS2X_GAME_THREAD_QOS gates it
// (ps2_runtime.cpp, the game thread's first statements). Other platforms: nothing.
#include <string>

#if defined(__APPLE__)
#include <pthread.h>
#include <pthread/qos.h>
#endif

// Set the calling thread to user-interactive. True when it now reports that class.
inline bool hostThreadSetInteractive()
{
#if defined(__APPLE__)
    if (pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0) != 0)
        return false;
    qos_class_t cls = QOS_CLASS_UNSPECIFIED;
    int relative = 0;
    return pthread_get_qos_class_np(pthread_self(), &cls, &relative) == 0 && cls == QOS_CLASS_USER_INTERACTIVE;
#else
    return false;
#endif
}

// The calling thread's class, for the log: "user-interactive", "user-initiated", "default", "utility",
// "background", "unspecified"; "n/a" off macOS.
inline std::string hostThreadQosName()
{
#if defined(__APPLE__)
    qos_class_t cls = QOS_CLASS_UNSPECIFIED;
    int relative = 0;
    if (pthread_get_qos_class_np(pthread_self(), &cls, &relative) != 0)
        return "unspecified";
    switch (cls)
    {
    case QOS_CLASS_USER_INTERACTIVE: return "user-interactive";
    case QOS_CLASS_USER_INITIATED: return "user-initiated";
    case QOS_CLASS_DEFAULT: return "default";
    case QOS_CLASS_UTILITY: return "utility";
    case QOS_CLASS_BACKGROUND: return "background";
    default: return "unspecified";
    }
#else
    return "n/a";
#endif
}
