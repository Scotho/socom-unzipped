#include "runtime/gs/gs_gl_backend.h"
#include "runtime/gs/ps2_gs_common.h"
#include "runtime/gs/ps2_gs_memory.h"

#include "raylib.h"
#include "rlgl.h"
#include "external/glad.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstddef>
#include <chrono>

// ---------------------------------------------------------------------------------------------
// Helpers (mirrors of the CPU backend's static helpers so the two paths agree)
// ---------------------------------------------------------------------------------------------
namespace
{
    constexpr uint32_t kMaxRtWidth = 1024u;
    constexpr uint32_t kRtHeight = 1024u;
    constexpr uint32_t kHostFrameWidth = 640u;
    constexpr uint32_t kHostFrameHeight = 512u;

    // PS2X_GS_TRACE_PAGES="0xPAGE:count": log every shadow/GPU event that touches those VRAM
    // pages (uploads, local copies, render-target refreshes, downloads, GPU draws, texture
    // decodes) with the frame number — the order of who wrote what into a page that a texture
    // is later decoded from (SOCOM II's title labels: pages 0x190..0x195 inside frame buffer
    // 0x8c's row band).
    bool tracePagesHit(uint32_t page, uint32_t count)
    {
        static const char *const s_env = std::getenv("PS2X_GS_TRACE_PAGES");
        static uint32_t s_page = 0u, s_count = 0u;
        static bool s_parsed = false;
        if (!s_env)
            return false;
        if (!s_parsed)
        {
            s_parsed = true;
            char *end = nullptr;
            s_page = static_cast<uint32_t>(std::strtoul(s_env, &end, 0));
            s_count = (end && *end == ':') ? static_cast<uint32_t>(std::strtoul(end + 1, nullptr, 0)) : 1u;
        }
        return page < s_page + s_count && page + count > s_page;
    }

    uint32_t rgba5551To8888(uint32_t c)
    {
        const uint32_t r = (c & 0x1Fu) << 3;
        const uint32_t g = ((c >> 5) & 0x1Fu) << 3;
        const uint32_t b = ((c >> 10) & 0x1Fu) << 3;
        const uint32_t a = (c & 0x8000u) ? 0x80u : 0u;
        return r | (g << 8) | (b << 16) | (a << 24);
    }

    uint32_t rgba8888To5551(uint32_t c)
    {
        const uint32_t r = (c & 0xFFu) >> 3;
        const uint32_t g = ((c >> 8) & 0xFFu) >> 3;
        const uint32_t b = ((c >> 16) & 0xFFu) >> 3;
        const uint32_t a = ((c >> 24) & 0x80u) ? 0x8000u : 0u;
        return r | (g << 5) | (b << 10) | a;
    }

    uint32_t applyTexa(const GSTexaReg &texa, uint8_t psm, uint32_t texel)
    {
        if (psm == GS_PSM_CT32)
            return texel;
        const uint8_t r = static_cast<uint8_t>(texel & 0xFFu);
        const uint8_t g = static_cast<uint8_t>((texel >> 8) & 0xFFu);
        const uint8_t b = static_cast<uint8_t>((texel >> 16) & 0xFFu);
        const bool rgbZero = r == 0u && g == 0u && b == 0u;
        uint8_t a = static_cast<uint8_t>((texel >> 24) & 0xFFu);
        switch (psm)
        {
        case GS_PSM_CT24:
            a = (texa.aem && rgbZero) ? 0u : texa.ta0;
            break;
        case GS_PSM_CT16:
        case GS_PSM_CT16S:
            if ((a & 0x80u) != 0u)
                a = texa.ta1;
            else
                a = (texa.aem && rgbZero) ? 0u : texa.ta0;
            break;
        default:
            break;
        }
        return (texel & 0x00FFFFFFu) | (static_cast<uint32_t>(a) << 24);
    }

    uint32_t resolveClutIndex(uint8_t index, uint8_t cpsm, uint8_t csm, uint8_t csa, uint8_t sourcePsm)
    {
        uint32_t clutIndex = index;
        if (csm != 0u)
            return (sourcePsm == GS_PSM_T4 || sourcePsm == GS_PSM_T4HH || sourcePsm == GS_PSM_T4HL) ? (clutIndex & 0x0Fu) : clutIndex;
        const bool is16 = cpsm == GS_PSM_CT16 || cpsm == GS_PSM_CT16S;
        const uint32_t csaMask = is16 ? 0x1Fu : 0x0Fu;
        const uint32_t clutIndexMask = is16 ? 0x1FFu : 0x0FFu;
        const uint32_t clutBase = (static_cast<uint32_t>(csa) & csaMask) << 4u;
        switch (sourcePsm)
        {
        case GS_PSM_T4:
        case GS_PSM_T4HH:
        case GS_PSM_T4HL:
            clutIndex = clutBase + (clutIndex & 0x0Fu);
            break;
        case GS_PSM_T8:
        case GS_PSM_T8H:
            clutIndex = clutBase + clutIndex;
            break;
        default:
            return clutIndex;
        }
        // CSM1 stores the CLUT with address bits 3 and 4 swapped (a 4-bit CLUT is an 8x2 block,
        // not a 16x1 strip). Same as the CPU rasterizer's swizzleClutIndexCSM1; without it the
        // bright half of every 4-bit palette read the wrong slot (UI text came out dim).
        clutIndex &= clutIndexMask;
        return (clutIndex & ~0x18u) | ((clutIndex & 0x08u) << 1u) | ((clutIndex & 0x10u) >> 1u);
    }

    uint32_t readVramRaw(uint8_t *vram, uint32_t psm, uint32_t bp, uint32_t bw, uint32_t x, uint32_t y)
    {
        switch (psm)
        {
        case GS_PSM_CT32: return GSMem::ReadCT32(vram, bp, bw, x, y);
        case GS_PSM_CT24: return GSMem::ReadCT24(vram, bp, bw, x, y);
        case GS_PSM_CT16: return GSMem::ReadCT16(vram, bp, bw, x, y);
        case GS_PSM_CT16S: return GSMem::ReadCT16S(vram, bp, bw, x, y);
        case GS_PSM_T8: return GSMem::ReadP8(vram, bp, bw, x, y);
        case GS_PSM_T8H: return GSMem::ReadP8H(vram, bp, bw, x, y);
        case GS_PSM_T4: return GSMem::ReadP4(vram, bp, bw, x, y);
        case GS_PSM_T4HL: return GSMem::ReadP4HL(vram, bp, bw, x, y);
        case GS_PSM_T4HH: return GSMem::ReadP4HH(vram, bp, bw, x, y);
        case GS_PSM_Z32: return GSMem::ReadZ32(vram, bp, bw, x, y);
        case GS_PSM_Z24: return GSMem::ReadZ24(vram, bp, bw, x, y);
        case GS_PSM_Z16: return GSMem::ReadZ16(vram, bp, bw, x, y);
        case GS_PSM_Z16S: return GSMem::ReadZ16S(vram, bp, bw, x, y);
        default: return 0u;
        }
    }

    void writeVramRaw(uint8_t *vram, uint32_t psm, uint32_t bp, uint32_t bw, uint32_t x, uint32_t y, uint32_t value)
    {
        switch (psm)
        {
        case GS_PSM_CT32: GSMem::WriteCT32(vram, bp, bw, x, y, value); break;
        case GS_PSM_CT24: GSMem::WriteCT24(vram, bp, bw, x, y, value); break;
        case GS_PSM_CT16: GSMem::WriteCT16(vram, bp, bw, x, y, value); break;
        case GS_PSM_CT16S: GSMem::WriteCT16S(vram, bp, bw, x, y, value); break;
        case GS_PSM_Z32: GSMem::WriteZ32(vram, bp, bw, x, y, value); break;
        case GS_PSM_Z24: GSMem::WriteZ24(vram, bp, bw, x, y, value); break;
        case GS_PSM_Z16: GSMem::WriteZ16(vram, bp, bw, x, y, value); break;
        case GS_PSM_Z16S: GSMem::WriteZ16S(vram, bp, bw, x, y, value); break;
        default: break;
        }
    }

    // Display register decoding (same as the CPU backend).
    void decodeDisplaySize(uint64_t display64, uint32_t &outWidth, uint32_t &outHeight)
    {
        const uint32_t dw = static_cast<uint32_t>((display64 >> 32) & 0x0FFFu);
        const uint32_t dh = static_cast<uint32_t>((display64 >> 44) & 0x07FFu);
        const uint32_t magh = static_cast<uint32_t>((display64 >> 23) & 0x0Fu);
        outWidth = (dw + 1u) / (magh + 1u);
        outHeight = dh + 1u;
        if (outWidth < 64u || outHeight < 64u)
        {
            outWidth = kHostFrameWidth;
            outHeight = 448u;
        }
        outWidth = std::min<uint32_t>(outWidth, kHostFrameWidth);
        outHeight = std::min<uint32_t>(outHeight, kHostFrameHeight);
    }

    GSFrameReg decodeDisplayFrame(uint64_t dispfb64)
    {
        GSFrameReg frame{};
        frame.fbp = static_cast<uint32_t>(dispfb64 & 0x1FFu);
        frame.fbw = static_cast<uint32_t>((dispfb64 >> 9) & 0x3Fu);
        frame.psm = static_cast<uint8_t>((dispfb64 >> 15) & 0x1Fu);
        return frame;
    }

    bool hasDisplaySetup(uint64_t display64, const GSFrameReg &frame)
    {
        const uint32_t dw = static_cast<uint32_t>((display64 >> 32) & 0x0FFFu);
        const uint32_t dh = static_cast<uint32_t>((display64 >> 44) & 0x07FFu);
        const uint32_t magh = static_cast<uint32_t>((display64 >> 23) & 0x0Fu);
        return frame.fbw != 0u || dw != 0u || dh != 0u || magh != 0u;
    }

    const char *kVertexShader = R"GLSL(
#version 330 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aTex;
layout(location = 2) in vec4 aColor;
layout(location = 3) in float aFog;
uniform vec2 uRtSize;
out vec4 vColor;
out vec3 vTex;
out float vFog;
void main()
{
    gl_Position = vec4(aPos.x / uRtSize.x * 2.0 - 1.0, aPos.y / uRtSize.y * 2.0 - 1.0, aPos.z * 2.0 - 1.0, 1.0);
    vColor = aColor;
    vTex = aTex;
    vFog = aFog;
}
)GLSL";

    const char *kFragmentShader = R"GLSL(
#version 330 core
in vec4 vColor;
in vec3 vTex;
in float vFog;
uniform sampler2D uTex;
uniform vec2 uTexSize;
uniform int uTme, uTfx, uTcc, uFst, uWrapU, uWrapV;
uniform vec4 uRegion;
uniform int uAte, uAtst, uAfail;
uniform float uAref;
uniform int uFge, uFba;
uniform vec3 uFogColor;
layout(location = 0, index = 0) out vec4 oColor;
layout(location = 0, index = 1) out vec4 oBlendAlpha;

float wrapCoord(float c, int mode, float size, float mn, float mx)
{
    if (mode == 0) return mod(c, size);
    if (mode == 1) return clamp(c, 0.0, size - 1.0 + 0.999);
    if (mode == 2) return clamp(c, mn, mx + 0.999);
    return float((int(floor(c)) & int(mx)) | int(mn)) + fract(c);
}

void main()
{
    vec4 c = vColor;
    if (uTme == 1)
    {
        vec2 tc = (uFst == 1) ? vTex.xy : vTex.xy / max(vTex.z, 1e-6);
        float u = wrapCoord(tc.x, uWrapU, uTexSize.x, uRegion.x, uRegion.y);
        float v = wrapCoord(tc.y, uWrapV, uTexSize.y, uRegion.z, uRegion.w);
        vec4 t = texture(uTex, vec2(u, v) / uTexSize);
        if (uTfx == 0)
        {
            c.rgb = min(c.rgb * t.rgb * 2.0, 1.0);
            c.a = (uTcc == 1) ? min(c.a * t.a * 2.0, 1.0) : c.a;
        }
        else if (uTfx == 1)
        {
            c.rgb = t.rgb;
            c.a = (uTcc == 1) ? t.a : c.a;
        }
        else if (uTfx == 2)
        {
            c.rgb = min(c.rgb * t.rgb * 2.0 + c.a, 1.0);
            c.a = (uTcc == 1) ? min(t.a + c.a, 1.0) : c.a;
        }
        else
        {
            c.rgb = min(c.rgb * t.rgb * 2.0 + c.a, 1.0);
            c.a = (uTcc == 1) ? t.a : c.a;
        }
    }
    if (uAte == 1)
    {
        float a = floor(c.a * 255.0 + 0.5);
        bool pass = true;
        if (uAtst == 0) pass = false;
        else if (uAtst == 2) pass = a < uAref;
        else if (uAtst == 3) pass = a <= uAref;
        else if (uAtst == 4) pass = a == uAref;
        else if (uAtst == 5) pass = a >= uAref;
        else if (uAtst == 6) pass = a > uAref;
        else if (uAtst == 7) pass = a != uAref;
        if (!pass && (uAfail == 0 || uAfail == 2)) discard;
    }
    if (uFge == 1)
        c.rgb = mix(uFogColor, c.rgb, vFog);
    if (uFba == 1)
        c.a = float(int(floor(c.a * 255.0 + 0.5)) | 128) / 255.0;
    oColor = c;
    oBlendAlpha = vec4(min(c.a * 2.0, 1.0));
}
)GLSL";

    uint32_t compileShader(GLenum type, const char *source)
    {
        const GLuint shader = glCreateShader(type);
        glShaderSource(shader, 1, &source, nullptr);
        glCompileShader(shader);
        GLint ok = 0;
        glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
        if (!ok)
        {
            char log[2048];
            glGetShaderInfoLog(shader, sizeof(log), nullptr, log);
            std::fprintf(stderr, "[gs-gl] shader compile failed: %s\n", log);
            glDeleteShader(shader);
            return 0u;
        }
        return shader;
    }
}

// ---------------------------------------------------------------------------------------------
// Construction / VRAM model
// ---------------------------------------------------------------------------------------------
GSGlBackend::GSGlBackend()
    : m_cpu(std::make_unique<GSCpuBackend>()), m_shadow(std::make_unique<GSCpuBackend>())
{
}

GSGlBackend::~GSGlBackend() = default;

void GSGlBackend::Initialize(uint8_t *vram, uint32_t vramSize)
{
    m_vram = vram;
    m_vramSize = vramSize;
    m_cpu->Initialize(vram, vramSize);
    m_shadowMemory.assign(vramSize, 0u);
    m_shadow->Initialize(m_shadowMemory.data(), vramSize);
    m_gpuDirtyPages.fill(0u);
    m_shadowPageGeneration.fill(0u);
    std::fprintf(stderr, "[gs-gl] OpenGL backend active (PS2X_GS_BACKEND=cpu for the rasterizer)\n");
}

void GSGlBackend::Reset()
{
    Cmd cmd;
    cmd.type = CmdType::Reset;
    const uint64_t token = postAndGetToken(std::move(cmd));
    if (m_glReady.load(std::memory_order_acquire) && std::this_thread::get_id() != m_renderThread)
        waitForToken(token);
    m_cpu->Reset();
    {
        std::lock_guard<std::mutex> lock(m_dirtyMutex);
        m_gpuDirtyPages.fill(0u);
    }
}

uint32_t GSGlBackend::pageHeightForPsm(uint32_t psm)
{
    switch (psm)
    {
    case GS_PSM_CT16:
    case GS_PSM_CT16S:
    case GS_PSM_Z16:
    case GS_PSM_Z16S:
        return 64u;
    case GS_PSM_T8:
    case GS_PSM_T8H:
        return 64u;
    case GS_PSM_T4:
    case GS_PSM_T4HL:
    case GS_PSM_T4HH:
        return 128u;
    default:
        return 32u;
    }
}

// Number of 8 KB pages a buffer of `bufferWidth64`*64 pixels by `heightPixels` occupies.
uint32_t GSGlBackend::pageSpan(uint32_t psm, uint32_t bufferWidth64, uint32_t heightPixels)
{
    uint32_t pageWidth = 64u;
    if (psm == GS_PSM_T8 || psm == GS_PSM_T8H || psm == GS_PSM_T4 || psm == GS_PSM_T4HL || psm == GS_PSM_T4HH)
        pageWidth = 128u;
    const uint32_t widthPixels = std::max<uint32_t>(1u, bufferWidth64) * 64u;
    const uint32_t pagesPerRow = std::max<uint32_t>(1u, (widthPixels + pageWidth - 1u) / pageWidth);
    const uint32_t rows = std::max<uint32_t>(1u, (heightPixels + pageHeightForPsm(psm) - 1u) / pageHeightForPsm(psm));
    return pagesPerRow * rows;
}

