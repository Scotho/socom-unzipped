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
    constexpr uint32_t kMaxRtWidth = 2048u;
    constexpr uint32_t kRtHeight = 1024u;
    constexpr uint32_t kHostFrameWidth = 640u;
    constexpr uint32_t kHostFrameHeight = 512u;

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
        const uint32_t clutBase = (static_cast<uint32_t>(csa) & csaMask) << 4u;
        switch (sourcePsm)
        {
        case GS_PSM_T4:
        case GS_PSM_T4HH:
        case GS_PSM_T4HL:
            return clutBase + (clutIndex & 0x0Fu);
        case GS_PSM_T8:
        case GS_PSM_T8H:
            return clutBase + clutIndex;
        default:
            return clutIndex;
        }
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
        CommandBuffer buffer;
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
    CommandBuffer buffer;
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

uint32_t GSGlBackend::HostFrameTexture(uint32_t &width, uint32_t &height)
{
    width = m_presentWidth;
    height = m_presentHeight;
    return m_presentTexture;
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
    for (Cmd &cmd : buffer.commands)
    {
        const auto t0 = std::chrono::steady_clock::now();
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
    for (RenderTarget &rt : m_renderTargets)
        if (rt.fbp == fbp && rt.fbw == fbw)
            return &rt;
    if (!create)
        return nullptr;
    RenderTarget rt;
    rt.fbp = fbp;
    rt.fbw = std::max<uint32_t>(fbw, 1u);
    rt.psm = psm;
    rt.width = std::min<uint32_t>(kMaxRtWidth, rt.fbw * 64u);
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
    GSTransferCommand whole{};
    whole.bitbltbuf.dbp = fbp << 5;
    whole.bitbltbuf.dbw = static_cast<uint8_t>(rt.fbw);
    whole.bitbltbuf.dpsm = static_cast<uint8_t>(psm);
    whole.trxreg.rrw = static_cast<uint16_t>(rt.width);
    whole.trxreg.rrh = 448u;
    refreshRenderTargetsFromShadow(fbp, pageSpan(psm, rt.fbw, 448u), whole);
    return &ref;
}

GSGlBackend::DepthTarget *GSGlBackend::getDepthTarget(uint32_t zbp, uint32_t fbw, uint32_t width, uint32_t height)
{
    for (DepthTarget &dt : m_depthTargets)
        if (dt.zbp == zbp && dt.fbw == fbw)
            return &dt;
    DepthTarget dt;
    dt.zbp = zbp;
    dt.fbw = fbw;
    dt.width = width;
    dt.height = height;
    glGenTextures(1, &dt.texture);
    glBindTexture(GL_TEXTURE_2D, dt.texture);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT32F, width, height, 0, GL_DEPTH_COMPONENT, GL_FLOAT, nullptr);
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
        refreshRenderTargetsFromShadow(page, span, command);
    }
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
    // Uploads arrive in chunks; refresh overlapping render targets once per completed rectangle.
    m_uploadReceivedBytes += size;
    if (m_uploadExpectedBytes != 0u && m_uploadReceivedBytes >= m_uploadExpectedBytes)
    {
        m_uploadReceivedBytes = 0u;
        refreshRenderTargetsFromShadow(page, span, t);
    }
}

