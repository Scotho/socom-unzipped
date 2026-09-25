#include "ps2recomp/control_flow_analyzer.h"
#include "ps2recomp/types.h"
#include "ps2recomp/instructions.h"
#include "ps2recomp/control_flow_utils.h"
#include "ps2recomp/recompiler_reporter.h"

#include <algorithm>
#include <cstring>

namespace ps2recomp
{
    ControlFlowAnalyzer::ControlFlowAnalyzer(
        const std::vector<Section> &sections,
        const std::unordered_map<uint32_t, std::vector<uint32_t>> &configuredJumpTableTargetsByAddress,
        RecompilerReporter *reporter)
        : m_sections(sections),
          m_configJumpTableTargetsByAddress(configuredJumpTableTargetsByAddress),
          m_reporter(reporter)
    {
    }

    ControlFlowAnalysisResult ControlFlowAnalyzer::analyze(
        const Function &function,
        const std::vector<Instruction> &instructions,
        const std::vector<Function> *allFunctions) const
    {
        ControlFlowAnalysisResult result;
        std::unordered_set<uint32_t> instructionAddresses;
        instructionAddresses.reserve(instructions.size());
        bool hasIndirectRegisterJump = false;
        std::vector<const Instruction *> indirectJumps;

        auto isExecutableAddress = [&](uint32_t address) -> bool
        {
            for (const auto &section : m_sections)
            {
                if (!section.isCode)
                {
                    continue;
                }
                if (address >= section.address && address < (section.address + section.size))
                {
                    return true;
                }
            }
            return false;
        };

        auto findContainingExternalFunction = [&](uint32_t address) -> const Function *
        {
            if (!allFunctions || !isExecutableAddress(address))
            {
                return nullptr;
            }

            const Function *best = nullptr;
            for (const auto &candidateFn : *allFunctions)
            {
                if (!candidateFn.isRecompiled || candidateFn.isStub || candidateFn.isSkipped)
                {
                    continue;
                }

                if (candidateFn.name.rfind("entry_", 0) == 0)
                {
                    continue;
                }

                if (address < candidateFn.start || address >= candidateFn.end)
                {
                    continue;
                }

                if (!best || candidateFn.start > best->start)
                {
                    best = &candidateFn;
                }
            }

            return best;
        };

        auto queueExternalEntryTarget = [&](uint32_t target)
        {
            const Function *containingFn = findContainingExternalFunction(target);
            if (!containingFn)
            {
                return;
            }

            if (containingFn->start == function.start)
            {
                return;
            }

            if (target == containingFn->start)
            {
                return;
            }

            result.externalEntryPoints.insert(target);
        };

        // Is this address inside any row of the map at all -- stubs, skipped rows and entry_
        // slices included? Used only to decide whether a continuation is worth warning about.
        auto isCoveredByAnyFunction = [&](uint32_t address) -> bool
        {
            if (!allFunctions)
            {
                // No map to judge against (unit fixtures): say nothing.
                return true;
            }

            for (const auto &candidateFn : *allFunctions)
            {
                if (address >= candidateFn.start && address < candidateFn.end)
                {
                    return true;
                }
            }

            return false;
        };

        // Where a thread resumes: a call's return pc, a syscall's return pc, a not-taken branch's
        // fallthrough, a loop's back edge. The scheduler dispatches on that pc, so some recompiled
        // function has to own it.
        //
        // Ghidra's map sometimes starts the next row ON a delay slot (FUN_00544550 begins at the
        // delay slot of the jal at 0x54454c), which puts the continuation one instruction inside
        // the *next* row. Registering it only when it falls in the producing row -- what this did
        // before -- left those pcs owned by nobody and the thread died at
        // [guest-branch:missing-target]. Register it wherever it lands, the way an external branch
        // target is resolved, and say so at build time when it lands in no row at all.
        enum class ContinuationScope
        {
            AnyRow,      // the producing row may own it (a resume entry of this function)
            CrossRowOnly // only another row may own it
        };

        auto queueContinuationTarget = [&](uint32_t continuationPc,
                                           uint32_t sourcePc,
                                           const char *kind,
                                           ContinuationScope scope)
        {
            if (continuationPc >= function.start && continuationPc < function.end &&
                instructionAddresses.contains(continuationPc))
            {
                if (scope == ContinuationScope::AnyRow)
                {
                    result.entryPoints.insert(continuationPc);
                    result.resumeEntryPoints.insert(continuationPc);
                }

                // A continuation inside the producing row needs nothing when the row itself is
                // what runs it: the generated function simply carries on at that instruction.
                return;
            }

            if (findContainingExternalFunction(continuationPc))
            {
                // Owned by another row: register it exactly as a cross-function branch target is
                // registered, guards and all -- one source of truth for "this entry is legitimate".
                queueExternalEntryTarget(continuationPc);
                return;
            }

            if (isCoveredByAnyFunction(continuationPc))
            {
                return;
            }

            if (m_reporter)
            {
                m_reporter->recordUnmappedContinuation(function.name, sourcePc, continuationPc, kind);
            }
        };

        auto queueResumeEntryTarget = [&](uint32_t resumeAddr, uint32_t sourcePc, const char *kind)
        {
            queueContinuationTarget(resumeAddr, sourcePc, kind, ContinuationScope::AnyRow);
        };

        auto queueLoopResumeEntryTarget = [&](uint32_t target, uint32_t sourcePc)
        {
            if (target > sourcePc || target == function.start)
            {
                return;
            }

            queueResumeEntryTarget(target, sourcePc, "loop back edge");
        };

        // `b`/`bl` are assembled as beq/beql over two equal registers: nothing reaches their +8.
        auto branchAlwaysTaken = [](const Instruction &inst) -> bool
        {
            return (inst.opcode == OPCODE_BEQ || inst.opcode == OPCODE_BEQL) && inst.rs == inst.rt;
        };

        auto readImageWord = [&](uint32_t address, uint32_t &out) -> bool
        {
            if (address & 3u)
            {
                return false;
            }

            for (const auto &section : m_sections)
            {
                if (!section.data || address < section.address ||
                    (static_cast<uint64_t>(address) + 4ull) >
                        (static_cast<uint64_t>(section.address) + section.size))
                {
                    continue;
                }

                std::memcpy(&out, section.data + (address - section.address), sizeof(out));
                return true;
            }

            return false;
        };

        // The primary opcodes the R5900 does not define -- the same table
        // tools_py/find_data_entries.py screens data words with. A word out of a string table or a
        // float array picks one of these often enough to be worth asking.
        auto decodesAsInstruction = [](uint32_t raw) -> bool
        {
            switch (raw >> 26)
            {
            case 0x13u:                                       // COP3
            case 0x1Du:                                       // unassigned
            case 0x30u: case 0x32u: case 0x34u: case 0x35u:   // ll and the unassigned COPz loads
            case 0x38u: case 0x3Au: case 0x3Bu:               // sc and the unassigned COPz stores
            case 0x3Cu: case 0x3Du:
                return false;
            default:
                return true;
            }
        };

        auto isTransferWord = [](uint32_t raw) -> bool
        {
            const uint32_t op = raw >> 26;
            if (op == OPCODE_J || op == OPCODE_JAL || op == OPCODE_REGIMM ||
                (op >= OPCODE_BEQ && op <= OPCODE_BGTZ) ||
                (op >= OPCODE_BEQL && op <= OPCODE_BGTZL))
            {
                return true;
            }
            return op == OPCODE_SPECIAL && ((raw & 0x3Fu) == SPECIAL_JR || (raw & 0x3Fu) == SPECIAL_JALR);
        };

        // A row the map laid over data decodes data words as branches. A garbage *target* mostly
        // resolves to nothing and is dropped; a garbage *fallthrough* is the next two words, so it
        // lands inside a genuine row almost every time and would be registered -- handing the
        // runtime a function-table slot for a pc that should have faulted, and silencing the very
        // [guest-branch:missing-target] this whole change exists to expose. Four shapes say "data",
        // each one find_data_entries.py already earns its keep with. (That the row the
        // continuation lands in is text is enforced by findContainingExternalFunction, which
        // resolves only inside a code section.)
        auto fallthroughLooksLikeCode = [&](const Instruction &inst, uint32_t target) -> bool
        {
            if (!isExecutableAddress(target))
            {
                return false;                     // a branch out of the image is table data
            }

            if (target == inst.address + 4u)
            {
                return false;                     // 0x04210000, "bgez at,+0": a float, not code
            }

            uint32_t word = 0;
            if (readImageWord(inst.address + 4u, word) &&
                (!decodesAsInstruction(word) || isTransferWord(word)))
            {
                return false;                     // no delay slot holds a branch: this is not code
            }

            if (readImageWord(inst.address + 8u, word) && !decodesAsInstruction(word))
            {
                return false;                     // the continuation itself is not an instruction
            }

            return true;
        };

        for (const auto &inst : instructions)
        {
            instructionAddresses.insert(inst.address);
            if (inst.opcode == OPCODE_SPECIAL &&
                ((inst.function == SPECIAL_JR && inst.rs != 31) ||
                 inst.function == SPECIAL_JALR))
            {
                hasIndirectRegisterJump = true;
                indirectJumps.push_back(&inst);
            }
        }

        for (const auto &inst : instructions)
        {
            // A guest-installed syscall handler runs as a separate invocation,
            // so the scheduler resumes this thread at syscall+4 and needs an
            // entry point there. +4, not +8: syscall has no delay slot.
            if (inst.opcode == OPCODE_SPECIAL && inst.function == SPECIAL_SYSCALL)
            {
                queueResumeEntryTarget(inst.address + 4u, inst.address, "syscall return");
            }

            bool isStaticJump = (inst.opcode == OPCODE_J || inst.opcode == OPCODE_JAL);
            if (inst.isBranch && inst.opcode != OPCODE_J && inst.opcode != OPCODE_JAL)
            {
                const int32_t offsetBytes = (static_cast<int32_t>(static_cast<int16_t>(inst.simmediate)) << 2);
                const uint32_t target = static_cast<uint32_t>(
                    static_cast<int64_t>(inst.address + 4u) + static_cast<int64_t>(offsetBytes));

                if (target >= function.start && target < function.end &&
                    instructionAddresses.contains(target))
                {
                    result.entryPoints.insert(target);
                    queueLoopResumeEntryTarget(target, inst.address);
                }
                else
                {
                    queueExternalEntryTarget(target);
                }

                // The not-taken path continues at +8. Only another row can need that registered:
                // inside this row the generated code falls through to it on its own. Both cheap
                // questions -- is there a map at all, does the continuation even leave this row --
                // come before the gate, which reads the image and is the only thing here that
                // touches the sections.
                const uint32_t fallthroughPc = inst.address + 8u;
                const bool insideThisRow = fallthroughPc >= function.start &&
                                           fallthroughPc < function.end &&
                                           instructionAddresses.contains(fallthroughPc);
                if (allFunctions && !insideThisRow && !branchAlwaysTaken(inst) &&
                    fallthroughLooksLikeCode(inst, target))
                {
                    queueContinuationTarget(fallthroughPc, inst.address, "branch fallthrough",
                                            ContinuationScope::CrossRowOnly);
                }
            }
            else if (isStaticJump)
            {
                uint32_t target = buildAbsoluteJumpTarget(inst.address, inst.target);
                if (target >= function.start && target < function.end &&
                    instructionAddresses.contains(target))
                {
                    result.entryPoints.insert(target);
                    queueLoopResumeEntryTarget(target, inst.address);

                    if (inst.opcode == OPCODE_JAL)
                    {
                        queueResumeEntryTarget(inst.address + 8u, inst.address, "call return");
                    }
                }
                else
                {
                    queueExternalEntryTarget(target);

                    if (inst.opcode == OPCODE_JAL)
                    {
                        queueResumeEntryTarget(inst.address + 8u, inst.address, "call return");
                    }
                }
            }
        }

        if (hasIndirectRegisterJump)
        {
            bool needsIndirectFallback = false;
            for (const Instruction *jrInst : indirectJumps)
            {
                if (jrInst->function == SPECIAL_JALR)
                {
                    queueResumeEntryTarget(jrInst->address + 8u, jrInst->address, "call return");
                }

                bool foundTable = false;

                uint32_t jrReg = jrInst->rs;

                int lwIndex = -1;
                uint32_t baseReg = 0;
                int32_t lwOffset = 0;

                auto it = std::find_if(instructions.begin(), instructions.end(), [&](const Instruction &inst)
                                       { return inst.address == jrInst->address; });
                if (it != instructions.end())
                {
                    int jrIndex = std::distance(instructions.begin(), it);
                    for (int i = jrIndex - 1; i >= 0 && i >= jrIndex - 20; --i)
                    {
                        const auto &inst = instructions[i];
                        if ((inst.opcode == OPCODE_LW || inst.opcode == OPCODE_LWU) && inst.rt == jrReg)
                        {
                            lwIndex = i;
                            baseReg = inst.rs;
                            lwOffset = inst.simmediate;
                            break;
                        }
                    }

                    if (lwIndex != -1)
                    {
                        int adduIndex = -1;
                        uint32_t tableBaseReg = 0;
                        uint32_t indexReg = 0;
                        for (int i = lwIndex - 1; i >= 0 && i >= lwIndex - 10; --i)
                        {
                            const auto &inst = instructions[i];
                            if (inst.opcode == OPCODE_SPECIAL && inst.function == SPECIAL_ADDU && inst.rd == baseReg)
                            {
                                adduIndex = i;
                                tableBaseReg = inst.rs;
                                indexReg = inst.rt;
                                break;
                            }
                        }

                        uint32_t tableAddress = 0;
                        bool foundTableAddress = false;

                        if (adduIndex != -1)
                        {
                            for (int i = adduIndex - 1; i >= 0 && i >= adduIndex - 20; --i)
                            {
                                const auto &inst = instructions[i];
                                if (inst.opcode == OPCODE_LUI)
                                {
                                    if (inst.rt == tableBaseReg || inst.rt == indexReg)
                                    {
                                        uint32_t high = inst.immediate << 16;
                                        uint32_t low = 0;
                                        for (int j = i + 1; j < adduIndex; ++j)
                                        {
                                            const auto &lowInst = instructions[j];
                                            if (lowInst.rs == inst.rt && lowInst.rt == inst.rt)
                                            {
                                                if (lowInst.opcode == OPCODE_ADDIU)
                                                {
                                                    low = (uint32_t)lowInst.simmediate;
                                                }
                                                else if (lowInst.opcode == OPCODE_ORI)
                                                {
                                                    low = lowInst.immediate;
                                                }
                                            }
                                        }
                                        tableAddress = high + low;
                                        foundTableAddress = true;
                                        break;
                                    }
                                }
                            }
                        }

                        if (foundTableAddress)
                        {
                            tableAddress += lwOffset;

                            const auto configuredTableIt = m_configJumpTableTargetsByAddress.find(tableAddress);
                            if (configuredTableIt != m_configJumpTableTargetsByAddress.end())
                            {
                                std::vector<uint32_t> jrTargets;
                                jrTargets.reserve(configuredTableIt->second.size());
                                for (uint32_t target : configuredTableIt->second)
                                {
                                    if (target >= function.start && target < function.end &&
                                        instructionAddresses.contains(target))
                                    {
                                        jrTargets.push_back(target);
                                    }
                                    else
                                    {
                                        queueExternalEntryTarget(target);
                                    }
                                }

                                if (!jrTargets.empty())
                                {
                                    std::sort(jrTargets.begin(), jrTargets.end());
                                    jrTargets.erase(std::unique(jrTargets.begin(), jrTargets.end()), jrTargets.end());
                                    result.jumpTableTargets[jrInst->address] = jrTargets;
                                    for (uint32_t target : jrTargets)
                                    {
                                        result.entryPoints.insert(target);
                                    }
                                    foundTable = true;
                                }
                            }

                            uint32_t unshiftedIndexReg = 0;
                            for (int i = adduIndex - 1; i >= 0 && i >= adduIndex - 10; --i)
                            {
                                const auto &inst = instructions[i];
                                if (inst.opcode == OPCODE_SPECIAL && inst.function == SPECIAL_SLL && (inst.rd == tableBaseReg || inst.rd == indexReg))
                                {
                                    unshiftedIndexReg = inst.rt;
                                    break;
                                }
                            }

                            uint32_t numCases = 0;
                            if (unshiftedIndexReg != 0)
                            {
                                for (int i = adduIndex - 1; i >= 0 && i >= adduIndex - 30; --i)
                                {
                                    const auto &inst = instructions[i];
                                    if ((inst.opcode == OPCODE_SLTIU || inst.opcode == OPCODE_SLTI) && inst.rs == unshiftedIndexReg)
                                    {
                                        numCases = inst.immediate;
                                        break;
                                    }
                                }
                            }

                            if (!foundTable && numCases > 0 && numCases <= 1000)
                            {
                                const Section *rodata = nullptr;
                                for (const auto &sec : m_sections)
                                {
                                    if (tableAddress >= sec.address && tableAddress < sec.address + sec.size)
                                    {
                                        rodata = &sec;
                                        break;
                                    }
                                }

                                if (rodata && rodata->data)
                                {
                                    std::vector<uint32_t> jrTargets;
                                    bool validJumpTable = true;
                                    std::unordered_set<uint32_t> uniqueTargets;
                                    for (uint32_t i = 0; i < numCases; ++i)
                                    {
                                        uint32_t addr = tableAddress + i * 4;
                                        if (addr >= rodata->address && addr + 4 <= rodata->address + rodata->size)
                                        {
                                            uint32_t target = 0;
                                            std::memcpy(&target, rodata->data + (addr - rodata->address), 4);
                                            if (target >= function.start && target < function.end && instructionAddresses.contains(target))
                                            {
                                                if (!uniqueTargets.contains(target))
                                                {
                                                    jrTargets.push_back(target);
                                                    uniqueTargets.insert(target);
                                                }
                                            }
                                            else
                                            {
                                                queueExternalEntryTarget(target);
                                            }
                                        }
                                        else
                                        {
                                            validJumpTable = false;
                                            break;
                                        }
                                    }
                                    if (validJumpTable && !jrTargets.empty())
                                    {
                                        result.jumpTableTargets[jrInst->address] = jrTargets;
                                        for (uint32_t t : jrTargets)
                                        {
                                            result.entryPoints.insert(t);
                                        }
                                        foundTable = true;
                                    }
                                }
                            }
                        }
                    }
                }
                if (!foundTable)
                {
                    needsIndirectFallback = true;
                }
            }

            if (needsIndirectFallback)
            {
                if (m_reporter)
                {
                    std::vector<uint32_t> jumpAddresses;
                    jumpAddresses.reserve(indirectJumps.size());
                    for (const Instruction *jrInst : indirectJumps)
                    {
                        jumpAddresses.push_back(jrInst->address);
                    }
                    m_reporter->recordIndirectFallbackPromotion(function.name, jumpAddresses, instructionAddresses.size());
                }

                for (uint32_t addr : instructionAddresses)
                {
                    if (addr >= function.start && addr < function.end)
                    {
                        result.entryPoints.insert(addr);
                        // Keep labels and runtime registration for unresolved JR/JALR targets
                        // without emitting a local switch over every possible target.
                        result.indirectFallbackEntryPoints.insert(addr);
                    }
                }
            }
        }

        return result;
    }

}