// ---------------------------------------------------------------------------------------------
// Game-thread side: recording
// ---------------------------------------------------------------------------------------------
void GSGlBackend::record(Cmd &&cmd, const uint8_t *data, size_t size)
{
    std::lock_guard<std::mutex> lock(m_queueMutex);
    if (data && size)
    {
        cmd.dataOffset = m_pending.data.size();
        cmd.dataSize = size;
        m_pending.data.insert(m_pending.data.end(), data, data + size);
    }
    cmd.token = m_nextToken++;
    m_pending.commands.push_back(std::move(cmd));
}

uint64_t GSGlBackend::postAndGetToken(Cmd &&cmd, const uint8_t *data, size_t size)
{
    std::lock_guard<std::mutex> lock(m_queueMutex);
    if (data && size)
    {
        cmd.dataOffset = m_pending.data.size();
        cmd.dataSize = size;
        m_pending.data.insert(m_pending.data.end(), data, data + size);
    }
    const uint64_t token = m_nextToken++;
    cmd.token = token;
    m_pending.commands.push_back(std::move(cmd));
    return token;
}

void GSGlBackend::waitForToken(uint64_t token)
{
    if (std::this_thread::get_id() == m_renderThread)
    {
        // Called on the GL thread (debug readback): execute inline.
        CommandBuffer &buffer = m_executing;
        buffer.clear();
        {
            std::lock_guard<std::mutex> lock(m_queueMutex);
            buffer.commands.swap(m_pending.commands);
            buffer.data.swap(m_pending.data);
        }
        executeCommands(buffer);
        return;
    }
    if (!m_glReady.load(std::memory_order_acquire))
        return; // no GL yet (early boot): nothing to wait for
    std::unique_lock<std::mutex> lock(m_queueMutex);
    m_queueCv.wait_for(lock, std::chrono::seconds(2), [&]
                       { return m_executedToken.load(std::memory_order_acquire) >= token; });
}

bool GSGlBackend::pagesMayBeGpuDirty(uint32_t page, uint32_t pageCount) const
{
    std::lock_guard<std::mutex> lock(m_dirtyMutex);
    for (uint32_t p = page; p < page + pageCount && p < 512u; ++p)
        if (m_gpuDirtyPages[p])
            return true;
    return false;
}

void GSGlBackend::syncDirtyPagesForRead(uint32_t page, uint32_t pageCount) const
{
    if (!pagesMayBeGpuDirty(page, pageCount))
        return;
    auto *self = const_cast<GSGlBackend *>(this);
    Cmd cmd;
    cmd.type = CmdType::Readback;
    const uint64_t token = self->postAndGetToken(std::move(cmd));
    self->waitForToken(token);
    std::lock_guard<std::mutex> lock(m_dirtyMutex);
    self->m_gpuDirtyPages.fill(0u);
}

void GSGlBackend::markRtDirtyFromFrame(const GSContext &context)
{
    const uint32_t height = std::min<uint32_t>(kRtHeight, static_cast<uint32_t>(context.scissor.y1) + 1u);
    const uint32_t span = pageSpan(context.frame.psm, context.frame.fbw, height);
    std::lock_guard<std::mutex> lock(m_dirtyMutex);
    for (uint32_t p = context.frame.fbp; p < context.frame.fbp + span && p < 512u; ++p)
        m_gpuDirtyPages[p] = 1u;
    if (!context.zbuf.zmask)
    {
        const uint32_t zspan = pageSpan(context.zbuf.psm, context.frame.fbw, height);
        for (uint32_t p = context.zbuf.zbp; p < context.zbuf.zbp + zspan && p < 512u; ++p)
            m_gpuDirtyPages[p] = 1u;
    }
}

void GSGlBackend::Submit(const GSPrimitiveBatch &batch)
{
    markRtDirtyFromFrame(batch.state.context);
    Cmd cmd;
    cmd.type = CmdType::Submit;
    cmd.batch = batch;
    record(std::move(cmd));
}

void GSGlBackend::BeginTransfer(const GSTransferCommand &command)
{
    m_currentTransfer = command;
    // Local->host and local->local read GS memory: make sure GPU-drawn pages are downloaded first.
    if (command.direction == 1u || command.direction == 2u)
    {
        const uint32_t page = command.bitbltbuf.sbp >> 5;
        const uint32_t span = pageSpan(command.bitbltbuf.spsm, command.bitbltbuf.sbw,
                                       command.trxpos.ssay + command.trxreg.rrh);
        syncDirtyPagesForRead(page, span);
    }
    m_cpu->BeginTransfer(command);
    Cmd cmd;
    cmd.type = CmdType::BeginTransfer;
    cmd.transfer = command;
    record(std::move(cmd));
}

void GSGlBackend::UploadImage(const uint8_t *data, uint32_t sizeBytes)
{
    m_cpu->UploadImage(data, sizeBytes);
    Cmd cmd;
    cmd.type = CmdType::Upload;
    record(std::move(cmd), data, sizeBytes);
}

void GSGlBackend::Flush() {}
void GSGlBackend::TextureFlush() {}

void GSGlBackend::Sync(GSSyncReason reason)
{
    if (reason == GSSyncReason::DebugReadback || reason == GSSyncReason::Reset)
    {
        Cmd cmd;
        cmd.type = CmdType::Readback;
        const uint64_t token = postAndGetToken(std::move(cmd));
        waitForToken(token);
        std::lock_guard<std::mutex> lock(m_dirtyMutex);
        m_gpuDirtyPages.fill(0u);
    }
}

PresentationFrame GSGlBackend::Present(const GSPresentationRequest &request)
{
    static const bool s_wantPixels = std::getenv("PS2X_FRAME_DUMP") != nullptr;
    PresentationFrame frame{};
    Cmd cmd;
    cmd.type = CmdType::Present;
    cmd.present = request;
    cmd.args[0] = s_wantPixels ? 1u : 0u;
    const uint64_t token = postAndGetToken(std::move(cmd));

    const GSFrameReg display1 = decodeDisplayFrame(request.dispfb1);
    uint32_t width = 0u, height = 0u;
    decodeDisplaySize(request.display1, width, height);
    frame.width = width;
    frame.height = height;
    frame.displayFbp = display1.fbp;
    frame.sourceFbp = display1.fbp;
    if (s_wantPixels)
    {
        waitForToken(token);
        std::lock_guard<std::mutex> lock(m_queueMutex);
        frame.pixels = m_presentPixels;
        if (frame.pixels.size() != static_cast<size_t>(kHostFrameWidth) * kHostFrameHeight * 4u)
            frame.pixels.clear();
    }
    return frame;
}

bool GSGlBackend::ClearFramebuffer(const GSContext &context, uint32_t rgba)
{
    markRtDirtyFromFrame(context);
    Cmd cmd;
    cmd.type = CmdType::Clear;
    cmd.context = context;
    cmd.args[0] = rgba;
    record(std::move(cmd));
    return true;
}

uint32_t GSGlBackend::ConsumeLocalToHostBytes(uint8_t *dst, uint32_t maxBytes)
{
    return m_cpu->ConsumeLocalToHostBytes(dst, maxBytes);
}

uint32_t GSGlBackend::ReadVram(uint32_t psm, uint32_t base, uint32_t bw, uint32_t x, uint32_t y) const
{
    syncDirtyPagesForRead(base >> 5, 1u + pageSpan(psm, bw, y + 1u));
    return m_cpu->ReadVram(psm, base, bw, x, y);
}

void GSGlBackend::WriteVram(uint32_t psm, uint32_t base, uint32_t bw, uint32_t x, uint32_t y, uint32_t value)
{
    m_cpu->WriteVram(psm, base, bw, x, y, value);
    Cmd cmd;
    cmd.type = CmdType::WriteVram;
    cmd.args[0] = psm;
    cmd.args[1] = base;
    cmd.args[2] = bw;
    cmd.args[3] = x | (y << 16);
    cmd.args[4] = value;
    record(std::move(cmd));
}

void GSGlBackend::SnapshotVram(std::vector<uint8_t> &out) const
{
    syncDirtyPagesForRead(0u, 512u);
    m_cpu->SnapshotVram(out);
}

GSTransferSnapshot GSGlBackend::GetTransferSnapshot() const
{
    return m_cpu->GetTransferSnapshot();
}

// ---------------------------------------------------------------------------------------------
// Render-thread side
// ---------------------------------------------------------------------------------------------
bool GSGlBackend::ensureGl()
{
    if (m_program != 0u)
        return true;
    if (!IsWindowReady())
        return false;
    const uint32_t vs = compileShader(GL_VERTEX_SHADER, kVertexShader);
    const uint32_t fs = compileShader(GL_FRAGMENT_SHADER, kFragmentShader);
    if (!vs || !fs)
        return false;
    m_program = glCreateProgram();
    glAttachShader(m_program, vs);
    glAttachShader(m_program, fs);
    glBindFragDataLocationIndexed(m_program, 0, 0, "oColor");
    glBindFragDataLocationIndexed(m_program, 0, 1, "oBlendAlpha");
    glLinkProgram(m_program);
    GLint ok = 0;
    glGetProgramiv(m_program, GL_LINK_STATUS, &ok);
    glDeleteShader(vs);
    glDeleteShader(fs);
    if (!ok)
    {
        char log[2048];
        glGetProgramInfoLog(m_program, sizeof(log), nullptr, log);
        std::fprintf(stderr, "[gs-gl] program link failed: %s\n", log);
        glDeleteProgram(m_program);
        m_program = 0u;
        return false;
    }
    auto uni = [&](const char *name) { return glGetUniformLocation(m_program, name); };
    m_u.rtSize = uni("uRtSize");
    m_u.tex = uni("uTex");
    m_u.texSize = uni("uTexSize");
    m_u.tme = uni("uTme");
    m_u.tfx = uni("uTfx");
    m_u.tcc = uni("uTcc");
    m_u.fst = uni("uFst");
    m_u.wrapU = uni("uWrapU");
    m_u.wrapV = uni("uWrapV");
    m_u.region = uni("uRegion");
    m_u.ate = uni("uAte");
    m_u.atst = uni("uAtst");
    m_u.afail = uni("uAfail");
    m_u.aref = uni("uAref");
    m_u.fge = uni("uFge");
    m_u.fogColor = uni("uFogColor");
    m_u.fba = uni("uFba");

    glGenVertexArrays(1, &m_vao);
    glGenBuffers(1, &m_vbo);
    glBindVertexArray(m_vao);
    glBindBuffer(GL_ARRAY_BUFFER, m_vbo);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, sizeof(GlVertex), reinterpret_cast<void *>(offsetof(GlVertex, x)));
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, sizeof(GlVertex), reinterpret_cast<void *>(offsetof(GlVertex, s)));
    glEnableVertexAttribArray(2);
    glVertexAttribPointer(2, 4, GL_UNSIGNED_BYTE, GL_TRUE, sizeof(GlVertex), reinterpret_cast<void *>(offsetof(GlVertex, r)));
    glEnableVertexAttribArray(3);
    glVertexAttribPointer(3, 1, GL_FLOAT, GL_FALSE, sizeof(GlVertex), reinterpret_cast<void *>(offsetof(GlVertex, fog)));
    glBindVertexArray(0);
    m_renderThread = std::this_thread::get_id();
    m_glReady.store(true, std::memory_order_release);
    std::fprintf(stderr, "[gs-gl] initialised: %s\n", reinterpret_cast<const char *>(glGetString(GL_VERSION)));
    return true;
}

bool GSGlBackend::HostRenderFrame()
{
    if (!ensureGl())
        return false;
    // The executed buffer is a member so its capacity (commands and upload bytes) is handed back
    // to m_pending by the swap: no vector growth on the game thread every frame (~7% of it).
    CommandBuffer &buffer = m_executing;
    buffer.clear();
    {
        std::lock_guard<std::mutex> lock(m_queueMutex);
        buffer.commands.swap(m_pending.commands);
        buffer.data.swap(m_pending.data);
    }
    if (!buffer.commands.empty())
        executeCommands(buffer);
    // Restore raylib's expectations.
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    glDisable(GL_SCISSOR_TEST);
    glDisable(GL_DEPTH_TEST);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glBlendEquation(GL_FUNC_ADD);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glViewport(0, 0, GetScreenWidth(), GetScreenHeight());
    glUseProgram(0);
    glBindVertexArray(0);
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, 0);
    return m_presentTexture != 0u;
}

uint32_t GSGlBackend::HostFrameTexture(uint32_t &width, uint32_t &height, uint32_t &textureWidth, uint32_t &textureHeight)
{
    width = m_presentWidth;
    height = m_presentHeight;
    textureWidth = m_presentTexWidth;
    textureHeight = m_presentTexHeight;
    return m_presentTexture;
}

// PS2X_GS_TRACE_PRESENT / PS2X_GS_TRACE_CMDS=<n>: trace after present n; a negative n counts from
// the first movie block upload (SOCOM II's intro movie starts at a different present count per run).
long GSGlBackend::traceSkip(const char *env) const
{
    // The trace switches never change during a run: cache the lookups (std::getenv here was ~4%
    // of the GL thread with tracing off; the callers are on every upload/download/refresh).
    struct CachedEnv
    {
        const char *name;
        const char *value;
    };
    static CachedEnv s_cache[8] = {};
    static int s_cacheCount = 0;
    const char *e = nullptr;
    bool found = false;
    for (int i = 0; i < s_cacheCount; ++i)
    {
        if (s_cache[i].name == env || std::strcmp(s_cache[i].name, env) == 0)
        {
            e = s_cache[i].value;
            found = true;
            break;
        }
    }
    if (!found)
    {
        e = std::getenv(env);
        if (s_cacheCount < 8)
            s_cache[s_cacheCount++] = {env, e};
    }
    if (!e)
        return -1;
    if (e[0] == 't' && e[1] == 'r')   // "trig": armed by PS2X_TRIGGER (game-state trigger in the PC sampler)
    {
        extern std::atomic<bool> g_ps2xTraceArmed;
        return g_ps2xTraceArmed.load() ? 0L : 0x7FFFFFF0L;
    }
    if (e[0] == 't')   // "t<seconds>": host-time trigger (any frame once that much time has passed)
    {
        static const auto s_epoch = std::chrono::steady_clock::now();
        const double elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - s_epoch).count();
        return elapsed >= std::atof(e + 1) ? 0L : 0x7FFFFFF0L;
    }
    const long v = std::strtol(e, nullptr, 0);
    if (v >= 0)
        return v;
    if (v == -1)   // seam-relative: from the decode that first shows the movie seam
        return m_seamFrame ? static_cast<long>(m_seamFrame) - 1 : 0x7FFFFFF0L;
    if (m_movieStartFrame == 0u)
        return 0x7FFFFFF0L;
    return static_cast<long>(m_movieStartFrame) - v;
}