// A transfer wrote into pages that a render target covers: re-decode that rectangle from the
// shadow VRAM into the RT texture (video frames are uploaded straight into the display buffer).
void GSGlBackend::refreshRenderTargetsFromShadow(uint32_t page, uint32_t pageCount, const GSTransferCommand &transfer)
{
    for (RenderTarget &rt : m_renderTargets)
    {
        const uint32_t rtSpan = pageSpan(rt.psm, rt.fbw, rt.usedHeight);
        if (page + pageCount <= rt.fbp || page >= rt.fbp + rtSpan)
            continue;
        if (transfer.bitbltbuf.dbp != (rt.fbp << 5) || transfer.bitbltbuf.dpsm != rt.psm)
        {
            // Different base/format aliasing the same memory: re-read the affected rows in the RT's own layout.
        }
        const uint32_t x0 = std::min<uint32_t>(transfer.trxpos.dsax, rt.width);
        const uint32_t y0 = std::min<uint32_t>(transfer.trxpos.dsay, rt.height);
        const uint32_t w = std::min<uint32_t>(transfer.trxreg.rrw, rt.width - x0);
        const uint32_t h = std::min<uint32_t>(transfer.trxreg.rrh, rt.height - y0);
        if (w == 0u || h == 0u)
            continue;
        std::vector<uint32_t> pixels(static_cast<size_t>(w) * h);
        const uint32_t base = rt.fbp << 5;
        for (uint32_t y = 0; y < h; ++y)
            for (uint32_t x = 0; x < w; ++x)
            {
                uint32_t p = readVramRaw(m_shadowMemory.data(), rt.psm, base, rt.fbw, x0 + x, y0 + y);
                if (rt.psm == GS_PSM_CT16 || rt.psm == GS_PSM_CT16S)
                    p = rgba5551To8888(p);
                else if (rt.psm == GS_PSM_CT24)
                    p |= 0x80000000u;
                pixels[static_cast<size_t>(y) * w + x] = p;
            }
        glBindTexture(GL_TEXTURE_2D, rt.color);
        glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
        glTexSubImage2D(GL_TEXTURE_2D, 0, static_cast<GLint>(x0), static_cast<GLint>(y0), static_cast<GLsizei>(w), static_cast<GLsizei>(h), GL_RGBA, GL_UNSIGNED_BYTE, pixels.data());
        rt.usedHeight = std::max(rt.usedHeight, std::min<uint32_t>(kRtHeight, y0 + h));
    }
}

void GSGlBackend::executeClear(const GSContext &context, uint32_t rgba)
{
    RenderTarget *rt = getRenderTarget(context.frame.fbp, context.frame.fbw, context.frame.psm, true);
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
}

// Download a render target (GPU) into the shadow VRAM so texture decoding sees the drawn pixels.
void GSGlBackend::downloadRenderTargetToShadow(RenderTarget &rt)
{
    const uint32_t h = std::min<uint32_t>(rt.usedHeight, rt.height);
    std::vector<uint32_t> pixels(static_cast<size_t>(rt.width) * h);
    glBindFramebuffer(GL_FRAMEBUFFER, rt.fbo);
    glPixelStorei(GL_PACK_ALIGNMENT, 4);
    glReadPixels(0, 0, rt.width, h, GL_RGBA, GL_UNSIGNED_BYTE, pixels.data());
    const uint32_t base = rt.fbp << 5;
    for (uint32_t y = 0; y < h; ++y)
        for (uint32_t x = 0; x < rt.width; ++x)
        {
            uint32_t p = pixels[static_cast<size_t>(y) * rt.width + x];
            if (rt.psm == GS_PSM_CT16 || rt.psm == GS_PSM_CT16S)
                p = rgba8888To5551(p);
            writeVramRaw(m_shadowMemory.data(), rt.psm, base, rt.fbw, x, y, p);
        }
    rt.shadowStale = false;
}

