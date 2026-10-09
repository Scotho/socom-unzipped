// macOS fork: the game thread's QoS class (host_thread_qos.h).
#include "MiniTest.h"
#include "runtime/host_thread_qos.h"

#include <thread>

void register_host_thread_qos_tests()
{
    MiniTest::Case("HostThreadQos", [](TestCase &tc)
    {
        tc.Run("on macOS the calling thread becomes user-interactive; elsewhere nothing happens", [](TestCase &t)
        {
            bool applied = false;
            std::string after;
            std::thread worker([&] {
                applied = hostThreadSetInteractive();
                after = hostThreadQosName();
            });
            worker.join();
#if defined(__APPLE__)
            t.IsTrue(applied, "applied");
            t.Equals(after, std::string("user-interactive"), "the thread reports the class");
#else
            t.IsFalse(applied, "no QoS outside macOS");
            t.Equals(after, std::string("n/a"), "no class to report");
#endif
        });

        tc.Run("a new thread starts at the default class, so the call is what changes it", [](TestCase &t)
        {
            std::string before;
            std::thread worker([&] { before = hostThreadQosName(); });
            worker.join();
#if defined(__APPLE__)
            t.IsFalse(before == "user-interactive", "not interactive by default");
#else
            t.Equals(before, std::string("n/a"), "n/a");
#endif
        });
    });
}