void GSGlBackend::executeCommands(CommandBuffer &buffer)
{
    static const bool s_stats = std::getenv("PS2X_GS_STATS") != nullptr;
    static double s_time[8] = {0};
    static uint64_t s_count[8] = {0};
    static uint64_t s_calls = 0;
    static uint64_t s_bytes = 0;
    static auto s_lastReport = std::chrono::steady_clock::now();
    s_bytes += buffer.data.size();
    // PS2X_GS_TRACE_CMDS=<presents to skip>: then print the next 4000 replayed commands.
    static const char *s_traceEnv = std::getenv("PS2X_GS_TRACE_CMDS");
    static const bool s_traceCmds = s_traceEnv != nullptr;
    static uint32_t s_traceLines = 0;
    // PS2X_GS_TRACE_PRESENT: which replayed command changes the movie staging area (page row 3 of
    // base 0: frame rows 96..128, page columns 0 and 6) — first non-black row of the two columns.
    const long s_probeSkip = traceSkip("PS2X_GS_TRACE_PRESENT");
    auto probe = [this](uint32_t base, uint32_t c) -> int {
        for (uint32_t y = 90u; y < 340u; ++y)
        {
            uint32_t sum = 0, cnt = 0;
            for (uint32_t x = c * 64u; x < c * 64u + 64u; x += 4u, ++cnt)
            {
                const uint32_t p = readVramRaw(m_shadowMemory.data(), GS_PSM_CT32, base, 10u, x, y);
                sum += ((p & 0xFFu) + ((p >> 8) & 0xFFu) + ((p >> 16) & 0xFFu)) / 3u;
            }
            if (sum > 8u * cnt)
                return static_cast<int>(y);
        }
        return -1;
    };
    const bool probeOn = s_probeSkip >= 0 && static_cast<long>(m_frameCounter) > s_probeSkip && static_cast<long>(m_frameCounter) <= s_probeSkip + 3;
    static int s_probe[4] = {-2, -2, -2, -2};
    for (Cmd &cmd : buffer.commands)
    {
        const auto t0 = std::chrono::steady_clock::now();
        if (probeOn)
        {
            const int p[4] = {probe(0u, 2u), probe(0u, 6u), probe(0x1180u, 2u), probe(0x1180u, 6u)};
            if (p[0] != s_probe[0] || p[1] != s_probe[1] || p[2] != s_probe[2] || p[3] != s_probe[3])
            {
                std::fprintf(stderr, "[gs-gl probe] frame=%llu before cmd type=%u (dbp=%05x at %u,%u %ux%u): base0 col2=%d col6=%d | base1180 col2=%d col6=%d\n",
                             (unsigned long long)m_frameCounter, static_cast<unsigned>(cmd.type),
                             cmd.transfer.bitbltbuf.dbp, cmd.transfer.trxpos.dsax, cmd.transfer.trxpos.dsay,
                             cmd.transfer.trxreg.rrw, cmd.transfer.trxreg.rrh, p[0], p[1], p[2], p[3]);
                for (int i = 0; i < 4; ++i)
                    s_probe[i] = p[i];
            }
        }
        static const uint32_t s_traceMax = std::getenv("PS2X_GS_TRACE_CMDS_MAX") ? static_cast<uint32_t>(std::strtoul(std::getenv("PS2X_GS_TRACE_CMDS_MAX"), nullptr, 0)) : 4000u;
        static const long s_traceFrom = std::getenv("PS2X_GS_TRACE_CMDS_FROM") ? std::strtol(std::getenv("PS2X_GS_TRACE_CMDS_FROM"), nullptr, 0) : -1L;
        if (s_traceCmds && s_traceLines < s_traceMax &&
            (s_traceFrom >= 0 ? static_cast<long>(m_frameCounter) >= s_traceFrom : static_cast<long>(m_frameCounter) >= traceSkip("PS2X_GS_TRACE_CMDS")))
        {
            ++s_traceLines;
            switch (cmd.type)
            {
            case CmdType::Submit:
            {
                float xmin = 1e30f, xmax = -1e30f, ymin = 1e30f, ymax = -1e30f;
                double zmin = 1e300, zmax = -1e300;
                for (const GSVertex &v : cmd.batch.vertices)
                {
                    xmin = std::min(xmin, v.x); xmax = std::max(xmax, v.x);
                    ymin = std::min(ymin, v.y); ymax = std::max(ymax, v.y);
                    zmin = std::min(zmin, v.z); zmax = std::max(zmax, v.z);
                }
                std::fprintf(stderr, "[gs-cmd] n=%u x=[%.0f..%.0f] y=[%.0f..%.0f] z=[%.0f..%.0f] ", (unsigned)cmd.batch.vertices.size(),
                             xmin, xmax, ymin, ymax, zmin, zmax);
                std::fprintf(stderr, "submit prim=%u tme=%u fst=%u q=%g tbp0=%05x psm=%02x cbp=%05x cpsm=%02x fbp=%03x fpsm=%02x zbp=%03x zpsm=%02x zmsk=%u test=%05llx abe=%u v0=(%.0f,%.0f,%.0f) v1=(%.0f,%.0f) rgba=%02x%02x%02x%02x sc=(%d,%d)-(%d,%d) off=(%u,%u) frame=%llu%c",
                             cmd.batch.state.prim.type, cmd.batch.state.prim.tme ? 1u : 0u, cmd.batch.state.prim.fst ? 1u : 0u,
                             (double)cmd.batch.vertices[1].q, cmd.batch.state.context.tex0.tbp0,
                             cmd.batch.state.context.tex0.psm, cmd.batch.state.context.tex0.cbp, cmd.batch.state.context.tex0.cpsm,
                             cmd.batch.state.context.frame.fbp, cmd.batch.state.context.frame.psm, cmd.batch.state.context.zbuf.zbp,
                             cmd.batch.state.context.zbuf.psm, cmd.batch.state.context.zbuf.zmask ? 1u : 0u,
                             (unsigned long long)(cmd.batch.state.context.test & 0x7FFFFu), cmd.batch.state.prim.abe ? 1u : 0u,
                             cmd.batch.vertices[0].x, cmd.batch.vertices[0].y, (double)cmd.batch.vertices[0].z,
                             cmd.batch.vertices[1].x, cmd.batch.vertices[1].y,
                             cmd.batch.vertices[1].r, cmd.batch.vertices[1].g, cmd.batch.vertices[1].b, cmd.batch.vertices[1].a, cmd.batch.state.context.scissor.x0, cmd.batch.state.context.scissor.y0, cmd.batch.state.context.scissor.x1, cmd.batch.state.context.scissor.y1, (unsigned)(cmd.batch.state.context.xyoffset.ofx >> 4), (unsigned)(cmd.batch.state.context.xyoffset.ofy >> 4), (unsigned long long)m_frameCounter, 10);
                break;
            }
            case CmdType::BeginTransfer:
                std::fprintf(stderr, "[gs-cmd] transfer dir=%u sbp=%05x spsm=%02x -> dbp=%05x dpsm=%02x dbw=%u at (%u,%u) %ux%u%c",
                             cmd.transfer.direction, cmd.transfer.bitbltbuf.sbp, cmd.transfer.bitbltbuf.spsm, cmd.transfer.bitbltbuf.dbp,
                             cmd.transfer.bitbltbuf.dpsm, cmd.transfer.bitbltbuf.dbw, cmd.transfer.trxpos.dsax, cmd.transfer.trxpos.dsay,
                             cmd.transfer.trxreg.rrw, cmd.transfer.trxreg.rrh, 10);
                break;
            case CmdType::Upload:
                std::fprintf(stderr, "[gs-cmd] upload %zu bytes%c", cmd.dataSize, 10);
                break;
            case CmdType::WriteVram:
                std::fprintf(stderr, "[gs-cmd] writevram psm=%02x base=%05x%c", cmd.args[0], cmd.args[1], 10);
                break;
            case CmdType::Clear:
                std::fprintf(stderr, "[gs-cmd] clear fbp=%03x%c", cmd.context.frame.fbp, 10);
                break;
            case CmdType::Present:
                std::fprintf(stderr, "[gs-cmd] present%c", 10);
                break;
            default:
                std::fprintf(stderr, "[gs-cmd] other %u%c", static_cast<unsigned>(cmd.type), 10);
                break;
            }
        }
        switch (cmd.type)
        {
        case CmdType::Submit:
            executeSubmit(cmd.batch);
            break;
        case CmdType::BeginTransfer:
            flushBatch();
            executeTransfer(cmd.transfer);
            break;
        case CmdType::Upload:
            flushBatch();
            executeUpload(buffer.data.data() + cmd.dataOffset, cmd.dataSize);
            break;
        case CmdType::WriteVram:
            flushBatch();
            m_shadow->WriteVram(cmd.args[0], cmd.args[1], cmd.args[2], cmd.args[3] & 0xFFFFu, cmd.args[3] >> 16, cmd.args[4]);
            markShadowPages(cmd.args[1] >> 5, 1u);
            break;
        case CmdType::Clear:
            flushBatch();
            executeClear(cmd.context, cmd.args[0]);
            break;
        case CmdType::Present:
            flushBatch();
            m_presentPixelsRequested = cmd.args[0] != 0u;
            executePresent(cmd.present);
            break;
        case CmdType::Readback:
            flushBatch();
            executeReadback();
            break;
        case CmdType::Reset:
            flushBatch();
            for (auto &kv : m_textures)
                glDeleteTextures(1, &kv.second.texture);
            m_textures.clear();
            for (RenderTarget &rt : m_renderTargets)
            {
                glDeleteFramebuffers(1, &rt.fbo);
                glDeleteTextures(1, &rt.color);
            }
            m_renderTargets.clear();
            for (DepthTarget &dt : m_depthTargets)
                glDeleteTextures(1, &dt.texture);
            m_depthTargets.clear();
            m_shadow->Reset();
            m_presentTexture = 0u;
            break;
        }
        m_executedToken.store(cmd.token, std::memory_order_release);
        if (s_stats)
        {
            const auto t1 = std::chrono::steady_clock::now();
            const int idx = static_cast<int>(cmd.type) & 7;
            s_time[idx] += std::chrono::duration<double, std::milli>(t1 - t0).count();
            ++s_count[idx];
        }
    }
    flushBatch();
    m_queueCv.notify_all();
    if (s_stats && (++s_calls % 60u) == 0u)
    {
        const auto now = std::chrono::steady_clock::now();
        const double elapsed = std::chrono::duration<double, std::milli>(now - s_lastReport).count();
        s_lastReport = now;
        std::fprintf(stderr, "[gs-gl stats] elapsed=%.0fms (%.1f fps) blends=%s\n", elapsed, 60000.0 / std::max(1.0, elapsed), m_blendLog.c_str());
        m_blendLog.clear();
        std::fprintf(stderr, "[gs-gl stats] states=%s%c", m_stateLog.c_str(), 10);
        m_stateLog.clear();
        std::fprintf(stderr, "[gs-gl stats] calls=%llu bytes=%llu ms: submit=%.1f/%llu transfer=%.1f/%llu upload=%.1f/%llu wvram=%.1f/%llu clear=%.1f/%llu present=%.1f/%llu readback=%.1f/%llu textures=%zu rts=%zu\n",
                     (unsigned long long)s_calls, (unsigned long long)s_bytes,
                     s_time[0], (unsigned long long)s_count[0], s_time[1], (unsigned long long)s_count[1],
                     s_time[2], (unsigned long long)s_count[2], s_time[3], (unsigned long long)s_count[3],
                     s_time[4], (unsigned long long)s_count[4], s_time[5], (unsigned long long)s_count[5],
                     s_time[6], (unsigned long long)s_count[6], m_textures.size(), m_renderTargets.size());
        for (int i = 0; i < 8; ++i) { s_time[i] = 0; s_count[i] = 0; }
        s_bytes = 0;
    }
}

GSGlBackend::RenderTarget *GSGlBackend::getRenderTarget(uint32_t fbp, uint32_t fbw, uint32_t psm, bool create)
{
    // Targets are keyed by base page only: the game addresses the same buffer with different
    // FRAME widths (1024-wide at boot, 640-wide in the shell) and draws must land in one texture.
    // Allocate the maximum stride so pixel coordinates map directly regardless of FBW.
    for (RenderTarget &rt : m_renderTargets)
        if (rt.fbp == fbp)
        {
            rt.fbw = std::max<uint32_t>(fbw, 1u);
            return &rt;
        }
    if (!create)
        return nullptr;
    RenderTarget rt;
    rt.fbp = fbp;
    rt.fbw = std::max<uint32_t>(fbw, 1u);
    rt.psm = psm;
    rt.width = kMaxRtWidth;
    rt.height = kRtHeight;
    glGenTextures(1, &rt.color);
    glBindTexture(GL_TEXTURE_2D, rt.color);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, rt.width, rt.height, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glGenFramebuffers(1, &rt.fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, rt.fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, rt.color, 0);
    glDisable(GL_SCISSOR_TEST);
    glClearColor(0.0f, 0.0f, 0.0f, 0.0f);
    glClear(GL_COLOR_BUFFER_BIT);
    // Seed the target with whatever the shadow VRAM holds (uploads that landed before any draw).
    m_renderTargets.push_back(rt);
    RenderTarget &ref = m_renderTargets.back();
    ref.dirtyRows = true;
    ref.dirtyRowFirst = 0u;
    ref.dirtyRowLast = 448u;
    ref.dirtyMask = (1u << 14) - 1u;   // bands 0..13 = rows 0..448
    return &ref;
}

GSGlBackend::DepthTarget *GSGlBackend::getDepthTarget(uint32_t zbp, uint32_t fbw, uint32_t width, uint32_t height)
{
    for (DepthTarget &dt : m_depthTargets)
        if (dt.zbp == zbp)
            return &dt;
    DepthTarget dt;
    dt.zbp = zbp;
    dt.fbw = fbw;
    dt.width = width;
    dt.height = height;
    glGenTextures(1, &dt.texture);
    glBindTexture(GL_TEXTURE_2D, dt.texture);
    // PS2 local memory starts zeroed: initialise the depth buffer to 0 instead of leaving it undefined
    // (otherwise GEQUAL tests fail until the game's own clear writes it).
    std::vector<float> zeros(static_cast<size_t>(width) * height, 0.0f);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT32F, width, height, 0, GL_DEPTH_COMPONENT, GL_FLOAT, zeros.data());
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    m_depthTargets.push_back(dt);
    return &m_depthTargets.back();
}

void GSGlBackend::markShadowPages(uint32_t page, uint32_t pageCount)
{
    ++m_generation;
    for (uint32_t p = page; p < page + pageCount && p < 512u; ++p)
        m_shadowPageGeneration[p] = m_generation;
}

void GSGlBackend::executeTransfer(const GSTransferCommand &command)
{
    m_shadow->BeginTransfer(command);
    if (command.direction == 2u) // local -> local: the shadow copies immediately; refresh RTs
    {
        const uint32_t page = command.bitbltbuf.dbp >> 5;
        const uint32_t span = pageSpan(command.bitbltbuf.dpsm, command.bitbltbuf.dbw, command.trxpos.dsay + command.trxreg.rrh);
        markShadowPages(page, span);
        if (tracePagesHit(page, span))
            std::fprintf(stderr, "[gs-pages] frame=%llu local-copy sbp=%05x -> dbp=%05x dbw=%u %ux%u pages %03x+%u\n",
                         (unsigned long long)m_frameCounter, command.bitbltbuf.sbp, command.bitbltbuf.dbp, command.bitbltbuf.dbw,
                         command.trxreg.rrw, command.trxreg.rrh, page, span);
        refreshRenderTargetsFromShadow(page, span, command);
    }
    if (m_movieStartFrame == 0u && command.trxreg.rrw == 16u && command.trxreg.rrh == 16u && command.bitbltbuf.dbw == 10u &&
        command.trxpos.dsax == 0u && command.trxpos.dsay == 0u && (command.bitbltbuf.dbp == 0x3c0u || command.bitbltbuf.dbp == 0x1540u))
        m_movieStartFrame = m_frameCounter ? m_frameCounter : 1u;
    m_currentTransfer = command;
    m_uploadReceivedBytes = 0u;
    m_uploadExpectedBytes = static_cast<uint64_t>(command.trxreg.rrw) * command.trxreg.rrh *
                            GSInternal::bitsPerPixel(command.bitbltbuf.dpsm) / 8u;
}

void GSGlBackend::executeUpload(const uint8_t *data, size_t size)
{
    m_shadow->UploadImage(data, static_cast<uint32_t>(size));
    const GSTransferCommand &t = m_currentTransfer;
    const uint32_t page = t.bitbltbuf.dbp >> 5;
    const uint32_t span = pageSpan(t.bitbltbuf.dpsm, t.bitbltbuf.dbw, t.trxpos.dsay + t.trxreg.rrh);
    markShadowPages(page, span);
    if (tracePagesHit(page, span))
        std::fprintf(stderr, "[gs-pages] frame=%llu upload dbp=%05x dbw=%u psm=%02x dst=(%u,%u) %ux%u pages %03x+%u bytes=%zu\n",
                     (unsigned long long)m_frameCounter, t.bitbltbuf.dbp, t.bitbltbuf.dbw, t.bitbltbuf.dpsm,
                     t.trxpos.dsax, t.trxpos.dsay, t.trxreg.rrw, t.trxreg.rrh, page, span, size);
    // Uploads arrive in chunks; refresh overlapping render targets once per completed rectangle.
    m_uploadReceivedBytes += size;
    if (m_uploadExpectedBytes != 0u && m_uploadReceivedBytes >= m_uploadExpectedBytes)
    {
        m_uploadReceivedBytes = 0u;
        refreshRenderTargetsFromShadow(page, span, t);
        // PS2X_GS_TRACE_PRESENT: after the last 16x16 block of a movie frame (dsax 624, dsay 208),
        // the first non-black row per 64-px page column of the frame area in the shadow VRAM.
        const long s_upSkip = traceSkip("PS2X_GS_TRACE_PRESENT");
        static uint32_t s_upPrinted = 0u;
        if (s_upSkip >= 0 && static_cast<long>(m_frameCounter) > s_upSkip && s_upPrinted < 12u &&
            t.trxreg.rrw == 16u && t.trxreg.rrh == 16u && t.trxpos.dsax == 624u && t.trxpos.dsay == 208u)
        {
            ++s_upPrinted;
            char line[256];
            int n = std::snprintf(line, sizeof(line), "[gs-gl upload-scan] frame=%llu dbp=%05x dbw=%u first-row/page-col:",
                                  (unsigned long long)m_frameCounter, t.bitbltbuf.dbp, t.bitbltbuf.dbw);
            for (uint32_t c = 0; c < 10u && n < 240; ++c)
            {
                int firstRow = -1;
                for (uint32_t y = 0; y < 240u; ++y)
                {
                    uint32_t sum = 0, cnt = 0;
                    for (uint32_t x = c * 64u; x < c * 64u + 64u; x += 4u, ++cnt)
                    {
                        const uint32_t p = readVramRaw(m_shadowMemory.data(), t.bitbltbuf.dpsm, t.bitbltbuf.dbp, t.bitbltbuf.dbw, x, y);
                        sum += ((p & 0xFFu) + ((p >> 8) & 0xFFu) + ((p >> 16) & 0xFFu)) / 3u;
                    }
                    if (sum > 8u * cnt) { firstRow = static_cast<int>(y); break; }
                }
                n += std::snprintf(line + n, sizeof(line) - n, " %d", firstRow);
            }
            std::fprintf(stderr, "%s\n", line);
        }
    }
}

