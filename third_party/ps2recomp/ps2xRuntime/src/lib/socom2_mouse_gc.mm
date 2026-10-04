// macOS fork: raw, unaccelerated mouse deltas from the GameController framework (macOS 11+). GLFW cannot give
// raw motion on Cocoa (its deltas are NSEvent's, after acceleration), so the mouse module reads GCMouse here
// and raylib only hides and locks the cursor.
#include "socom2_mouse.h"

#import <Foundation/Foundation.h>
#import <GameController/GameController.h>

#include <atomic>
#include <chrono>
#include <iostream>

namespace
{
    // Delivery: GCDevice.handlerQueue defaults to the main queue, which the render loop drains once per frame (when it
    // polls events), so counts arrived in per-frame batches. The mouse gets its own serial queue; the counts go to the
    // atomic accumulator as they arrive. PS2X_MOUSE_GC_MAINQ=1 restores the main queue (the measurement's baseline).
    std::atomic<uint64_t> g_events{0}, g_onMain{0}, g_maxGapUs{0}, g_lastUs{0};
    bool g_mainQueue = false;   // set once by socom2MouseGcStart, before any attach

    uint64_t nowUs()
    {
        return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count());
    }

    void attach(GCMouse *mouse) API_AVAILABLE(macos(11.0))
    {
        if (mouse == nil || mouse.mouseInput == nil)
            return;
        static dispatch_queue_t queue = dispatch_queue_create("socom2.mouse", DISPATCH_QUEUE_SERIAL);
        if (!g_mainQueue)
            mouse.handlerQueue = queue;
        // GCMouse reports +y up; the stick's +y is down (RY 0xFF = look down). Negate y so the mouse matches the
        // pad: mouse forward looks up.
        mouse.mouseInput.mouseMovedHandler = ^(GCMouseInput *, float deltaX, float deltaY) {
            ps2_stubs::socom2MouseAddRaw(static_cast<double>(deltaX), -static_cast<double>(deltaY));
            const uint64_t t = nowUs(), last = g_lastUs.exchange(t);
            g_events.fetch_add(1);
            if ([NSThread isMainThread])
                g_onMain.fetch_add(1);
            if (last != 0 && t - last < 100000u && t - last > g_maxGapUs.load())   // gaps under 100 ms: while moving
                g_maxGapUs.store(t - last);
        };
        std::cout << "[mouse] raw deltas: GCMouse \"" << (mouse.vendorName ? mouse.vendorName.UTF8String : "mouse")
                  << "\"" << std::endl;
    }
}

namespace ps2_stubs
{
    void socom2MouseGcReport()
    {
        static uint64_t lastAt = 0;
        const uint64_t t = nowUs();
        if (lastAt == 0)
            lastAt = t;
        if (t - lastAt < 5000000u)
            return;
        const double secs = double(t - lastAt) / 1e6;
        lastAt = t;
        const uint64_t n = g_events.exchange(0), main = g_onMain.exchange(0), gap = g_maxGapUs.exchange(0);
        if (n != 0)
            std::cout << "[mouse] gc events=" << uint64_t(double(n) / secs) << "/s main=" << (100 * main / n)
                      << "% maxgap=" << double(gap) / 1000.0 << "ms queue=" << (g_mainQueue ? "main" : "own")
                      << std::endl;
    }

    bool socom2MouseGcStart(bool mainQueue)
    {
        g_mainQueue = mainQueue;
        if (@available(macOS 11.0, *))
        {
            for (GCMouse *mouse in GCMouse.mice)
                attach(mouse);
            [[NSNotificationCenter defaultCenter] addObserverForName:GCMouseDidConnectNotification
                                                              object:nil
                                                               queue:nil
                                                          usingBlock:^(NSNotification *note) { attach(note.object); }];
            return true;
        }
        return false;
    }
}
