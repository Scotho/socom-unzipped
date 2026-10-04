// macOS fork: raw, unaccelerated mouse deltas from the GameController framework (macOS 11+). GLFW cannot give
// raw motion on Cocoa (its deltas are NSEvent's, after acceleration), so the mouse module reads GCMouse here
// and raylib only hides and locks the cursor.
#include "socom2_mouse.h"

#import <Foundation/Foundation.h>
#import <GameController/GameController.h>

#include <iostream>

namespace
{
    void attach(GCMouse *mouse) API_AVAILABLE(macos(11.0))
    {
        if (mouse == nil || mouse.mouseInput == nil)
            return;
        // GCMouse reports +y up; the stick's +y is down (RY 0xFF = look down). Negate y so the mouse matches the
        // pad: mouse forward looks up.
        mouse.mouseInput.mouseMovedHandler = ^(GCMouseInput *, float deltaX, float deltaY) {
            ps2_stubs::socom2MouseAddRaw(static_cast<double>(deltaX), -static_cast<double>(deltaY));
        };
        std::cout << "[mouse] raw deltas: GCMouse \"" << (mouse.vendorName ? mouse.vendorName.UTF8String : "mouse")
                  << "\"" << std::endl;
    }
}

namespace ps2_stubs
{
    bool socom2MouseGcStart()
    {
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