// A transfer wrote into pages a render target covers (video frames are uploaded straight into the
// display buffer as hundreds of small transfers with their own base addresses). Mark the affected
// page rows; they are re-read from the shadow VRAM in the target's own layout before the next draw
// into that target or the next present (refreshDirtyRows).
void GSGlBackend::refreshRenderTargetsFromShadow(uint32_t page, uint32_t pageCount, const GSTransferCommand &transfer)
{
    for (RenderTarget &rt : m_renderTargets)
    {
        const uint32_t pagesPerRow = std::max<uint32_t>(1u, (rt.fbw * 64u + 63u) / 64u);
        const uint32_t pageHeight = pageHeightForPsm(rt.psm);
        const uint32_t rtPages = pagesPerRow * ((kRtHeight + pageHeight - 1u) / pageHeight);
        if (page + pageCount <= rt.fbp || page >= rt.fbp + rtPages)
            continue;
        const uint32_t first = page > rt.fbp ? page - rt.fbp : 0u;
        const uint32_t last = std::min<uint32_t>(page + pageCount - rt.fbp, rtPages);   // exclusive
        uint32_t rowFirst = (first / pagesPerRow) * pageHeight;
        uint32_t rowLast = std::min<uint32_t>(kRtHeight, ((last + pagesPerRow - 1u) / pagesPerRow) * pageHeight);
        // A transfer in the target's own layout writes exactly rows [dsay, dsay+rrh) below its
        // base page row: use them. The page-span window above starts at the base page, so a
        // 16x16 movie block at row 392 marked rows 0..408 dirty, and the next draw re-read the
        // whole window from the shadow — resurrecting rows of the last cinematic frame that the
        // GPU had already painted black (the movie strip at rows ~396-415 on SOCOM II's
        // black typing screen before the mission briefing, user report 2026-09-09).
        bool exact = false;
        if (transfer.bitbltbuf.dbw == rt.fbw && transfer.bitbltbuf.dpsm == rt.psm && page >= rt.fbp && (page - rt.fbp) % pagesPerRow == 0u)
        {
            const uint32_t baseRow = ((page - rt.fbp) / pagesPerRow) * pageHeight;
            const uint32_t y0 = baseRow + transfer.trxpos.dsay;
            const uint32_t y1 = y0 + transfer.trxreg.rrh;
            const uint32_t x0 = transfer.trxpos.dsax;
            const uint32_t x1 = std::min<uint32_t>(x0 + transfer.trxreg.rrw, rt.fbw * 64u);
            if (y0 < kRtHeight && y1 > y0 && x1 > x0)
            {
                rowFirst = std::max(rowFirst, y0);
                rowLast = std::min<uint32_t>(rowLast, y1);
                if (rt.dirtyRects.size() < 4096u)
                {
                    rt.dirtyRects.push_back({x0, y0, x1, std::min<uint32_t>(y1, kRtHeight)});
                    exact = true;
                }
            }
        }
        if (rowFirst >= rowLast)
            continue;
        {
            // PS2X_GS_TRACE_DIRTY=<frame>: from that frame on, log every dirty mark that lands in
            // the visible rows of a display buffer, with the transfer that caused it.
            static const long s_traceDirty = std::getenv("PS2X_GS_TRACE_DIRTY") ? std::strtol(std::getenv("PS2X_GS_TRACE_DIRTY"), nullptr, 0) : -1L;
            if (s_traceDirty >= 0 && static_cast<long>(m_frameCounter) >= s_traceDirty && rowFirst < 448u && rowLast > 380u)
                std::fprintf(stderr, "[gs-gl dirty] frame=%llu rt fbp=%03x rows %u..%u <- transfer dbp=%05x dbw=%u dpsm=%02x dst=(%u,%u) %ux%u pages %03x+%u\n",
                             (unsigned long long)m_frameCounter, rt.fbp, rowFirst, rowLast, transfer.bitbltbuf.dbp, transfer.bitbltbuf.dbw,
                             transfer.bitbltbuf.dpsm, transfer.trxpos.dsax, transfer.trxpos.dsay, transfer.trxreg.rrw, transfer.trxreg.rrh, page, pageCount);
        }
        if (!rt.dirtyRows)
        {
            rt.dirtyRowFirst = rowFirst;
            rt.dirtyRowLast = rowLast;
            rt.dirtyRows = true;
            rt.dirtyMask = 0u;
        }
        else
        {
            rt.dirtyRowFirst = std::min(rt.dirtyRowFirst, rowFirst);
            rt.dirtyRowLast = std::max(rt.dirtyRowLast, rowLast);
        }
        if (!exact)
            for (uint32_t band = rowFirst / 32u; band < (std::min<uint32_t>(rowLast, kRtHeight) + 31u) / 32u && band < 32u; ++band)
                rt.dirtyMask |= 1u << band;
    }
}

// Re-read the marked rows of a render target from the shadow VRAM (its own base/width/format).
void GSGlBackend::refreshDirtyRows(RenderTarget &rt)
{
    if (!rt.dirtyRows)
        return;
    // PS2X_GS_NO_DIRTY_REFRESH=1: A/B switch — drop the pending rows instead of re-reading them.
    static const bool s_noRefresh = std::getenv("PS2X_GS_NO_DIRTY_REFRESH") != nullptr;
    if (s_noRefresh)
    {
        rt.dirtyRows = false;
        rt.dirtyMask = 0u;
        rt.dirtyRects.clear();
        return;
    }
    {
        const long skip = traceSkip("PS2X_GS_TRACE_PRESENT");
        if (skip >= 0 && static_cast<long>(m_frameCounter) > skip && static_cast<long>(m_frameCounter) <= skip + 3)
            std::fprintf(stderr, "[gs-gl refresh] frame=%llu rt fbp=%03x rows %u..%u mask=%08x -> gpu\n", (unsigned long long)m_frameCounter,
                         rt.fbp, rt.dirtyRowFirst, rt.dirtyRowLast, rt.dirtyMask);
    }
    const uint32_t mask = rt.dirtyMask;
    std::vector<RenderTarget::DirtyRect> rects;
    rects.swap(rt.dirtyRects);
    rt.dirtyRows = false;
    rt.dirtyMask = 0u;
    const uint32_t w = std::min<uint32_t>(rt.width, rt.fbw * 64u);
    if (w == 0u)
        return;
    const uint32_t base = rt.fbp << 5;
    glBindTexture(GL_TEXTURE_2D, rt.color);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
    auto convert = [&](uint32_t p) -> uint32_t
    {
        if (rt.psm == GS_PSM_CT16 || rt.psm == GS_PSM_CT16S)
            return rgba5551To8888(p);
        if (rt.psm == GS_PSM_CT24)
            return p | 0x80000000u;
        return p;
    };
    // Exact rectangles first (uploads in the target's own layout: only the written pixels).
    for (const RenderTarget::DirtyRect &r : rects)
    {
        const uint32_t x0 = std::min(r.x0, w), x1 = std::min(r.x1, w);
        const uint32_t y0 = r.y0, y1 = std::min<uint32_t>(r.y1, rt.height);
        if (x1 <= x0 || y1 <= y0)
            continue;
        std::vector<uint32_t> px(static_cast<size_t>(x1 - x0) * (y1 - y0));
        for (uint32_t y = y0; y < y1; ++y)
            for (uint32_t x = x0; x < x1; ++x)
                px[static_cast<size_t>(y - y0) * (x1 - x0) + (x - x0)] = convert(readVramRaw(m_shadowMemory.data(), rt.psm, base, rt.fbw, x, y));
        glTexSubImage2D(GL_TEXTURE_2D, 0, static_cast<GLint>(x0), static_cast<GLint>(y0), static_cast<GLsizei>(x1 - x0), static_cast<GLsizei>(y1 - y0), GL_RGBA, GL_UNSIGNED_BYTE, px.data());
        rt.usedHeight = std::max(rt.usedHeight, y1);
    }
    // Re-read each run of dirty 32-row bands on its own; bands nobody uploaded into keep the
    // GPU's newer contents (the game's draws are not mirrored in the shadow).
    for (uint32_t band = 0; band < 32u;)
    {
        if (!(mask & (1u << band)))
        {
            ++band;
            continue;
        }
        uint32_t end = band;
        while (end < 32u && (mask & (1u << end)))
            ++end;
        const uint32_t y0 = band * 32u;
        const uint32_t y1 = std::min<uint32_t>(end * 32u, rt.height);
        band = end;
        if (y1 <= y0)
            continue;
        {
            const uint32_t ph = pageHeightForPsm(rt.psm), ppr = std::max<uint32_t>(1u, rt.fbw);
            const uint32_t p0 = rt.fbp + (y0 / ph) * ppr, p1 = rt.fbp + ((y1 + ph - 1u) / ph) * ppr;
            if (p1 > p0 && tracePagesHit(p0, p1 - p0))
                std::fprintf(stderr, "[gs-pages] frame=%llu refresh shadow->gpu rt fbp=%03x rows %u..%u pages %03x+%u\n",
                             (unsigned long long)m_frameCounter, rt.fbp, y0, y1, p0, p1 - p0);
        }
        std::vector<uint32_t> pixels(static_cast<size_t>(w) * (y1 - y0));
        for (uint32_t y = y0; y < y1; ++y)
            for (uint32_t x = 0; x < w; ++x)
            {
                uint32_t p = readVramRaw(m_shadowMemory.data(), rt.psm, base, rt.fbw, x, y);
                if (rt.psm == GS_PSM_CT16 || rt.psm == GS_PSM_CT16S)
                    p = rgba5551To8888(p);
                else if (rt.psm == GS_PSM_CT24)
                    p |= 0x80000000u;
                pixels[static_cast<size_t>(y - y0) * w + x] = p;
            }
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, static_cast<GLint>(y0), static_cast<GLsizei>(w), static_cast<GLsizei>(y1 - y0), GL_RGBA, GL_UNSIGNED_BYTE, pixels.data());
        rt.usedHeight = std::max(rt.usedHeight, y1);
    }
}

void GSGlBackend::executeClear(const GSContext &context, uint32_t rgba)
{
    RenderTarget *rt = getRenderTarget(context.frame.fbp, context.frame.fbw, context.frame.psm, true);
    // Rows an image upload wrote into this target before the clear must land before the clear,
    // not after it: without this the next draw's refreshDirtyRows painted the stale rows (the
    // last cinematic frame, uploaded as 16x16 blocks into the display buffer) over the cleared
    // black screen — SOCOM II showed a strip of the previous movie at rows ~396-415 during the
    // fade/typing screen before the mission briefing (user report 2026-09-09).
    refreshDirtyRows(*rt);
    {
        static const bool s_traceClear = std::getenv("PS2X_GS_TRACE_DISPFB") != nullptr;
        if (s_traceClear)
            std::fprintf(stderr, "[gs-gl clear] frame=%llu fbp=%03x fbw=%u psm=%02x scissor=(%d,%d)-(%d,%d) rgba=%08x\n",
                         (unsigned long long)m_frameCounter, context.frame.fbp, context.frame.fbw, context.frame.psm,
                         context.scissor.x0, context.scissor.y0, context.scissor.x1, context.scissor.y1, rgba);
    }
    glBindFramebuffer(GL_FRAMEBUFFER, rt->fbo);
    glViewport(0, 0, rt->width, rt->height);
    glEnable(GL_SCISSOR_TEST);
    glScissor(context.scissor.x0, context.scissor.y0,
              std::max<int>(0, context.scissor.x1 - context.scissor.x0 + 1),
              std::max<int>(0, context.scissor.y1 - context.scissor.y0 + 1));
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glClearColor((rgba & 0xFFu) / 255.0f, ((rgba >> 8) & 0xFFu) / 255.0f, ((rgba >> 16) & 0xFFu) / 255.0f, ((rgba >> 24) & 0xFFu) / 255.0f);
    glClear(GL_COLOR_BUFFER_BIT);
    rt->gpuDirty = true;
    rt->shadowStale = true;
    rt->usedHeight = std::max(rt->usedHeight, std::min<uint32_t>(kRtHeight, static_cast<uint32_t>(context.scissor.y1) + 1u));
    noteGpuRows(*rt, static_cast<uint32_t>(std::max<int>(0, context.scissor.y0)), std::min<uint32_t>(kRtHeight, static_cast<uint32_t>(context.scissor.y1) + 1u));
}

// Rows [y0, y1) of a target were written by the GPU since the shadow/CPU VRAM last synced with
// it. Downloads write back only this window: a target's texture is 1024 rows tall regardless of
// how much the game uses, and writing all of it back clobbers every buffer that lives below the
// target's base in VRAM (SOCOM II's movie staging buffer sits 140 pages after the display buffer:
// its freshly uploaded frame was overwritten with a stale copy, one page-row of the frame at a time).
void GSGlBackend::noteGpuRows(RenderTarget &rt, uint32_t y0, uint32_t y1)
{
    if (y1 <= y0)
        return;
    {
        const uint32_t ph = pageHeightForPsm(rt.psm), ppr = std::max<uint32_t>(1u, rt.fbw);
        const uint32_t p0 = rt.fbp + (y0 / ph) * ppr, p1 = rt.fbp + ((y1 + ph - 1u) / ph) * ppr;
        if (p1 > p0 && tracePagesHit(p0, p1 - p0))
            std::fprintf(stderr, "[gs-pages] frame=%llu gpu-draw rt fbp=%03x rows %u..%u pages %03x+%u (dirty %d %u..%u)\n",
                         (unsigned long long)m_frameCounter, rt.fbp, y0, y1, p0, p1 - p0, rt.dirtyRows ? 1 : 0, rt.dirtyRowFirst, rt.dirtyRowLast);
    }
    if (!rt.gpuRows)
    {
        rt.gpuRowFirst = y0;
        rt.gpuRowLast = y1;
        rt.gpuRows = true;
    }
    else
    {
        rt.gpuRowFirst = std::min(rt.gpuRowFirst, y0);
        rt.gpuRowLast = std::max(rt.gpuRowLast, y1);
    }
}

