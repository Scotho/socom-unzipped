#pragma once
// Sprint 10 Q4: the launcher's look on the chrome the runtime's window owns -- the icon (every platform, through
// raylib) and on Windows 11 the caption's colours (dwmapi, loaded by hand so nothing new is linked). Called once,
// after InitWindow. What it does NOT do, and why, is in ps2x/host_window.h: the client area is the game's frame
// and the gate's capture, so no bar or button is drawn over it.
namespace ps2x_host
{
    // Sets the window icon from the embedded PNG and colours the caption; prints one "[window] chrome: ..." line
    // saying which halves took (the icon; the caption colours or "caption colours: not on this Windows").
    void applyHostWindowChrome();
}
