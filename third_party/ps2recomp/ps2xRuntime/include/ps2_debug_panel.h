#ifndef PS2_DEBUG_PANEL_H
#define PS2_DEBUG_PANEL_H

class PS2Runtime;

class PS2DebugPanel
{
public:
    void initialize();
    void shutdown();
    void draw(PS2Runtime &runtime);

    bool isVisible() const { return m_visible; }
    void setVisible(bool visible) { m_visible = visible; }
    void toggleVisible() { m_visible = !m_visible; }

private:
    bool m_initialized = false;
    // Owner 2026-09-20: the debug build is welcome to exist, but a player must not find the Runtime
    // Debugger sitting open over their game. It starts closed; F1 opens it (ps2_debug_panel.cpp, the
    // IsKeyPressed(KEY_F1) toggle), which is how anyone who wants it has always reached it.
    bool m_visible = false;
    bool m_showRegisters = true;
    unsigned int m_memoryAddress = 0x00100000u;
    unsigned int m_memoryBytes = 0x100u;
};

#endif // PS2_DEBUG_PANEL_H