// Download a render target (GPU) into the shadow VRAM so texture decoding sees the drawn pixels.
void GSGlBackend::downloadRenderTargetToShadow(RenderTarget &rt)
{
    const uint32_t h = std::min<uint32_t>(rt.usedHeight, rt.height);
    std::vector<uint32_t> pixels(static_cast<size_t>(rt.width) * h);
    {
        // PS2X_GS_TRACE_PRESENT: log the downloads after the trace point (layout the shadow is written with).
        const long s_dlSkip = traceSkip("PS2X_GS_TRACE_PRESENT");
        static uint32_t s_dlPrinted = 0u;
        if (s_dlSkip >= 0 && static_cast<long>(m_frameCounter) > s_dlSkip && s_dlPrinted < 20u)
        {
            ++s_dlPrinted;
            std::fprintf(stderr, "[gs-gl download] frame=%llu rt fbp=%03x fbw=%u psm=%02x used=%u rows=%u dirty=%d %u..%u gpu=%d %u..%u\n",
                         (unsigned long long)m_frameCounter, rt.fbp, rt.fbw, rt.psm, rt.usedHeight, h,
                         rt.dirtyRows ? 1 : 0, rt.dirtyRowFirst, rt.dirtyRowLast, rt.gpuRows ? 1 : 0, rt.gpuRowFirst, rt.gpuRowLast);
        }
    }
    // Called from the texture path in the middle of a draw batch: restore the batch target's
    // FBO afterwards, or the draw lands in this target (SOCOM II's movie copy sprite went into
    // the staging buffer instead of the display buffer whenever the two were laid out that way).
    GLint prevFbo = 0;
    glGetIntegerv(GL_FRAMEBUFFER_BINDING, &prevFbo);
    glBindFramebuffer(GL_FRAMEBUFFER, rt.fbo);
    glPixelStorei(GL_PACK_ALIGNMENT, 4);
    glReadPixels(0, 0, rt.width, h, GL_RGBA, GL_UNSIGNED_BYTE, pixels.data());
    const uint32_t base = rt.fbp << 5;
    // Only rows the GPU drew since the last sync (see noteGpuRows); nothing else is stale.
    const uint32_t yStart = rt.gpuRows ? std::min(h, rt.gpuRowFirst) : 0u;
    const uint32_t yEnd = rt.gpuRows ? std::min(h, rt.gpuRowLast) : 0u;
    const uint32_t xEnd = std::min<uint32_t>(rt.width, std::max<uint32_t>(1u, rt.fbw) * 64u);
    if (yEnd > yStart)
    {
        const uint32_t ph = pageHeightForPsm(rt.psm), ppr = std::max<uint32_t>(1u, rt.fbw);
        const uint32_t p0 = rt.fbp + (yStart / ph) * ppr, p1 = rt.fbp + ((yEnd + ph - 1u) / ph) * ppr;
        if (p1 > p0 && tracePagesHit(p0, p1 - p0))
            std::fprintf(stderr, "[gs-pages] frame=%llu download gpu->shadow rt fbp=%03x rows %u..%u (skip dirty %d %u..%u) pages %03x+%u\n",
                         (unsigned long long)m_frameCounter, rt.fbp, yStart, yEnd, rt.dirtyRows ? 1 : 0, rt.dirtyRowFirst, rt.dirtyRowLast, p0, p1 - p0);
    }
    for (uint32_t y = yStart; y < yEnd; ++y)
    {
        // Rows an image upload wrote into the shadow after the last GPU draw hold the newest
        // data (the GPU copy is refreshed from them lazily): do not clobber them with the stale
        // GPU pixels. SOCOM II's movie path clears the movie buffer on the GPU, uploads the next
        // decoded frame into it, then textures from it; this download used to overwrite the
        // uploaded frame with the clear, so every movie frame textured black.
        if (rt.dirtyRows && ((rt.dirtyMask & (1u << std::min<uint32_t>(31u, y / 32u))) || std::any_of(rt.dirtyRects.begin(), rt.dirtyRects.end(), [&](const RenderTarget::DirtyRect &r) { return y >= r.y0 && y < r.y1; })))
            continue;
        // Only the buffer's own width: the texture is 1024 px wide regardless of FBW, and pixels
        // past FBW*64 address the *next* page row's first columns (SOCOM II's movie staging
        // buffer, FBW 10, got its frame rows 96..128 of page columns 0-5 blacked out by the GPU
        // rows 64..96 of the same target — a seam at x=384 on every movie frame).
        for (uint32_t x = 0; x < xEnd; ++x)
        {
            uint32_t p = pixels[static_cast<size_t>(y) * rt.width + x];
            if (rt.psm == GS_PSM_CT16 || rt.psm == GS_PSM_CT16S)
                p = rgba8888To5551(p);
            writeVramRaw(m_shadowMemory.data(), rt.psm, base, rt.fbw, x, y, p);
        }
    }
    rt.shadowStale = false;
    rt.gpuRows = false;
    glBindFramebuffer(GL_FRAMEBUFFER, static_cast<GLuint>(prevFbo));
}

// Download into the game thread's authoritative VRAM (guest reads GS memory).
void GSGlBackend::downloadRenderTargetToCpu(RenderTarget &rt)
{
    const uint32_t h = std::min<uint32_t>(rt.usedHeight, rt.height);
    std::vector<uint32_t> pixels(static_cast<size_t>(rt.width) * h);
    // Called from the texture path in the middle of a draw batch: restore the batch target's
    // FBO afterwards, or the draw lands in this target (SOCOM II's movie copy sprite went into
    // the staging buffer instead of the display buffer whenever the two were laid out that way).
    GLint prevFbo = 0;
    glGetIntegerv(GL_FRAMEBUFFER_BINDING, &prevFbo);
    glBindFramebuffer(GL_FRAMEBUFFER, rt.fbo);
    glPixelStorei(GL_PACK_ALIGNMENT, 4);
    glReadPixels(0, 0, rt.width, h, GL_RGBA, GL_UNSIGNED_BYTE, pixels.data());
    const uint32_t base = rt.fbp << 5;
    const uint32_t yStart = rt.gpuRows ? std::min(h, rt.gpuRowFirst) : 0u;   // see downloadRenderTargetToShadow
    const uint32_t yEnd = rt.gpuRows ? std::min(h, rt.gpuRowLast) : 0u;
    const uint32_t xEnd = std::min<uint32_t>(rt.width, std::max<uint32_t>(1u, rt.fbw) * 64u);
    if (yEnd > yStart)
    {
        const uint32_t ph = pageHeightForPsm(rt.psm), ppr = std::max<uint32_t>(1u, rt.fbw);
        const uint32_t p0 = rt.fbp + (yStart / ph) * ppr, p1 = rt.fbp + ((yEnd + ph - 1u) / ph) * ppr;
        if (p1 > p0 && tracePagesHit(p0, p1 - p0))
            std::fprintf(stderr, "[gs-pages] frame=%llu download gpu->cpu rt fbp=%03x rows %u..%u (skip dirty %d %u..%u) pages %03x+%u\n",
                         (unsigned long long)m_frameCounter, rt.fbp, yStart, yEnd, rt.dirtyRows ? 1 : 0, rt.dirtyRowFirst, rt.dirtyRowLast, p0, p1 - p0);
    }
    for (uint32_t y = yStart; y < yEnd; ++y)
    {
        if (rt.dirtyRows && ((rt.dirtyMask & (1u << std::min<uint32_t>(31u, y / 32u))) || std::any_of(rt.dirtyRects.begin(), rt.dirtyRects.end(), [&](const RenderTarget::DirtyRect &r) { return y >= r.y0 && y < r.y1; })))   // see downloadRenderTargetToShadow
            continue;
        // Only the buffer's own width: the texture is 1024 px wide regardless of FBW, and pixels
        // past FBW*64 address the *next* page row's first columns (SOCOM II's movie staging
        // buffer, FBW 10, got its frame rows 96..128 of page columns 0-5 blacked out by the GPU
        // rows 64..96 of the same target — a seam at x=384 on every movie frame).
        for (uint32_t x = 0; x < xEnd; ++x)
        {
            uint32_t p = pixels[static_cast<size_t>(y) * rt.width + x];
            if (rt.psm == GS_PSM_CT16 || rt.psm == GS_PSM_CT16S)
                p = rgba8888To5551(p);
            m_cpu->WriteVram(rt.psm, base, rt.fbw, x, y, p);
            writeVramRaw(m_shadowMemory.data(), rt.psm, base, rt.fbw, x, y, p);
        }
    }
    rt.gpuDirty = false;
    rt.shadowStale = false;
    rt.gpuRows = false;
    glBindFramebuffer(GL_FRAMEBUFFER, static_cast<GLuint>(prevFbo));
}

void GSGlBackend::executeReadback()
{
    for (RenderTarget &rt : m_renderTargets)
        if (rt.gpuDirty)
            downloadRenderTargetToCpu(rt);
}

void GSGlBackend::executePresent(const GSPresentationRequest &request)
{
    const GSFrameReg display1 = decodeDisplayFrame(request.dispfb1);
    const GSFrameReg display2 = decodeDisplayFrame(request.dispfb2);
    const bool en1 = (request.pmode & 1ull) != 0ull && hasDisplaySetup(request.display1, display1);
    const bool en2 = (request.pmode & 2ull) != 0ull && hasDisplaySetup(request.display2, display2);
    const GSFrameReg &display = en1 ? display1 : display2;
    uint32_t width = 0u, height = 0u;
    decodeDisplaySize(en1 ? request.display1 : request.display2, width, height);
    if (!en1 && !en2)
    {
        // Display off (PMODE EN1=EN2=0): the host shows black. Blank the dump pixels too so
        // PS2X_FRAME_DUMP counters do not report the last presented frame as still visible.
        m_presentTexture = 0u;
        if (m_presentPixelsRequested)
        {
            std::lock_guard<std::mutex> lock(m_queueMutex);
            m_presentPixels.assign(static_cast<size_t>(kHostFrameWidth) * kHostFrameHeight * 4u, 0u);
        }
        static uint32_t s_offLogged = 0u;
        if (s_offLogged < 2u)
        {
            ++s_offLogged;
            std::fprintf(stderr, "[gs-gl present] frame=%llu display off (pmode=%llx)\n", (unsigned long long)m_frameCounter, (unsigned long long)request.pmode);
        }
        return;
    }

    RenderTarget *rt = getRenderTarget(display.fbp, display.fbw, display.psm, false);
    if (!rt)
    {
        // The display base may sit inside a larger target (or an upload-only buffer).
        for (RenderTarget &candidate : m_renderTargets)
        {
            const uint32_t span = pageSpan(candidate.psm, candidate.fbw, std::min<uint32_t>(candidate.usedHeight, 512u));
            if (display.fbp >= candidate.fbp && display.fbp < candidate.fbp + span)
            {
                rt = &candidate;
                break;
            }
        }
    }
    if (!rt)
        rt = getRenderTarget(display.fbp, display.fbw, display.psm, true);
    if (request.hasPreferredSource && request.preferredDestFbp == display.fbp)
    {
        if (RenderTarget *pref = getRenderTarget(request.preferredSource.fbp, request.preferredSource.fbw, request.preferredSource.psm, false))
            if (pref->gpuDirty)
                rt = pref;
    }
    // PS2X_GS_TRACE_PRESENT: sample the displayed target before the shadow refresh, and record
    // the refresh window, to tell a blank target from a refresh that blanks it.
    {
        static const long s_skipPre = [] { const char *e = std::getenv("PS2X_GS_TRACE_PRESENT"); return e ? std::strtol(e, nullptr, 0) : -1L; }();
        static uint32_t s_printedPre = 0u;
        // After the skip: the first 30 presents, then every present that still has pending
        // dirty rows below 512 (the visible part of the display buffers) — a refresh that would
        // repaint rows of a buffer the game already drew over.
        if (s_skipPre >= 0 && static_cast<long>(m_frameCounter + 1u) > s_skipPre &&
            (s_printedPre < 30u || (rt->dirtyRows && rt->dirtyRowFirst < 512u)))
        {
            ++s_printedPre;
            uint8_t px[4] = {0, 0, 0, 0};
            glBindFramebuffer(GL_READ_FRAMEBUFFER, rt->fbo);
            glReadPixels(320, 224, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px);
            glBindFramebuffer(GL_FRAMEBUFFER, 0);
            std::fprintf(stderr, "[gs-gl present-pre] frame=%llu rt fbp=%03x fbo=%u used=%u centre=%02x%02x%02x%02x dirty=%d rows=%u..%u shadowStale=%d gpuDirty=%d pref=%d\n",
                         (unsigned long long)(m_frameCounter + 1u), rt->fbp, rt->fbo, rt->usedHeight, px[0], px[1], px[2], px[3],
                         rt->dirtyRows ? 1 : 0, rt->dirtyRowFirst, rt->dirtyRowLast, rt->shadowStale ? 1 : 0, rt->gpuDirty ? 1 : 0,
                         (request.hasPreferredSource && request.preferredDestFbp == display.fbp) ? 1 : 0);
        }
    }
    // DISPLAY gives the field height (224) when the game renders full frames (448 rows) and
    // scans out interlaced; present the rows that were actually drawn in that case.
    refreshDirtyRows(*rt);
    // PS2X_GS_DUMP_DISPLAY="<dir>:<t0>:<t1>": every ~2 s of host time in [t0, t1) write the
    // displayed buffer three ways (gpu = the GL target, shadow = the render thread's VRAM copy,
    // cpu = the authoritative game-thread VRAM) as PPMs, to tell which layer holds a pixel.
    {
        static const char *const s_dumpEnv = std::getenv("PS2X_GS_DUMP_DISPLAY");
        if (s_dumpEnv)
        {
            static const auto s_epoch = std::chrono::steady_clock::now();
            static double s_next = -1.0;
            static std::string s_dir;
            static double s_t0 = 0.0, s_t1 = 0.0;
            if (s_next < 0.0)
            {
                std::string spec(s_dumpEnv);
                // "<dir>:<t0>:<t1>" — split on the LAST two colons (the dir may carry a drive letter).
                const size_t c2 = spec.rfind(':');
                const size_t c1 = c2 == std::string::npos ? std::string::npos : spec.rfind(':', c2 - 1);
                s_dir = spec.substr(0, c1);
                s_t0 = c1 == std::string::npos ? 0.0 : std::atof(spec.c_str() + c1 + 1);
                s_t1 = c2 == std::string::npos ? 1e9 : std::atof(spec.c_str() + c2 + 1);
                s_next = s_t0;
            }
            const double elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - s_epoch).count();
            if (elapsed >= s_next && elapsed < s_t1)
            {
                s_next = elapsed + 2.0;
                const uint32_t w = std::min<uint32_t>(640u, rt->width), h = std::min<uint32_t>(448u, rt->height);
                std::vector<uint32_t> gpu(static_cast<size_t>(rt->width) * h);
                glBindFramebuffer(GL_READ_FRAMEBUFFER, rt->fbo);
                glReadPixels(0, 0, rt->width, h, GL_RGBA, GL_UNSIGNED_BYTE, gpu.data());
                glBindFramebuffer(GL_FRAMEBUFFER, 0);
                const uint32_t base = rt->fbp << 5;
                auto writePpm = [&](const char *tag, auto fetch)
                {
                    char name[512];
                    std::snprintf(name, sizeof(name), "%s/display_%03.0fs_fbp%03x_%s.ppm", s_dir.c_str(), elapsed, rt->fbp, tag);
                    FILE *f = std::fopen(name, "wb");
                    if (!f)
                        return;
                    std::fprintf(f, "P6\n%u %u\n255\n", w, h);
                    for (uint32_t y = 0; y < h; ++y)
                        for (uint32_t x = 0; x < w; ++x)
                        {
                            const uint32_t p = fetch(x, y);
                            const uint8_t rgb[3] = {static_cast<uint8_t>(p & 0xFFu), static_cast<uint8_t>((p >> 8) & 0xFFu), static_cast<uint8_t>((p >> 16) & 0xFFu)};
                            std::fwrite(rgb, 1, 3, f);
                        }
                    std::fclose(f);
                };
                writePpm("gpu", [&](uint32_t x, uint32_t y) { return gpu[static_cast<size_t>(y) * rt->width + x]; });
                writePpm("shadow", [&](uint32_t x, uint32_t y) { return readVramRaw(m_shadowMemory.data(), rt->psm, base, rt->fbw, x, y); });
                writePpm("cpu", [&](uint32_t x, uint32_t y) { return m_cpu->ReadVram(rt->psm, base, rt->fbw, x, y); });
                std::fprintf(stderr, "[gs-gl dump-display] t=%.1f frame=%llu fbp=%03x -> %s\n", elapsed, (unsigned long long)m_frameCounter, rt->fbp, s_dir.c_str());
            }
        }
    }
    // Copy the presented rectangle into a dedicated texture: the render target keeps being drawn
    // into (the next frame's clear lands on it while it is on screen), which showed as flicker.
    m_presentWidth = std::min<uint32_t>(width, rt->width);
    m_presentHeight = std::min<uint32_t>(height, rt->height);
    if (m_presentCopyTexture == 0u || m_presentTexWidth != rt->width || m_presentTexHeight != rt->height)
    {
        if (m_presentCopyTexture != 0u)
            glDeleteTextures(1, &m_presentCopyTexture);
        if (m_presentCopyFbo == 0u)
            glGenFramebuffers(1, &m_presentCopyFbo);
        glGenTextures(1, &m_presentCopyTexture);
        glBindTexture(GL_TEXTURE_2D, m_presentCopyTexture);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, rt->width, rt->height, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        m_presentTexWidth = rt->width;
        m_presentTexHeight = rt->height;
    }
    glBindFramebuffer(GL_READ_FRAMEBUFFER, rt->fbo);
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, m_presentCopyFbo);
    glFramebufferTexture2D(GL_DRAW_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, m_presentCopyTexture, 0);
    glDisable(GL_SCISSOR_TEST);
    // glBlitFramebuffer honours the colour mask: a frame that ends with an FBMSK-masked draw
    // would otherwise leave the copy black while the render target itself is fine.
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glBlitFramebuffer(0, 0, static_cast<GLint>(m_presentWidth), static_cast<GLint>(m_presentHeight),
                      0, 0, static_cast<GLint>(m_presentWidth), static_cast<GLint>(m_presentHeight),
                      GL_COLOR_BUFFER_BIT, GL_NEAREST);
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    m_presentTexture = m_presentCopyTexture;
    m_presentFbp = display.fbp;

    // PMODE merge: both read circuits enabled on different frame buffers. SOCOM II shows its
    // pre-rendered movies this way — circuit 1 reads a black buffer, circuit 2 the buffer the
    // decoded frames are uploaded into, ALP=0x7f (MMOD=1) — so presenting circuit 1 alone was a
    // black screen. Copy circuit 2's target too and hand it out with alpha = its weight
    // (1 - ALP/255); the host draws it alpha-blended over circuit 1. SLBG=1 (background colour
    // instead of circuit 2) and MMOD=0 (per-pixel alpha from circuit 1) fall back to circuit 1.
    m_presentTexture2 = 0u;
    if (en1 && en2 && display2.fbp != display1.fbp)
    {
        const bool mmod = (request.pmode & (1ull << 5)) != 0ull;
        const bool slbg = (request.pmode & (1ull << 7)) != 0ull;
        const uint32_t alp = static_cast<uint32_t>((request.pmode >> 8) & 0xFFull);
        if (mmod && !slbg && alp < 0xFFu)
        {
            RenderTarget *rt2 = getRenderTarget(display2.fbp, display2.fbw, display2.psm, false);
            if (!rt2)
            {
                for (RenderTarget &candidate : m_renderTargets)
                {
                    const uint32_t span = pageSpan(candidate.psm, candidate.fbw, std::min<uint32_t>(candidate.usedHeight, 512u));
                    if (display2.fbp >= candidate.fbp && display2.fbp < candidate.fbp + span)
                    {
                        rt2 = &candidate;
                        break;
                    }
                }
            }
            if (rt2 && rt2 != rt)
            {
                refreshDirtyRows(*rt2);
                if (m_presentCopyTexture2 == 0u || m_presentTexWidth != rt->width || m_presentTexHeight != rt->height)
                {
                    if (m_presentCopyTexture2 != 0u)
                        glDeleteTextures(1, &m_presentCopyTexture2);
                    if (m_presentCopyFbo2 == 0u)
                        glGenFramebuffers(1, &m_presentCopyFbo2);
                    glGenTextures(1, &m_presentCopyTexture2);
                    glBindTexture(GL_TEXTURE_2D, m_presentCopyTexture2);
                    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, rt->width, rt->height, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
                }
                const uint32_t w2 = std::min<uint32_t>(m_presentWidth, rt2->width);
                const uint32_t h2 = std::min<uint32_t>(m_presentHeight, rt2->height);
                glBindFramebuffer(GL_READ_FRAMEBUFFER, rt2->fbo);
                glBindFramebuffer(GL_DRAW_FRAMEBUFFER, m_presentCopyFbo2);
                glFramebufferTexture2D(GL_DRAW_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, m_presentCopyTexture2, 0);
                glDisable(GL_SCISSOR_TEST);
                glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
                glBlitFramebuffer(0, 0, static_cast<GLint>(w2), static_cast<GLint>(h2),
                                  0, 0, static_cast<GLint>(w2), static_cast<GLint>(h2),
                                  GL_COLOR_BUFFER_BIT, GL_NEAREST);
                // Alpha channel := circuit 2's weight in the merge (RGB untouched).
                glBindFramebuffer(GL_FRAMEBUFFER, m_presentCopyFbo2);
                glColorMask(GL_FALSE, GL_FALSE, GL_FALSE, GL_TRUE);
                glClearColor(0.0f, 0.0f, 0.0f, 1.0f - static_cast<float>(alp) / 255.0f);
                glClear(GL_COLOR_BUFFER_BIT);
                glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
                glBindFramebuffer(GL_FRAMEBUFFER, 0);
                m_presentTexture2 = m_presentCopyTexture2;
            }
        }
    }
    ++m_frameCounter;
    // PS2X_GS_TRACE_PRESENT=<skip>: after <skip> presents, print 30 presents with the copy's
    // centre pixel (rgba) and the GL error state, to tell a black copy from a black draw.
    {
        static const long s_skip = [] { const char *e = std::getenv("PS2X_GS_TRACE_PRESENT"); return e ? std::strtol(e, nullptr, 0) : -1L; }();
        static uint32_t s_printed = 0u;
        if (s_skip >= 0 && static_cast<long>(m_frameCounter) > s_skip && s_printed < 30u)
        {
            ++s_printed;
            uint8_t px[4] = {0, 0, 0, 0};
            glBindFramebuffer(GL_READ_FRAMEBUFFER, m_presentCopyFbo);
            glReadPixels(static_cast<GLint>(m_presentWidth / 2u), static_cast<GLint>(m_presentHeight / 2u), 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px);
            glBindFramebuffer(GL_FRAMEBUFFER, 0);
            uint8_t px2[4] = {0, 0, 0, 0};
            if (m_presentTexture2 != 0u)
            {
                glBindFramebuffer(GL_READ_FRAMEBUFFER, m_presentCopyFbo2);
                glReadPixels(static_cast<GLint>(m_presentWidth / 2u), static_cast<GLint>(m_presentHeight / 2u), 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px2);
                glBindFramebuffer(GL_FRAMEBUFFER, 0);
            }
            std::fprintf(stderr, "[gs-gl present-trace] frame=%llu en1=%d en2=%d pmode=%llx fbp=%03x fbp2=%03x rt#fbo=%u %ux%u copy=%u centre=%02x%02x%02x%02x tex2=%u centre2=%02x%02x%02x%02x glerr=0x%x\n",
                         (unsigned long long)m_frameCounter, en1 ? 1 : 0, en2 ? 1 : 0, (unsigned long long)request.pmode, display.fbp, display2.fbp, rt->fbo,
                         m_presentWidth, m_presentHeight, m_presentCopyTexture, px[0], px[1], px[2], px[3],
                         m_presentTexture2, px2[0], px2[1], px2[2], px2[3], glGetError());
        }
    }
    {
        static uint32_t s_logged = 0u;
        // PS2X_GS_TRACE_DISPFB=1: log every change of the displayed buffer (fbp/fbw/psm/size).
        static const bool s_traceDispfb = std::getenv("PS2X_GS_TRACE_DISPFB") != nullptr;
        static uint64_t s_lastKey = ~0ull;
        const uint64_t key = (static_cast<uint64_t>(display.fbp) << 32) | (display.fbw << 24) | (display.psm << 16) | (width << 4) | (height & 0xFu) | (static_cast<uint64_t>(height) << 40);
        const bool changed = s_traceDispfb && key != s_lastKey;
        s_lastKey = key;
        if (changed || (s_logged < 4u && (m_frameCounter == 1u || m_frameCounter == 600u || m_frameCounter == 1200u || m_frameCounter == 1800u)))
        {
            if (!changed)
                ++s_logged;
            std::fprintf(stderr, "[gs-gl present] frame=%llu dispfb fbp=%03x fbw=%u psm=%02x display=%ux%u smode2=%llx rt=%ux%u used=%u -> present %ux%u\n",
                         (unsigned long long)m_frameCounter, display.fbp, display.fbw, display.psm, width, height,
                         (unsigned long long)request.smode2, rt->width, rt->height, rt->usedHeight, m_presentWidth, m_presentHeight);
        }
    }

    if (m_presentPixelsRequested)
    {
        std::vector<uint32_t> pixels(static_cast<size_t>(m_presentWidth) * m_presentHeight);
        glBindFramebuffer(GL_FRAMEBUFFER, rt->fbo);
        glPixelStorei(GL_PACK_ALIGNMENT, 4);
        glReadPixels(0, 0, m_presentWidth, m_presentHeight, GL_RGBA, GL_UNSIGNED_BYTE, pixels.data());
        std::lock_guard<std::mutex> lock(m_queueMutex);
        m_presentPixels.assign(static_cast<size_t>(kHostFrameWidth) * kHostFrameHeight * 4u, 0u);
        for (uint32_t y = 0; y < m_presentHeight && y < kHostFrameHeight; ++y)
            std::memcpy(m_presentPixels.data() + static_cast<size_t>(y) * kHostFrameWidth * 4u,
                        pixels.data() + static_cast<size_t>(y) * m_presentWidth,
                        std::min<uint32_t>(m_presentWidth, kHostFrameWidth) * 4u);
    }
}

