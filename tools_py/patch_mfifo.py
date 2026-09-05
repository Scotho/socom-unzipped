"""One-off patch: add fromSPR/toSPR DMA channels and MFIFO ring draining to ps2_memory.cpp/h.
Idempotent (checks for markers)."""
import sys

root = 'C:/projects/socom_pc/third_party/ps2recomp/ps2xRuntime/'
h = root + 'include/runtime/ps2_memory.h'
c = root + 'src/lib/ps2_memory.cpp'


def patch(path, pairs):
    s = open(path, encoding='utf-8').read()
    if 'mfifoDrainChannel' in s:
        print(path, 'already patched')
        return
    for old, new in pairs:
        assert old in s, old[:60]
        s = s.replace(old, new, 1)
    open(path, 'w', encoding='utf-8', newline='\n').write(s)
    print('patched', path)


patch(h, [
    ("    void processPendingTransfers();\n    std::vector<uint32_t> consumeCompletedDmacCauses();",
     """    void processPendingTransfers();
    std::vector<uint32_t> consumeCompletedDmacCauses();
    // MFIFO (D_CTRL.MFD): fromSPR (D8) feeds a ring buffer [RBOR, RBOR+RBSR+16) that VIF1 or GIF
    // drains in chain mode, stalling when TADR catches up with D8_MADR.
    uint32_t mfifoDrainChannel() const;
    bool isMfifoStalled(uint32_t channelBase) const { return m_mfifoStalled && channelBase == m_mfifoStalledChannel; }
    void kickMfifoDrain();
    void runSprDma(uint32_t channelBase, uint32_t chcr);"""),
    ("    std::vector<PendingTransfer> m_pendingVif1Transfers;",
     "    std::vector<PendingTransfer> m_pendingVif1Transfers;\n    bool m_mfifoStalled = false;\n    uint32_t m_mfifoStalledChannel = 0u;"),
])