// Download into the game thread's authoritative VRAM (guest reads GS memory).
void GSGlBackend::downloadRenderTargetToCpu(RenderTarget &rt)
{
    const uint32_t h = std::min<uint32_t>(rt.usedHeight, rt.height);
    std::vector<uint32_t> pixels(static_cast<size_t>(rt.width) * h);
    glBindFramebuffer(GL_FRAMEBUFFER, rt.fbo);
    glPixelStorei(GL_PACK_ALIGNMENT, 4);
    glReadPixels(0, 0, rt.width, h, GL_RGBA, GL_UNSIGNED_BYTE, pixels.data());
    const uint32_t base = rt.fbp << 5;
    for (uint32_t y = 0; y < h; ++y)
        for (uint32_t x = 0; x < rt.width; ++x)
        {
            uint32_t p = pixels[static_cast<size_t>(y) * rt.width + x];
            if (rt.psm == GS_PSM_CT16 || rt.psm == GS_PSM_CT16S)
                p = rgba8888To5551(p);
            m_cpu->WriteVram(rt.psm, base, rt.fbw, x, y, p);
            writeVramRaw(m_shadowMemory.data(), rt.psm, base, rt.fbw, x, y, p);
        }
    rt.gpuDirty = false;
    rt.shadowStale = false;
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
        m_presentTexture = 0u;
        return;
    }

    RenderTarget *rt = getRenderTarget(display.fbp, display.fbw, display.psm, false);
    if (!rt)
    {
        // The display base may sit inside a larger target (or an upload-only buffer).
        for (RenderTarget &candidate : m_renderTargets)
        {
            const uint32_t span = pageSpan(candidate.psm, candidate.fbw, candidate.usedHeight);
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
    m_presentTexture = rt->color;
    m_presentWidth = std::min<uint32_t>(width, rt->width);
    m_presentHeight = std::min<uint32_t>(height, rt->height);
    m_presentFbp = display.fbp;
    ++m_frameCounter;

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
    uint8_t *vram = m_shadowMemory.data();
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
    }

    for (uint32_t y = 0; y < height; ++y)
        for (uint32_t x = 0; x < width; ++x)
        {
            uint32_t out = readVramRaw(vram, tex.psm, tex.tbp0, tex.tbw, x, y);
            switch (tex.psm)
            {
            case GS_PSM_CT32:
            case GS_PSM_CT24:
            case GS_PSM_Z32:
            case GS_PSM_Z24:
                out = applyTexa(state.texa, tex.psm, out);
                break;
            case GS_PSM_CT16:
            case GS_PSM_CT16S:
            case GS_PSM_Z16:
            case GS_PSM_Z16S:
                out = applyTexa(state.texa, tex.psm, rgba5551To8888(out));
                break;
            default:
                out = indexed ? clut[out & 0xFFu] : 0xFFFF00FFu;
                break;
            }
            pixels[static_cast<size_t>(y) * width + x] = out;
        }

    // PS2X_GS_DUMP_TEX=<dir>: write every decoded texture as a PPM (RGB) + PGM (alpha) for inspection.
    static const char *s_dumpDir = std::getenv("PS2X_GS_DUMP_TEX");
    if (s_dumpDir)
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

    // If the texture lives in pages a render target has drawn into, bring the shadow up to date.
    for (RenderTarget &rt : m_renderTargets)
    {
        if (!rt.shadowStale)
            continue;
        const uint32_t span = pageSpan(rt.psm, rt.fbw, rt.usedHeight);
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
        out.q = std::fabs(v.q) < 1e-9f ? 1e-9f : std::fabs(v.q);
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
    glEnable(GL_SCISSOR_TEST);
    glScissor(ctx.scissor.x0, ctx.scissor.y0,
              std::max<int>(0, ctx.scissor.x1 - ctx.scissor.x0 + 1),
              std::max<int>(0, ctx.scissor.y1 - ctx.scissor.y0 + 1));
    rt->usedHeight = std::max(rt->usedHeight, std::min<uint32_t>(kRtHeight, static_cast<uint32_t>(ctx.scissor.y1) + 1u));
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
    glBindVertexArray(m_vao);
    glBindBuffer(GL_ARRAY_BUFFER, m_vbo);
    glBufferData(GL_ARRAY_BUFFER, static_cast<GLsizeiptr>(m_vertices.size() * sizeof(GlVertex)), m_vertices.data(), GL_STREAM_DRAW);
    glDrawArrays(GL_TRIANGLES, 0, static_cast<GLsizei>(m_vertices.size()));
    m_vertices.clear();
}