// ---------------------------------------------------------------------------------------------
// Textures
// ---------------------------------------------------------------------------------------------
uint32_t GSGlBackend::decodeTexture(const GSDrawState &state, const TextureKey &key, uint32_t width, uint32_t height, uint32_t pageStart, uint32_t pageCount)
{
    const GSTex0Reg &tex = state.context.tex0;
    std::vector<uint32_t> pixels(static_cast<size_t>(width) * height);
    {
        // PS2X_GS_TRACE_PRESENT: the same per-page-column scan as upload-scan, at decode time,
        // for the movie staging buffers (tbp0 0 / 0x1180, frame rows 96..336 in the buffer).
        const long s_dcSkip = traceSkip("PS2X_GS_TRACE_PRESENT");
        static uint32_t s_dcPrinted = 0u;
        const bool dcPrint = s_dcSkip >= 0 && static_cast<long>(m_frameCounter) > s_dcSkip && s_dcPrinted < 12u;
        if ((dcPrint || (m_movieStartFrame != 0u && m_seamFrame == 0u)) && tex.psm == GS_PSM_CT32 &&
            (tex.tbp0 == 0u || tex.tbp0 == 0x1180u) && width >= 640u)
        {
            int rows[10] = {-1, -1, -1, -1, -1, -1, -1, -1, -1, -1};
            char line[256];
            int n = std::snprintf(line, sizeof(line), "[gs-gl decode-scan] frame=%llu tbp0=%05x tbw=%u first-row/page-col:",
                                  (unsigned long long)m_frameCounter, tex.tbp0, tex.tbw);
            for (uint32_t c = 0; c < 10u && n < 240; ++c)
            {
                int firstRow = -1;
                for (uint32_t y = 90u; y < 340u; ++y)
                {
                    uint32_t sum = 0, cnt = 0;
                    for (uint32_t x = c * 64u; x < c * 64u + 64u; x += 4u, ++cnt)
                    {
                        const uint32_t p = readVramRaw(m_shadowMemory.data(), tex.psm, tex.tbp0, tex.tbw, x, y);
                        sum += ((p & 0xFFu) + ((p >> 8) & 0xFFu) + ((p >> 16) & 0xFFu)) / 3u;
                    }
                    if (sum > 8u * cnt) { firstRow = static_cast<int>(y); break; }
                }
                rows[c] = firstRow;
                n += std::snprintf(line + n, sizeof(line) - n, " %d", firstRow);
            }
            const bool seam = rows[0] > 0 && rows[6] > 0 && rows[0] != rows[6];
            if (seam && m_seamFrame == 0u)
            {
                m_seamFrame = m_frameCounter ? m_frameCounter : 1u;
                std::fprintf(stderr, "[gs-gl seam] first seen at frame=%llu (movie start frame=%llu): %s\n",
                             (unsigned long long)m_frameCounter, (unsigned long long)m_movieStartFrame, line);
            }
            if (dcPrint)
            {
                ++s_dcPrinted;
                std::fprintf(stderr, "%s\n", line);
            }
        }
    }
    // Experiment: PS2X_GS_TEX_FROM_CPU=1 decodes from the authoritative (game-thread) VRAM instead
    // of the render-thread shadow, to tell shadow staleness from decode bugs.
    static const bool s_fromCpu = std::getenv("PS2X_GS_TEX_FROM_CPU") != nullptr;
    static std::vector<uint8_t> s_cpuCopy;
    if (s_fromCpu)
        m_cpu->SnapshotVram(s_cpuCopy);
    uint8_t *vram = s_fromCpu && !s_cpuCopy.empty() ? s_cpuCopy.data() : m_shadowMemory.data();
    const uint32_t clutWidth = (state.texclut.cbw != 0u) ? static_cast<uint32_t>(state.texclut.cbw) : 1u;
    const bool indexed = tex.psm == GS_PSM_T8 || tex.psm == GS_PSM_T8H || tex.psm == GS_PSM_T4 || tex.psm == GS_PSM_T4HL || tex.psm == GS_PSM_T4HH;

    // Decode the CLUT once (256 entries) for indexed formats.
    uint32_t clut[256];
    if (indexed)
    {
        for (uint32_t i = 0; i < 256u; ++i)
        {
            const uint32_t clutIndex = resolveClutIndex(static_cast<uint8_t>(i), tex.cpsm, tex.csm, tex.csa, tex.psm);
            const uint32_t clutX = static_cast<uint32_t>(state.texclut.cou) + (clutIndex & 0x0Fu);
            const uint32_t clutY = static_cast<uint32_t>(state.texclut.cov) + (clutIndex >> 4);
            uint32_t c = 0u;
            switch (tex.cpsm)
            {
            case GS_PSM_CT32: c = applyTexa(state.texa, GS_PSM_CT32, GSMem::ReadCT32(vram, tex.cbp, clutWidth, clutX, clutY)); break;
            case GS_PSM_CT24: c = applyTexa(state.texa, GS_PSM_CT24, GSMem::ReadCT24(vram, tex.cbp, clutWidth, clutX, clutY)); break;
            case GS_PSM_CT16: c = applyTexa(state.texa, GS_PSM_CT16, rgba5551To8888(GSMem::ReadCT16(vram, tex.cbp, clutWidth, clutX, clutY))); break;
            case GS_PSM_CT16S: c = applyTexa(state.texa, GS_PSM_CT16S, rgba5551To8888(GSMem::ReadCT16S(vram, tex.cbp, clutWidth, clutX, clutY))); break;
            default: c = 0xFFFF00FFu; break;
            }
            clut[i] = c;
        }
        // Diagnostic (with PS2X_GS_DUMP_TEX, after PS2X_GS_GL_DEBUG_AFTER presents, first 64
        // decodes): does the shadow VRAM's CLUT match the authoritative VRAM?
        static const bool s_clutDiag = std::getenv("PS2X_GS_DUMP_TEX") != nullptr;
        static const unsigned long long s_clutAfter = std::getenv("PS2X_GS_GL_DEBUG_AFTER") ? std::strtoull(std::getenv("PS2X_GS_GL_DEBUG_AFTER"), nullptr, 0) : 0ull;
        static uint32_t s_clutDiagCount = 0;
        if (s_clutDiag && m_frameCounter >= s_clutAfter && s_clutDiagCount++ < 64u)
        {
            uint32_t mismatches = 0u;
            for (uint32_t i = 0; i < 256u; ++i)
            {
                const uint32_t clutIndex = resolveClutIndex(static_cast<uint8_t>(i), tex.cpsm, tex.csm, tex.csa, tex.psm);
                const uint32_t clutX = static_cast<uint32_t>(state.texclut.cou) + (clutIndex & 0x0Fu);
                const uint32_t clutY = static_cast<uint32_t>(state.texclut.cov) + (clutIndex >> 4);
                const uint32_t shadowRaw = readVramRaw(vram, tex.cpsm, tex.cbp, clutWidth, clutX, clutY);
                const uint32_t cpuRaw = m_cpu->ReadVram(tex.cpsm, tex.cbp, clutWidth, clutX, clutY);
                if (shadowRaw != cpuRaw)
                    ++mismatches;
            }
            std::fprintf(stderr, "[gs-gl tex] tbp0=%05x psm=%02x cbp=%05x cpsm=%02x cbw=%u cou=%u cov=%u clut mismatches shadow vs cpu: %u; clut[0..3]=%08x %08x %08x %08x\n",
                         tex.tbp0, tex.psm, tex.cbp, tex.cpsm, clutWidth, state.texclut.cou, state.texclut.cov, mismatches, clut[0], clut[1], clut[2], clut[3]);
        }
    }

    // Row spans (GSMem::ReadSpan: the same per-pixel Read* inlined, no page arithmetic per pixel;
    // this loop was ~14% of the GL thread), conversion chosen once per texture.
    {
        std::vector<uint32_t> row(width);
        const bool spanOk = GSMem::ReadSpan(tex.psm, vram, tex.tbp0, tex.tbw, 0u, 0u, 0u, row.data());
        enum class Conv { Color32, Color16, Indexed, Missing } conv;
        switch (tex.psm)
        {
        case GS_PSM_CT32: case GS_PSM_CT24: case GS_PSM_Z32: case GS_PSM_Z24: conv = Conv::Color32; break;
        case GS_PSM_CT16: case GS_PSM_CT16S: case GS_PSM_Z16: case GS_PSM_Z16S: conv = Conv::Color16; break;
        default: conv = indexed ? Conv::Indexed : Conv::Missing; break;
        }
        for (uint32_t y = 0; y < height; ++y)
        {
            if (spanOk)
                GSMem::ReadSpan(tex.psm, vram, tex.tbp0, tex.tbw, 0u, y, width, row.data());
            else
                for (uint32_t x = 0; x < width; ++x)
                    row[x] = readVramRaw(vram, tex.psm, tex.tbp0, tex.tbw, x, y);
            uint32_t *dst = pixels.data() + static_cast<size_t>(y) * width;
            switch (conv)
            {
            case Conv::Color32:
                for (uint32_t x = 0; x < width; ++x)
                    dst[x] = applyTexa(state.texa, tex.psm, row[x]);
                break;
            case Conv::Color16:
                for (uint32_t x = 0; x < width; ++x)
                    dst[x] = applyTexa(state.texa, tex.psm, rgba5551To8888(row[x]));
                break;
            case Conv::Indexed:
                for (uint32_t x = 0; x < width; ++x)
                    dst[x] = clut[row[x] & 0xFFu];
                break;
            default:
                for (uint32_t x = 0; x < width; ++x)
                    dst[x] = 0xFFFF00FFu;
                break;
            }
        }
    }

    // PS2X_GS_DUMP_TEX=<dir>: write every decoded texture as a PPM (RGB) + PGM (alpha) for inspection.
    static const char *s_dumpDir = std::getenv("PS2X_GS_DUMP_TEX");
    // Gated by PS2X_GS_GL_DEBUG_AFTER (presents) and capped: ungated it wrote 136k files per boot.
    static const unsigned long long s_dumpAfter = std::getenv("PS2X_GS_GL_DEBUG_AFTER") ? std::strtoull(std::getenv("PS2X_GS_GL_DEBUG_AFTER"), nullptr, 0) : 0ull;
    static uint32_t s_dumpCount = 0;
    if (s_dumpDir && m_frameCounter >= s_dumpAfter && s_dumpCount++ < 6u)
    {
        static uint32_t s_dumpIndex = 0;
        char path[512];
        std::snprintf(path, sizeof(path), "%s/tex_%03u_tbp%05x_psm%02x_%ux%u_cbp%05x_cpsm%02x.ppm", s_dumpDir, s_dumpIndex,
                      tex.tbp0, tex.psm, width, height, tex.cbp, tex.cpsm);
        if (FILE *fp = std::fopen(path, "wb"))
        {
            std::fprintf(fp, "P6\n%u %u\n255\n", width, height);
            for (uint32_t i = 0; i < width * height; ++i)
                std::fwrite(&pixels[i], 1, 3, fp);
            std::fclose(fp);
        }
        std::snprintf(path, sizeof(path), "%s/tex_%03u_alpha.pgm", s_dumpDir, s_dumpIndex);
        if (FILE *fp = std::fopen(path, "wb"))
        {
            std::fprintf(fp, "P5\n%u %u\n255\n", width, height);
            for (uint32_t i = 0; i < width * height; ++i)
            {
                const uint8_t a = static_cast<uint8_t>(pixels[i] >> 24);
                std::fwrite(&a, 1, 1, fp);
            }
            std::fclose(fp);
        }
        ++s_dumpIndex;
    }

    GLuint texture = 0u;
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_2D, texture);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, pixels.data());
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);

    TextureEntry entry;
    entry.texture = texture;
    entry.width = width;
    entry.height = height;
    entry.pageStart = pageStart;
    entry.pageCount = pageCount;
    entry.generation = m_generation;
    entry.lastUse = m_frameCounter;
    m_textures[key] = entry;
    return texture;
}

