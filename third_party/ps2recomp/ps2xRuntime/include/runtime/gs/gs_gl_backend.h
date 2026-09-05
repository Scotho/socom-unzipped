#pragma once

#include "runtime/gs/gs_backend.h"
#include "runtime/gs/gs_cpu_backend.h"

#include <array>
#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

// OpenGL 3.3 GS backend (design: docs/superpowers/plans/2026-09-05-gpu-gs-backend.md).
//
// The game thread records a command stream (draws, transfers, presents); the main thread — which
// owns raylib's GL context — replays it before each host frame. Two GSCpuBackend instances model
// VRAM: `m_cpu` (authoritative, game thread: uploads applied immediately, reads served from it)
// and `m_shadow` (render thread, fed by the replayed transfers; source for texture decoding).
// Drawing goes to per-framebuffer render targets; pages an RT has drawn into are "GPU-dirty" and
// are downloaded into the CPU VRAM only when the guest reads them.
class GSGlBackend final : public GSRasterBackend
{
public:
    GSGlBackend();
    ~GSGlBackend() override;

    void Initialize(uint8_t *vram, uint32_t vramSize) override;
    void Reset() override;

    void Submit(const GSPrimitiveBatch &batch) override;
    void BeginTransfer(const GSTransferCommand &command) override;
    void UploadImage(const uint8_t *data, uint32_t sizeBytes) override;

    void Flush() override;
    void TextureFlush() override;
    void Sync(GSSyncReason reason) override;
    PresentationFrame Present(const GSPresentationRequest &request) override;

    bool ClearFramebuffer(const GSContext &context, uint32_t rgba) override;
    uint32_t ConsumeLocalToHostBytes(uint8_t *dst, uint32_t maxBytes) override;

    uint32_t ReadVram(uint32_t psm, uint32_t base, uint32_t bw, uint32_t x, uint32_t y) const override;
    void WriteVram(uint32_t psm, uint32_t base, uint32_t bw, uint32_t x, uint32_t y, uint32_t value) override;
    void SnapshotVram(std::vector<uint8_t> &out) const override;
    GSTransferSnapshot GetTransferSnapshot() const override;

    // Main thread: replay recorded commands. Returns true when a presentable texture exists.
    bool HostDriven() const override { return true; }
    bool HostRenderFrame() override;
    uint32_t HostFrameTexture(uint32_t &width, uint32_t &height, uint32_t &textureWidth, uint32_t &textureHeight) override;

private:
    enum class CmdType : uint8_t
    {
        Submit,
        BeginTransfer,
        Upload,
        WriteVram,
        Clear,
        Present,
        Readback,
        Reset,
    };

    struct Cmd
    {
        CmdType type = CmdType::Submit;
        GSPrimitiveBatch batch{};
        GSTransferCommand transfer{};
        GSPresentationRequest present{};
        GSContext context{};
        uint32_t args[5] = {0, 0, 0, 0, 0};
        size_t dataOffset = 0;
        size_t dataSize = 0;
        uint64_t token = 0;
    };

    struct CommandBuffer
    {
        std::vector<Cmd> commands;
        std::vector<uint8_t> data;
        void clear()
        {
            commands.clear();
            data.clear();
        }
    };

    struct RenderTarget
    {
        uint32_t fbp = 0;   // pages
        uint32_t fbw = 0;   // 64-pixel units
        uint32_t psm = 0;
        uint32_t width = 0;
        uint32_t height = 0;
        uint32_t usedHeight = 32;
        uint32_t fbo = 0;
        uint32_t color = 0;
        uint32_t attachedDepth = 0;
        bool gpuDirty = false;
        bool shadowStale = false;   // shadow VRAM does not hold the GPU contents
        bool dirtyRows = false;     // rows [dirtyRowFirst, dirtyRowLast) must be re-read from the shadow
        uint32_t dirtyRowFirst = 0;
        uint32_t dirtyRowLast = 0;
    };

    struct DepthTarget
    {
        uint32_t zbp = 0;
        uint32_t fbw = 0;
        uint32_t texture = 0;
        uint32_t width = 0;
        uint32_t height = 0;
    };

    struct TextureKey
    {
        uint32_t tbp0 = 0, tbw = 0, psm = 0, tw = 0, th = 0;
        uint32_t cbp = 0, cpsm = 0, csm = 0, csa = 0;
        uint32_t texa = 0, texclut = 0;
        bool operator==(const TextureKey &o) const
        {
            return tbp0 == o.tbp0 && tbw == o.tbw && psm == o.psm && tw == o.tw && th == o.th && cbp == o.cbp &&
                   cpsm == o.cpsm && csm == o.csm && csa == o.csa && texa == o.texa && texclut == o.texclut;
        }
    };
    struct TextureKeyHash
    {
        size_t operator()(const TextureKey &k) const
        {
            size_t h = k.tbp0 * 0x9E3779B1u;
            h ^= (k.tbw + k.psm * 64u + k.tw * 4096u + k.th * 65536u) * 0x85EBCA6Bu;
            h ^= (k.cbp + k.cpsm * 16384u + k.csa * 262144u + k.csm * 524288u) * 0xC2B2AE35u;
            h ^= k.texa * 0x27D4EB2Fu ^ k.texclut * 0x165667B1u;
            return h;
        }
    };

    struct TextureEntry
    {
        uint32_t texture = 0;
        uint32_t width = 0;
        uint32_t height = 0;
        uint32_t pageStart = 0;
        uint32_t pageCount = 0;
        uint64_t generation = 0;
        uint64_t lastUse = 0;
    };

