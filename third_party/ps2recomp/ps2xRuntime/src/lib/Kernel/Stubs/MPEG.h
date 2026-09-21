#pragma once

#include "ps2_stubs.h"

namespace ps2_stubs
{
    void resetMpegStubState();
    // A demux call that consumes nothing (the presenter is far enough ahead, or the game's stream callback refused
    // the packet) lets any ready guest thread run once before returning 0, so a game that re-polls in a loop does
    // not starve its lower-priority threads (research/32 section 7.1).
    void setMpegDemuxIdleYields(bool enabled);
    void enqueueMpegDecodedFrameForTesting(uint32_t mpegAddr);
    // research/36 item 16: the decode gate's held video, the audio the game refused (set aside), and a way to let the
    // presenter "serve" pictures without a decoder.
    size_t mpegHeldVideoPacketsForTesting(uint32_t mpegAddr);
    size_t mpegAsideAudioPacketsForTesting(uint32_t mpegAddr);
    void mpegDropDecodedFramesForTesting(uint32_t mpegAddr, size_t count);
    // Drops the decoded pictures that are overdue by a whole interval at `currentTick` (vsync ticks) and returns
    // how many stay queued; the presenter's real-time policy, exposed for the test.
    size_t mpegSkipOverduePicturesForTesting(uint32_t mpegAddr, uint64_t currentTick);
    void notifyMpegCdStreamStart(PS2Runtime *runtime = nullptr);
    void notifyMpegCdStreamDataProduced(uint32_t byteCount, bool endOfStream);
    void notifyMpegCdStreamEof(PS2Runtime *runtime = nullptr);
    void sceMpegFlush(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegAddBs(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegAddCallback(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegAddStrCallback(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegClearRefBuff(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegCreate(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegDelete(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegDemuxPss(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegDemuxPssRing(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegDispCenterOffX(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegDispCenterOffY(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegDispHeight(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegDispWidth(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegGetDecodeMode(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegGetPicture(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegGetPictureRAW8(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegGetPictureRAW8xy(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegInit(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegIsEnd(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegIsRefBuffEmpty(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegReset(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegResetDefaultPtsGap(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegSetDecodeMode(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegSetDefaultPtsGap(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceMpegSetImageBuff(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
}