uint32_t GSGlBackend::resolveTexture(const GSDrawState &state, uint32_t &outWidth, uint32_t &outHeight)
{
    const GSTex0Reg &tex = state.context.tex0;
    const uint32_t width = std::min<uint32_t>(1024u, 1u << std::min<uint32_t>(tex.tw, 10u));
    const uint32_t height = std::min<uint32_t>(1024u, 1u << std::min<uint32_t>(tex.th, 10u));
    outWidth = width;
    outHeight = height;
    const uint32_t pageStart = tex.tbp0 >> 5;
    const uint32_t pageCount = pageSpan(tex.psm, tex.tbw, height);
    if (tracePagesHit(pageStart, pageCount))
        std::fprintf(stderr, "[gs-pages] frame=%llu texture tbp0=%05x tbw=%u psm=%02x %ux%u pages %03x+%u gpu-dirty=%d\n",
                     (unsigned long long)m_frameCounter, tex.tbp0, tex.tbw, tex.psm, width, height, pageStart, pageCount,
                     pagesMayBeGpuDirty(pageStart, pageCount) ? 1 : 0);

    // If the texture lives in pages a render target has drawn into, bring the shadow up to date.
    for (RenderTarget &rt : m_renderTargets)
    {
        if (!rt.shadowStale)
            continue;
        const uint32_t span = pageSpan(rt.psm, rt.fbw, std::min<uint32_t>(rt.usedHeight, 512u));
        if (pageStart + pageCount <= rt.fbp || pageStart >= rt.fbp + span)
            continue;
        downloadRenderTargetToShadow(rt);
        markShadowPages(rt.fbp, span);
    }

    TextureKey key;
    key.tbp0 = tex.tbp0;
    key.tbw = tex.tbw;
    key.psm = tex.psm;
    key.tw = width;
    key.th = height;
    key.cbp = tex.cbp;
    key.cpsm = tex.cpsm;
    key.csm = tex.csm;
    key.csa = tex.csa;
    key.texa = static_cast<uint32_t>(state.texa.ta0) | (static_cast<uint32_t>(state.texa.ta1) << 8) | (state.texa.aem ? 0x10000u : 0u);
    key.texclut = static_cast<uint32_t>(state.texclut.cbw) | (static_cast<uint32_t>(state.texclut.cou) << 8) | (static_cast<uint32_t>(state.texclut.cov) << 16);

    auto it = m_textures.find(key);
    if (it != m_textures.end())
    {
        uint64_t newest = 0u;
        for (uint32_t p = it->second.pageStart; p < it->second.pageStart + it->second.pageCount && p < 512u; ++p)
            newest = std::max(newest, m_shadowPageGeneration[p]);
        // CLUT pages too
        if (tex.psm == GS_PSM_T8 || tex.psm == GS_PSM_T8H || tex.psm == GS_PSM_T4 || tex.psm == GS_PSM_T4HL || tex.psm == GS_PSM_T4HH)
            newest = std::max(newest, m_shadowPageGeneration[std::min<uint32_t>(511u, tex.cbp >> 5)]);
        if (newest <= it->second.generation)
        {
            it->second.lastUse = m_frameCounter;
            return it->second.texture;
        }
        glDeleteTextures(1, &it->second.texture);
        m_textures.erase(it);
    }

    // Evict stale entries occasionally.
    if (m_textures.size() > 512u)
    {
        for (auto e = m_textures.begin(); e != m_textures.end();)
        {
            if (e->second.lastUse + 120u < m_frameCounter)
            {
                glDeleteTextures(1, &e->second.texture);
                e = m_textures.erase(e);
            }
            else
                ++e;
        }
    }
    return decodeTexture(state, key, width, height, pageStart, pageCount);
}

// ---------------------------------------------------------------------------------------------
// Drawing
// ---------------------------------------------------------------------------------------------
void GSGlBackend::appendVertex(const GSVertex &v, const GSDrawState &state, bool flatColorFromLast, const GSVertex &colorSource)
{
    const auto &ctx = state.context;
    GlVertex out{};
    out.x = v.x - static_cast<float>(ctx.xyoffset.ofx >> 4);
    out.y = v.y - static_cast<float>(ctx.xyoffset.ofy >> 4);
    out.z = static_cast<float>(std::min<double>(v.z, 4294967295.0) / 4294967296.0);
    if (state.prim.fst)
    {
        out.s = static_cast<float>(v.u) / 16.0f;
        out.t = static_cast<float>(v.v) / 16.0f;
        out.q = 1.0f;
    }
    else
    {
        out.s = v.s * static_cast<float>(state.textureWidth);
        out.t = v.t * static_cast<float>(state.textureHeight);
        // Q of 0 means "no perspective" for 2D STQ sprites (the UI's text glyphs never set Q);
        // treat it as 1.0 like the CPU rasterizer, not as a near-zero divisor.
        out.q = std::fabs(v.q) < 1e-8f ? 1.0f : std::fabs(v.q);
    }
    const GSVertex &c = flatColorFromLast ? colorSource : v;
    out.r = c.r;
    out.g = c.g;
    out.b = c.b;
    out.a = c.a;
    out.fog = static_cast<float>(v.fog) / 255.0f;
    m_vertices.push_back(out);
}

void GSGlBackend::executeSubmit(const GSPrimitiveBatch &batch)
{
    const GSDrawState &state = batch.state;
    DrawKey key{};
    key.context = state.context;
    key.prim = state.prim;
    key.texa = state.texa;
    key.texclut = state.texclut;
    key.pabe = state.pabe;
    key.linearFilter = state.linearFilter;
    key.textureWidth = state.textureWidth;
    key.textureHeight = state.textureHeight;
    key.fogR = state.fogR;
    key.fogG = state.fogG;
    key.fogB = state.fogB;
    if (m_hasBatch && std::memcmp(&key, &m_batchKey, sizeof(DrawKey)) != 0)
        flushBatch();
    if (!m_hasBatch)
    {
        m_hasBatch = true;
        m_batchKey = key;
        m_batchState = state;
        m_vertices.clear();
    }

    const GSVertex *v = batch.vertices.data();
    switch (state.prim.type)
    {
    case GS_PRIM_SPRITE:
    {
        if (batch.vertexCount < 2)
            return;
        GSVertex a = v[0], b = v[1];
        // Corners: (a.x,a.y) (b.x,a.y) (a.x,b.y) (b.x,b.y) with matching texcoords; colour = b.
        GSVertex tl = a, tr = a, bl = a, br = b;
        tr.x = b.x; tr.u = b.u; tr.s = b.s;
        bl.y = b.y; bl.v = b.v; bl.t = b.t;
        tl.z = tr.z = bl.z = b.z;
        tr.q = bl.q = b.q; tl.q = b.q;
        appendVertex(tl, state, true, b);
        appendVertex(tr, state, true, b);
        appendVertex(bl, state, true, b);
        appendVertex(tr, state, true, b);
        appendVertex(br, state, true, b);
        appendVertex(bl, state, true, b);
        break;
    }
    case GS_PRIM_TRIANGLE:
    case GS_PRIM_TRISTRIP:
    case GS_PRIM_TRIFAN:
    {
        if (batch.vertexCount < 3)
            return;
        const bool flat = !state.prim.iip;
        appendVertex(v[0], state, flat, v[2]);
        appendVertex(v[1], state, flat, v[2]);
        appendVertex(v[2], state, flat, v[2]);
        break;
    }
    case GS_PRIM_POINT:
    {
        GSVertex a = v[0], b = v[0];
        b.x += 1.0f;
        b.y += 1.0f;
        GSVertex tr = a, bl = a;
        tr.x = b.x;
        bl.y = b.y;
        appendVertex(a, state, false, a);
        appendVertex(tr, state, false, a);
        appendVertex(bl, state, false, a);
        appendVertex(tr, state, false, a);
        appendVertex(b, state, false, a);
        appendVertex(bl, state, false, a);
        break;
    }
    case GS_PRIM_LINE:
    case GS_PRIM_LINESTRIP:
    {
        if (batch.vertexCount < 2)
            return;
        // 1-pixel wide quad along the line.
        const GSVertex &a = v[0];
        const GSVertex &b = v[1];
        float dx = b.x - a.x, dy = b.y - a.y;
        const float len = std::sqrt(dx * dx + dy * dy);
        if (len < 1e-3f)
            return;
        const float nx = -dy / len * 0.5f, ny = dx / len * 0.5f;
        GSVertex a0 = a, a1 = a, b0 = b, b1 = b;
        a0.x += nx; a0.y += ny; a1.x -= nx; a1.y -= ny;
        b0.x += nx; b0.y += ny; b1.x -= nx; b1.y -= ny;
        const bool flat = !state.prim.iip;
        appendVertex(a0, state, flat, b);
        appendVertex(b0, state, flat, b);
        appendVertex(a1, state, flat, b);
        appendVertex(b0, state, flat, b);
        appendVertex(b1, state, flat, b);
        appendVertex(a1, state, flat, b);
        break;
    }
    default:
        break;
    }
}