cpp_pairs = [
    # 1. SPR channels + MFIFO awareness at the CHCR start
    ("""            const uint32_t channelBase = address & 0xFFFFFF00;
            const uint32_t madr = m_ioRegisters[channelBase + 0x10];
            const uint32_t qwc = m_ioRegisters[channelBase + 0x20];
            m_dmaStartCount.fetch_add(1, std::memory_order_relaxed);
""",
     """            const uint32_t channelBase = address & 0xFFFFFF00;
            const uint32_t madr = m_ioRegisters[channelBase + 0x10];
            const uint32_t qwc = m_ioRegisters[channelBase + 0x20];
            m_dmaStartCount.fetch_add(1, std::memory_order_relaxed);

            if (channelBase == 0x1000D000u || channelBase == 0x1000D400u)
            {
                runSprDma(channelBase, value);
                return true;
            }
            const bool mfifoDrain = (channelBase == mfifoDrainChannel());
            const uint32_t rbor = m_ioRegisters[0x1000E040u];
            const uint32_t rbsr = m_ioRegisters[0x1000E050u];
            auto ringWrap = [&](uint32_t a) -> uint32_t
            {
                return mfifoDrain ? (rbor + ((a - rbor) & rbsr)) : a;
            };
            bool mfifoStalledNow = false;
"""),
    # 2. ring-aware data append
    ("""                        while (bytes > 0)
                        {
                            if (src >= maxSz2)
                                src = 0;
                            uint32_t chunk = bytes;
                            if (src + chunk > maxSz2)
                                chunk = maxSz2 - src;
                            if (chunk == 0)
                                break;
                            chainBuf.insert(chainBuf.end(), base2 + src, base2 + src + chunk);
                            bytes -= chunk;
                            src += chunk;
                        }
                    };
""",
     """                        const bool inRing = mfifoDrain && !scratch && srcAddr >= rbor && srcAddr <= rbor + rbsr;
                        if (inRing)
                        {
                            uint32_t a = srcAddr;
                            while (bytes >= 16)
                            {
                                const uint32_t phys = translateAddress(a);
                                if (phys + 16 > maxSz2)
                                    break;
                                chainBuf.insert(chainBuf.end(), base2 + phys, base2 + phys + 16);
                                bytes -= 16;
                                a = rbor + ((a + 16 - rbor) & rbsr);
                            }
                            return;
                        }
                        while (bytes > 0)
                        {
                            if (src >= maxSz2)
                                src = 0;
                            uint32_t chunk = bytes;
                            if (src + chunk > maxSz2)
                                chunk = maxSz2 - src;
                            if (chunk == 0)
                                break;
                            chainBuf.insert(chainBuf.end(), base2 + src, base2 + src + chunk);
                            bytes -= chunk;
                            src += chunk;
                        }
                    };
"""),
    # 3. stall check + wrap at each tag
    ("""                    while (tagsProcessed < kMaxChainTags)
                    {
                        const uint32_t currentTagAddr = tagAddr;
""",
     """                    while (tagsProcessed < kMaxChainTags)
                    {
                        if (mfifoDrain)
                        {
                            tagAddr = ringWrap(tagAddr);
                            if (tagAddr == m_ioRegisters[0x1000D010u])   // MFIFO empty: wait for fromSPR
                            {
                                mfifoStalledNow = true;
                                break;
                            }
                        }
                        const uint32_t currentTagAddr = tagAddr;
"""),
    # 4. after the loop: keep STR when stalled
    ("""                    m_ioRegisters[channelBase + 0x30] = tagAddr;
                    m_ioRegisters[channelBase + 0x40] = asr0;
                    m_ioRegisters[channelBase + 0x50] = asr1;
                    chcr = (chcr & ~(0x3u << 4)) | ((asp & 0x3u) << 4);
                    chcr = (chcr & 0x0000FFFFu) | (lastTagUpper << 16);
                    m_ioRegisters[channelBase + 0x00] = chcr;
""",
     """                    m_ioRegisters[channelBase + 0x30] = ringWrap(tagAddr);
                    m_ioRegisters[channelBase + 0x40] = asr0;
                    m_ioRegisters[channelBase + 0x50] = asr1;
                    chcr = (chcr & ~(0x3u << 4)) | ((asp & 0x3u) << 4);
                    chcr = (chcr & 0x0000FFFFu) | (lastTagUpper << 16);
                    if (mfifoDrain)
                    {
                        m_mfifoStalled = mfifoStalledNow;
                        m_mfifoStalledChannel = mfifoStalledNow ? channelBase : 0u;
                        if (mfifoStalledNow)
                            chcr |= 0x100u;          // still running, waiting for data
                    }
                    m_ioRegisters[channelBase + 0x00] = chcr;
"""),
    # 5. processPendingTransfers: do not complete a stalled MFIFO channel
    ("""    if (hadGif)
    {
        raiseDStatChannel(2u); // GIF channel
""",
     """    if (hadGif && !isMfifoStalled(GIF_CHANNEL))
    {
        raiseDStatChannel(2u); // GIF channel
"""),
    ("""    if (hadVif1)
    {
        raiseDStatChannel(1u); // VIF1 channel
        queueCompletedDmacCause(1u);
        m_ioRegisters[VIF1_CHANNEL + 0x00] &= ~0x100u;
        m_ioRegisters[VIF1_CHANNEL + 0x20] = 0;
    }
}
""",
     """    if (hadVif1 && !isMfifoStalled(VIF1_CHANNEL))
    {
        raiseDStatChannel(1u); // VIF1 channel
        queueCompletedDmacCause(1u);
        m_ioRegisters[VIF1_CHANNEL + 0x00] &= ~0x100u;
        m_ioRegisters[VIF1_CHANNEL + 0x20] = 0;
    }
}

uint32_t PS2Memory::mfifoDrainChannel() const
{
    auto it = m_ioRegisters.find(0x1000E000u);
    const uint32_t mfd = it == m_ioRegisters.end() ? 0u : ((it->second >> 2) & 3u);
    if (mfd == 2u)
        return 0x10009000u;   // VIF1
    if (mfd == 3u)
        return 0x1000A000u;   // GIF
    return 0u;
}

void PS2Memory::kickMfifoDrain()
{
    const uint32_t channelBase = mfifoDrainChannel();
    if (channelBase == 0u)
        return;
    const uint32_t chcr = m_ioRegisters[channelBase + 0x00];
    if ((chcr & 0x100u) == 0u || ((chcr >> 2) & 3u) != 1u)
        return;                       // drain channel not started, or not in chain mode
    m_mfifoStalled = false;           // re-evaluate against the new D8_MADR
    writeIORegister(channelBase, chcr | 0x100u);
}

// D8 (fromSPR) / D9 (toSPR) normal-mode transfers; fromSPR honours the MFIFO ring when enabled.
void PS2Memory::runSprDma(uint32_t channelBase, uint32_t chcr)
{
    const bool fromSpr = (channelBase == 0x1000D000u);
    uint32_t madr = m_ioRegisters[channelBase + 0x10];
    const uint32_t qwc = m_ioRegisters[channelBase + 0x20];
    uint32_t sadr = m_ioRegisters[channelBase + 0x80] & (PS2_SCRATCHPAD_SIZE - 1u);
    const uint32_t rbor = m_ioRegisters[0x1000E040u];
    const uint32_t rbsr = m_ioRegisters[0x1000E050u];
    const bool ring = fromSpr && mfifoDrainChannel() != 0u;
    for (uint32_t i = 0; i < qwc; ++i)
    {
        uint32_t phys = 0;
        try
        {
            phys = translateAddress(madr);
        }
        catch (...)
        {
            break;
        }
        if (phys + 16u > PS2_RAM_SIZE)
            break;
        if (fromSpr)
            std::memcpy(m_rdram + phys, m_scratchpad + sadr, 16);
        else
            std::memcpy(m_scratchpad + sadr, m_rdram + phys, 16);
        sadr = (sadr + 16u) & (PS2_SCRATCHPAD_SIZE - 1u);
        madr = ring ? (rbor + ((madr + 16u - rbor) & rbsr)) : (madr + 16u);
    }
    m_ioRegisters[channelBase + 0x10] = madr;
    m_ioRegisters[channelBase + 0x20] = 0u;
    m_ioRegisters[channelBase + 0x80] = sadr;
    m_ioRegisters[channelBase + 0x00] = chcr & ~0x100u;
    const uint32_t channelBit = fromSpr ? 8u : 9u;
    uint32_t dstat = m_ioRegisters.count(0x1000E010u) ? m_ioRegisters[0x1000E010u] : 0u;
    dstat |= (1u << channelBit);
    if (((dstat & 0x3FFu) & ((dstat >> 16) & 0x3FFu)) != 0u)
        dstat |= (1u << 31);
    m_ioRegisters[0x1000E010u] = dstat;
    queueCompletedDmacCause(channelBit);
    if (ring)
        kickMfifoDrain();
}
"""),
    # 6. CHCR read: keep STR visible while the MFIFO drain channel is stalled
    ("""            if ((address & 0xFF) == 0x00)
            {
                uint32_t channelStatus = m_ioRegisters[address] & ~0x100u;
""",
     """            if ((address & 0xFF) == 0x00)
            {
                if (isMfifoStalled(address))
                    return m_ioRegisters[address] | 0x100u;
                uint32_t channelStatus = m_ioRegisters[address] & ~0x100u;
"""),
]
patch(c, cpp_pairs)