    struct DrawKey
    {
        GSContext context{};
        GSPrimReg prim{};
        GSTexaReg texa{};
        GSTexClutReg texclut{};
        bool pabe = false;
        bool linearFilter = false;
        uint16_t textureWidth = 0, textureHeight = 0;
        uint8_t fogR = 0, fogG = 0, fogB = 0;
    };

    struct GlVertex
    {
        float x, y, z;
        float s, t, q;
        uint8_t r, g, b, a;
        float fog;
    };

    // game-thread side
    void record(Cmd &&cmd, const uint8_t *data = nullptr, size_t size = 0);
    uint64_t postAndGetToken(Cmd &&cmd, const uint8_t *data = nullptr, size_t size = 0);
    void waitForToken(uint64_t token);
    void syncDirtyPagesForRead(uint32_t page, uint32_t pageCount) const;
    bool pagesMayBeGpuDirty(uint32_t page, uint32_t pageCount) const;
    void markRtDirtyFromFrame(const GSContext &context);

    // render-thread side
    void executeCommands(CommandBuffer &buffer);
    void executeSubmit(const GSPrimitiveBatch &batch);
    void executeTransfer(const GSTransferCommand &command);
    void executeUpload(const uint8_t *data, size_t size);
    void executeClear(const GSContext &context, uint32_t rgba);
    void executePresent(const GSPresentationRequest &request);
    void executeReadback();
    void flushBatch();
    bool ensureGl();
    RenderTarget *getRenderTarget(uint32_t fbp, uint32_t fbw, uint32_t psm, bool create);
    DepthTarget *getDepthTarget(uint32_t zbp, uint32_t fbw, uint32_t width, uint32_t height);
    uint32_t resolveTexture(const GSDrawState &state, uint32_t &outWidth, uint32_t &outHeight);
    uint32_t decodeTexture(const GSDrawState &state, const TextureKey &key, uint32_t width, uint32_t height, uint32_t pageStart, uint32_t pageCount);
    void downloadRenderTargetToShadow(RenderTarget &rt);
    void downloadRenderTargetToCpu(RenderTarget &rt);
    void refreshRenderTargetsFromShadow(uint32_t page, uint32_t pageCount, const GSTransferCommand &transfer);
    void refreshDirtyRows(RenderTarget &rt);
    void markShadowPages(uint32_t page, uint32_t pageCount);
    void setupDrawState(const GSDrawState &state);
    void appendVertex(const GSVertex &v, const GSDrawState &state, bool flatColorFromLast, const GSVertex &colorSource);

    static uint32_t pageSpan(uint32_t psm, uint32_t bufferWidth64, uint32_t heightPixels);
    static uint32_t pageHeightForPsm(uint32_t psm);

    std::unique_ptr<GSCpuBackend> m_cpu;
    std::unique_ptr<GSCpuBackend> m_shadow;
    std::vector<uint8_t> m_shadowMemory;
    uint8_t *m_vram = nullptr;
    uint32_t m_vramSize = 0;

    // command stream
    mutable std::mutex m_queueMutex;
    std::condition_variable m_queueCv;
    CommandBuffer m_pending;
    CommandBuffer m_executing;
    uint64_t m_nextToken = 1;
    std::atomic<uint64_t> m_executedToken{0};
    std::atomic<bool> m_glReady{false};
    std::thread::id m_renderThread{};

    // GPU-dirty page tracking (written on the game thread from draw submissions)
    mutable std::mutex m_dirtyMutex;
    std::array<uint8_t, 512> m_gpuDirtyPages{};

    // render thread state
    std::vector<RenderTarget> m_renderTargets;
    std::vector<DepthTarget> m_depthTargets;
    std::unordered_map<TextureKey, TextureEntry, TextureKeyHash> m_textures;
    std::array<uint64_t, 512> m_shadowPageGeneration{};
    uint64_t m_generation = 1;
    uint64_t m_frameCounter = 0;

    uint32_t m_program = 0;
    uint32_t m_vao = 0;
    uint32_t m_vbo = 0;
    struct Uniforms
    {
        int rtSize = -1, tex = -1, texSize = -1, tme = -1, tfx = -1, tcc = -1, fst = -1, wrapU = -1, wrapV = -1;
        int region = -1, ate = -1, atst = -1, afail = -1, aref = -1, fge = -1, fogColor = -1, fba = -1;
    } m_u;

    std::vector<GlVertex> m_vertices;
    bool m_hasBatch = false;
    DrawKey m_batchKey{};
    GSDrawState m_batchState{};
    RenderTarget *m_batchRt = nullptr;

    // presentation
    uint32_t m_presentTexture = 0;
    uint32_t m_presentWidth = 0;
    uint32_t m_presentHeight = 0;
    uint32_t m_presentFbp = 0;
    uint32_t m_presentCopyTexture = 0;
    uint32_t m_presentCopyFbo = 0;
    uint32_t m_presentTexWidth = 0;
    uint32_t m_presentTexHeight = 0;
    std::vector<uint8_t> m_presentPixels;   // filled only when a frame dump is requested
    bool m_presentPixelsRequested = false;

    // transfer bookkeeping for readback decisions (game thread)
    GSTransferCommand m_currentTransfer{};
    std::string m_blendLog;
    std::string m_stateLog;
    uint64_t m_uploadExpectedBytes = 0;
    uint64_t m_uploadReceivedBytes = 0;
};