void GSGlBackend::setupDrawState(const GSDrawState &state)
{
    const auto &ctx = state.context;
    RenderTarget *rt = getRenderTarget(ctx.frame.fbp, ctx.frame.fbw, ctx.frame.psm, true);
    m_batchRt = rt;
    refreshDirtyRows(*rt);
    glBindFramebuffer(GL_FRAMEBUFFER, rt->fbo);
    // Depth attachment keyed by ZBP.
    const bool zte = (ctx.test >> 16) & 1u;
    DepthTarget *dt = getDepthTarget(ctx.zbuf.zbp, rt->fbw, rt->width, rt->height);
    if (rt->attachedDepth != dt->texture)
    {
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_TEXTURE_2D, dt->texture, 0);
        rt->attachedDepth = dt->texture;
    }
    glViewport(0, 0, rt->width, rt->height);
    // The GS has no face culling. raylib's rlglInit enables GL_CULL_FACE for its own drawing
    // (and may re-enable it while drawing the debug UI), which silently dropped every sprite
    // whose second vertex lies above/left of the first — all of the UI's text glyphs.
    glDisable(GL_CULL_FACE);
    glEnable(GL_SCISSOR_TEST);
    glScissor(ctx.scissor.x0, ctx.scissor.y0,
              std::max<int>(0, ctx.scissor.x1 - ctx.scissor.x0 + 1),
              std::max<int>(0, ctx.scissor.y1 - ctx.scissor.y0 + 1));
    rt->usedHeight = std::max(rt->usedHeight, std::min<uint32_t>(kRtHeight, static_cast<uint32_t>(ctx.scissor.y1) + 1u));
    noteGpuRows(*rt, static_cast<uint32_t>(std::max<int>(0, ctx.scissor.y0)), std::min<uint32_t>(kRtHeight, static_cast<uint32_t>(ctx.scissor.y1) + 1u));
    rt->gpuDirty = true;
    rt->shadowStale = true;

    {
        char tag[64];
        std::snprintf(tag, sizeof(tag), " T%05llx/M%08x/tfx%u%s", (unsigned long long)(ctx.test & 0x7FFFFu), ctx.frame.fbmsk,
                      ctx.tex0.tfx & 3u, state.prim.tme ? "t" : "");
        if (m_stateLog.find(tag) == std::string::npos && m_stateLog.size() < 600u)
            m_stateLog += tag;
    }
    // Depth test.
    uint32_t ztst = (ctx.test >> 17) & 3u;
    if (!zte)
        ztst = 1u;
    // PS2X_GS_NO_ZTEST=1: A/B switch — every draw passes the depth test.
    static const bool s_noZtest = std::getenv("PS2X_GS_NO_ZTEST") != nullptr;
    if (s_noZtest)
        ztst = 1u;
    glEnable(GL_DEPTH_TEST);
    switch (ztst)
    {
    case 0: glDepthFunc(GL_NEVER); break;
    case 1: glDepthFunc(GL_ALWAYS); break;
    case 2: glDepthFunc(GL_GEQUAL); break;
    default: glDepthFunc(GL_GREATER); break;
    }
    glDepthMask(ctx.zbuf.zmask ? GL_FALSE : GL_TRUE);

    // Colour mask from FBMSK (per-channel when whole bytes).
    const uint32_t mask = ctx.frame.fbmsk;
    glColorMask((mask & 0x000000FFu) != 0x000000FFu, (mask & 0x0000FF00u) != 0x0000FF00u,
                (mask & 0x00FF0000u) != 0x00FF0000u, (mask & 0xFF000000u) != 0xFF000000u);

    // Alpha blending: out = (A - B) * C + D
    if (state.prim.abe)
    {
        const uint64_t alpha = ctx.alpha;
        const uint32_t asel = alpha & 3u, bsel = (alpha >> 2) & 3u, csel = (alpha >> 4) & 3u, dsel = (alpha >> 6) & 3u;
        {
            char tag[48];
            std::snprintf(tag, sizeof(tag), " A%uB%uC%uD%u/fix%02llx", asel, bsel, csel, dsel, (unsigned long long)((alpha >> 32) & 0xFFu));
            if (m_blendLog.find(tag) == std::string::npos && m_blendLog.size() < 400u)
                m_blendLog += tag;
        }
        const float fix = std::min(1.0f, static_cast<float>((alpha >> 32) & 0xFFu) / 128.0f);
        GLenum cFactor = GL_SRC1_ALPHA, cInv = GL_ONE_MINUS_SRC1_ALPHA;
        if (csel == 1u) { cFactor = GL_DST_ALPHA; cInv = GL_ONE_MINUS_DST_ALPHA; }
        else if (csel >= 2u) { cFactor = GL_CONSTANT_COLOR; cInv = GL_ONE_MINUS_CONSTANT_COLOR; glBlendColor(fix, fix, fix, fix); }
        GLenum eq = GL_FUNC_ADD, src = GL_ONE, dst = GL_ZERO;
        const uint32_t a = asel >= 2u ? 2u : asel, b = bsel >= 2u ? 2u : bsel, d = dsel >= 2u ? 2u : dsel;
        if (a == b)
        {
            src = (d == 0u) ? GL_ONE : GL_ZERO;
            dst = (d == 1u) ? GL_ONE : GL_ZERO;
        }
        else if (a == 0u && b == 1u)      // (Cs - Cd) * C + D
        {
            if (d == 1u) { src = cFactor; dst = cInv; }
            else if (d == 0u) { eq = GL_FUNC_SUBTRACT; src = GL_ONE; dst = cFactor; }   // approx (1+C)Cs - C Cd
            else { eq = GL_FUNC_SUBTRACT; src = cFactor; dst = cFactor; }
        }
        else if (a == 0u && b == 2u)      // Cs * C + D
        {
            src = cFactor;
            dst = (d == 1u) ? GL_ONE : GL_ZERO;
            if (d == 0u) src = GL_ONE;    // approx Cs(1+C)
        }
        else if (a == 1u && b == 0u)      // (Cd - Cs) * C + D
        {
            if (d == 0u) { src = cInv; dst = cFactor; }
            else if (d == 1u) { eq = GL_FUNC_REVERSE_SUBTRACT; src = cFactor; dst = GL_ONE; }
            else { eq = GL_FUNC_REVERSE_SUBTRACT; src = cFactor; dst = cFactor; }
        }
        else if (a == 1u && b == 2u)      // Cd * C + D
        {
            if (d == 0u) { src = GL_ONE; dst = cFactor; }
            else if (d == 1u) { src = GL_ZERO; dst = GL_ONE; }
            else { src = GL_ZERO; dst = cFactor; }
        }
        else if (a == 2u && b == 0u)      // -Cs * C + D
        {
            if (d == 1u) { eq = GL_FUNC_REVERSE_SUBTRACT; src = cFactor; dst = GL_ONE; }
            else if (d == 0u) { src = cInv; dst = GL_ZERO; }
            else { src = GL_ZERO; dst = GL_ZERO; }
        }
        else                              // a == 2, b == 1: -Cd * C + D
        {
            if (d == 0u) { eq = GL_FUNC_SUBTRACT; src = GL_ONE; dst = cFactor; }
            else if (d == 1u) { src = GL_ZERO; dst = cInv; }
            else { src = GL_ZERO; dst = GL_ZERO; }
        }
        glEnable(GL_BLEND);
        glBlendEquationSeparate(eq, GL_FUNC_ADD);
        glBlendFuncSeparate(src, dst, GL_ONE, GL_ZERO);
    }
    else
    {
        glDisable(GL_BLEND);
    }

    glUseProgram(m_program);
    glUniform2f(m_u.rtSize, static_cast<float>(rt->width), static_cast<float>(rt->height));
    glUniform1i(m_u.tme, state.prim.tme ? 1 : 0);
    glUniform1i(m_u.fge, state.prim.fge ? 1 : 0);
    glUniform3f(m_u.fogColor, state.fogR / 255.0f, state.fogG / 255.0f, state.fogB / 255.0f);
    glUniform1i(m_u.fba, (ctx.fba & 1ull) != 0ull ? 1 : 0);
    const uint32_t test = static_cast<uint32_t>(ctx.test);
    glUniform1i(m_u.ate, test & 1u);
    glUniform1i(m_u.atst, (test >> 1) & 7u);
    glUniform1f(m_u.aref, static_cast<float>((test >> 4) & 0xFFu));
    glUniform1i(m_u.afail, (test >> 12) & 3u);

    if (state.prim.tme)
    {
        uint32_t tw = 1u, th = 1u;
        const uint32_t texture = resolveTexture(state, tw, th);
        glActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, texture);
        const GLint filter = state.linearFilter ? GL_LINEAR : GL_NEAREST;
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, filter);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, filter);
        glUniform1i(m_u.tex, 0);
        glUniform2f(m_u.texSize, static_cast<float>(tw), static_cast<float>(th));
        glUniform1i(m_u.tfx, ctx.tex0.tfx & 3u);
        glUniform1i(m_u.tcc, ctx.tex0.tcc & 1u);
        glUniform1i(m_u.fst, state.prim.fst ? 1 : 0);
        const uint64_t clamp = ctx.clamp;
        glUniform1i(m_u.wrapU, static_cast<int>(clamp & 3u));
        glUniform1i(m_u.wrapV, static_cast<int>((clamp >> 2) & 3u));
        glUniform4f(m_u.region, static_cast<float>((clamp >> 4) & 0x3FFu), static_cast<float>((clamp >> 14) & 0x3FFu),
                    static_cast<float>((clamp >> 24) & 0x3FFu), static_cast<float>((clamp >> 34) & 0x3FFu));
    }
}

void GSGlBackend::flushBatch()
{
    if (!m_hasBatch)
        return;
    m_hasBatch = false;
    if (m_vertices.empty())
        return;
    setupDrawState(m_batchState);
    // PS2X_GS_GL_DEBUG_PSM=<psm>: print the first batches drawn with that texture format (state,
    // bound texture, blend and the vertices actually submitted), to compare with the CPU path.
    static const int s_debugPsm = std::getenv("PS2X_GS_GL_DEBUG_PSM") ? std::atoi(std::getenv("PS2X_GS_GL_DEBUG_PSM")) : -1;
    static int s_debugCount = 0;
    // PS2X_GS_GL_DEBUG_AFTER=<presents>: only debug draws issued after that many presents.
    static const unsigned long long s_debugAfter = std::getenv("PS2X_GS_GL_DEBUG_AFTER") ? std::strtoull(std::getenv("PS2X_GS_GL_DEBUG_AFTER"), nullptr, 0) : 0ull;
    const bool debugWindow = m_frameCounter >= s_debugAfter;
    if (debugWindow && s_debugPsm >= 0 && m_batchState.prim.tme && static_cast<int>(m_batchState.context.tex0.psm) == s_debugPsm && s_debugCount++ < 12)
    {
        GLint tex = 0, prog = 0, blend = 0, srcRgb = 0, dstRgb = 0, eqRgb = 0, depthFn = 0, depthMask = 0;
        GLint scissor[4] = {0, 0, 0, 0};
        GLboolean colorMask[4] = {0, 0, 0, 0};
        glGetIntegerv(GL_TEXTURE_BINDING_2D, &tex);
        glGetIntegerv(GL_CURRENT_PROGRAM, &prog);
        glGetIntegerv(GL_BLEND, &blend);
        glGetIntegerv(GL_BLEND_SRC_RGB, &srcRgb);
        glGetIntegerv(GL_BLEND_DST_RGB, &dstRgb);
        glGetIntegerv(GL_BLEND_EQUATION_RGB, &eqRgb);
        glGetIntegerv(GL_DEPTH_FUNC, &depthFn);
        glGetIntegerv(GL_DEPTH_WRITEMASK, &depthMask);
        glGetIntegerv(GL_SCISSOR_BOX, scissor);
        glGetBooleanv(GL_COLOR_WRITEMASK, colorMask);
        const auto &c = m_batchState.context;
        std::fprintf(stderr, "[gs-gl dbg] psm=%02x tex=%d prog=%d blend=%d src=%#x dst=%#x eq=%#x depth=%#x zmask=%d scissor=%d,%d %dx%d cmask=%d%d%d%d tw=%u th=%u clamp=%#llx alpha=%#llx tfx=%u tcc=%u fst=%u verts=%zu\n",
                     c.tex0.psm, tex, prog, blend, srcRgb, dstRgb, eqRgb, depthFn, depthMask, scissor[0], scissor[1], scissor[2], scissor[3],
                     colorMask[0], colorMask[1], colorMask[2], colorMask[3], m_batchState.textureWidth, m_batchState.textureHeight,
                     (unsigned long long)c.clamp, (unsigned long long)c.alpha, c.tex0.tfx & 3u, c.tex0.tcc & 1u, m_batchState.prim.fst ? 1u : 0u, m_vertices.size());
        for (size_t i = 0; i < std::min<size_t>(6, m_vertices.size()); ++i)
        {
            const GlVertex &v = m_vertices[i];
            std::fprintf(stderr, "[gs-gl dbg]   v%zu pos=(%.1f,%.1f,%.6f) st=(%.2f,%.2f) q=%.3f rgba=%u,%u,%u,%u\n", i, v.x, v.y, v.z, v.s, v.t, v.q, v.r, v.g, v.b, v.a);
        }
    }
    const bool debugThis = debugWindow && s_debugPsm >= 0 && m_batchState.prim.tme && static_cast<int>(m_batchState.context.tex0.psm) == s_debugPsm && s_debugCount <= 12;
    float dbgCx = 0.0f, dbgCy = 0.0f;
    if (debugThis && m_vertices.size() >= 6)
    {
        dbgCx = (m_vertices[0].x + m_vertices[4].x) * 0.5f;
        dbgCy = (m_vertices[0].y + m_vertices[4].y) * 0.5f;
        uint8_t before[4] = {0, 0, 0, 0};
        glReadPixels(static_cast<int>(dbgCx), static_cast<int>(dbgCy), 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, before);
        std::memcpy(m_dbgBefore, before, 4);
        float storedDepth = -2.0f;
        glReadPixels(static_cast<int>(dbgCx), static_cast<int>(dbgCy), 1, 1, GL_DEPTH_COMPONENT, GL_FLOAT, &storedDepth);
        std::fprintf(stderr, "[gs-gl dbg]   pixel(%d,%d) before=%u,%u,%u,%u storedDepth=%.7f vertexDepth(ndc->[0,1])=%.7f\n", static_cast<int>(dbgCx), static_cast<int>(dbgCy),
                     before[0], before[1], before[2], before[3], storedDepth, m_vertices[0].z);
        // Two more probes above the quad (letterbox band) to tell a failed clear from a stray draw.
        uint8_t pa[4] = {0, 0, 0, 0}, pb[4] = {0, 0, 0, 0};
        glReadPixels(100, 50, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, pa);
        glReadPixels(500, 50, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, pb);
        std::fprintf(stderr, "[gs-gl dbg]   band before: (100,50)=%u,%u,%u,%u (500,50)=%u,%u,%u,%u target fbp=%03x fbo=%u tex tbp0=%05x tbw=%u\n",
                     pa[0], pa[1], pa[2], pa[3], pb[0], pb[1], pb[2], pb[3],
                     m_batchRt ? m_batchRt->fbp : 0u, m_batchRt ? m_batchRt->fbo : 0u, m_batchState.context.tex0.tbp0, m_batchState.context.tex0.tbw);
        static const bool s_noDepth = std::getenv("PS2X_GS_GL_DEBUG_NODEPTH") != nullptr;
        if (s_noDepth)
            glDisable(GL_DEPTH_TEST);
        // What does the bound texture hold at the sampled texel?
        GLint tw = 0, th = 0;
        glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_WIDTH, &tw);
        glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_HEIGHT, &th);
        if (tw > 0 && th > 0)
        {
            std::vector<uint8_t> img(static_cast<size_t>(tw) * th * 4);
            glGetTexImage(GL_TEXTURE_2D, 0, GL_RGBA, GL_UNSIGNED_BYTE, img.data());
            const int sx = std::clamp(static_cast<int>((m_vertices[0].s + m_vertices[4].s) * 0.5f), 0, tw - 1);
            const int sy = std::clamp(static_cast<int>((m_vertices[0].t + m_vertices[4].t) * 0.5f), 0, th - 1);
            size_t opaque = 0;
            for (size_t i = 3; i < img.size(); i += 4)
                opaque += img[i] > 0 ? 1 : 0;
            const uint8_t *px = &img[(static_cast<size_t>(sy) * tw + sx) * 4];
            std::fprintf(stderr, "[gs-gl dbg]   bound tex %dx%d texel(%d,%d)=%u,%u,%u,%u nonzero-alpha texels=%zu\n", tw, th, sx, sy, px[0], px[1], px[2], px[3], opaque);
        }
    }
    if (m_batchRt)
        glBindFramebuffer(GL_FRAMEBUFFER, m_batchRt->fbo);   // the texture path may have rebound another target
    glBindVertexArray(m_vao);
    glBindBuffer(GL_ARRAY_BUFFER, m_vbo);
    glBufferData(GL_ARRAY_BUFFER, static_cast<GLsizeiptr>(m_vertices.size() * sizeof(GlVertex)), m_vertices.data(), GL_STREAM_DRAW);
    glDrawArrays(GL_TRIANGLES, 0, static_cast<GLsizei>(m_vertices.size()));
    {
        // PS2X_GS_PROBE=<frame>: for 400 frames from there, after every untextured sprite batch
        // into fbp 0x8c, read back rows 200 and 420 at x=320 (GL RT rows) to see whether the
        // draw reached the bottom band (the movie strip investigation, 2026-09-09).
        static const long s_probeFrom = std::getenv("PS2X_GS_PROBE") ? std::strtol(std::getenv("PS2X_GS_PROBE"), nullptr, 0) : -1L;
        if (s_probeFrom >= 0 && static_cast<long>(m_frameCounter) >= s_probeFrom && static_cast<long>(m_frameCounter) < s_probeFrom + 400 &&
            m_batchRt && m_batchRt->fbp == 0x8cu && !m_batchState.prim.tme && m_batchState.prim.type == GS_PRIM_SPRITE && m_vertices.size() >= 6)
        {
            uint8_t p200[4] = {0, 0, 0, 0}, p420[4] = {0, 0, 0, 0}, p440[4] = {0, 0, 0, 0};
            glReadPixels(320, 200, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, p200);
            glReadPixels(320, 420, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, p420);
            glReadPixels(320, 440, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, p440);
            float ymin = m_vertices[0].y, ymax = m_vertices[0].y;
            for (const auto &vv : m_vertices) { ymin = std::min(ymin, vv.y); ymax = std::max(ymax, vv.y); }
            std::fprintf(stderr, "[gs-gl probe] frame=%llu fbp=%03x fbo=%u sprite y=[%.0f..%.0f] rgba=%02x%02x%02x%02x -> row200=%02x%02x%02x row420=%02x%02x%02x row440=%02x%02x%02x glerr=%x\n",
                         (unsigned long long)m_frameCounter, m_batchRt->fbp, m_batchRt->fbo, ymin, ymax,
                         m_vertices[0].r, m_vertices[0].g, m_vertices[0].b, m_vertices[0].a,
                         p200[0], p200[1], p200[2], p420[0], p420[1], p420[2], p440[0], p440[1], p440[2], glGetError());
        }
    }
    if (debugThis && m_vertices.size() >= 6)
    {
        // Read back the whole quad region and count pixels the draw changed.
        const int x0 = static_cast<int>(std::min(m_vertices[0].x, m_vertices[4].x)), x1 = static_cast<int>(std::max(m_vertices[0].x, m_vertices[4].x));
        const int y0 = static_cast<int>(std::min(m_vertices[0].y, m_vertices[4].y)), y1 = static_cast<int>(std::max(m_vertices[0].y, m_vertices[4].y));
        const int w = std::max(1, x1 - x0), h = std::max(1, y1 - y0);
        std::vector<uint8_t> after(static_cast<size_t>(w) * h * 4);
        glReadPixels(x0, y0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, after.data());
        size_t changed = 0;
        uint8_t brightest[4] = {0, 0, 0, 0};
        for (size_t i = 0; i < after.size(); i += 4)
        {
            if (after[i] != m_dbgBefore[0] || after[i + 1] != m_dbgBefore[1] || after[i + 2] != m_dbgBefore[2])
            {
                ++changed;
                if (after[i] > brightest[0])
                    std::memcpy(brightest, &after[i], 4);
            }
        }
        GLint fbo = 0;
        glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &fbo);
        std::fprintf(stderr, "[gs-gl dbg]   quad %dx%d at (%d,%d): %zu of %d pixels changed, brightest=%u,%u,%u,%u fbo=%d glerr=%#x\n",
                     w, h, x0, y0, changed, w * h, brightest[0], brightest[1], brightest[2], brightest[3], fbo, glGetError());
    }
    m_vertices.clear();
}
