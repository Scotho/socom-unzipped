#include "launcher/diagnostics.h"

#include "launcher/launcher_config.h"
#include "ps2x/exit_codes.h"

#include <algorithm>
#include <initializer_list>
#include <regex>

namespace launcher::diagnostics
{
    namespace
    {
        bool startsWith(const std::string &line, const char *prefix)
        {
            return line.rfind(prefix, 0) == 0;
        }

        // The lines of `text` (CR dropped) that start with one of `prefixes`, each ended with '\n'.
        std::string linesStartingWith(const std::string &text, std::initializer_list<const char *> prefixes)
        {
            std::string out;
            size_t pos = 0;
            while (pos < text.size())
            {
                size_t end = text.find('\n', pos);
                if (end == std::string::npos)
                    end = text.size();
                std::string line = text.substr(pos, end - pos);
                pos = end + 1;
                if (!line.empty() && line.back() == '\r')
                    line.pop_back();
                for (const char *prefix : prefixes)
                    if (startsWith(line, prefix))
                    {
                        out += line;
                        out.push_back('\n');
                        break;
                    }
            }
            return out;
        }

        void replaceAll(std::string &text, const std::string &what, const std::string &with)
        {
            if (what.empty())
                return;
            size_t pos = 0;
            while ((pos = text.find(what, pos)) != std::string::npos)
            {
                text.replace(pos, what.size(), with);
                pos += with.size();
            }
        }
    }

    std::string sanitizedConfigJson(const std::string &configText)
    {
        Config config;
        if (!fromJson(configText, config))
            return "{\n  \"error\": \"config.json was malformed and is not included\"\n}\n";
        const size_t slash = config.isoPath.find_last_of("/\\");
        if (slash != std::string::npos)
            config.isoPath = config.isoPath.substr(slash + 1);
        // Sprint 10 Goal 9, R179: the password stays in the player's own file and nowhere else. The key is
        // written empty, so a reader of the zip sees the field was blanked rather than absent. (The credential
        // scrubber over the text is no substitute: it has a six-character floor, and "socom" is five.)
        config.loginPassword.clear();
        return toJson(config);
    }

    // Sprint 10 H6 (the KNOWN row): the home directory used to be matched case-sensitively in its three slash
    // spellings and nothing else was redacted, so `c:\users\bob`, `C:\Users\BOB~1`, another account's directory,
    // a credential printed on a log line and a peer's address all reached the report. Now: every user directory on
    // the machine -- `<drive>:\Users\<name>`, `/home/<name>`, `/Users/<name>`, either slash, any case, any short
    // name -- becomes `~`; a value after a credential-shaped key becomes `[redacted]`; every IPv4 but the project's
    // hosted box becomes `[ip]`. The rules are the leak check's (tools_py/release/leakrules.py), reduced to what a
    // run log can carry. std::regex over a log that clipLog has already bounded (4.3 MB at most; 64 KB for a bug
    // report) is fast enough, and it runs once per report.
    namespace
    {
        const std::regex kUserDir(R"((?:[A-Za-z]:[\\/]{1,2}Users[\\/]{1,2}|/home/|/Users/)[^\\/\s"'<>|]+)", std::regex::icase);
        const std::regex kCredential(
            R"((\b[\w-]{0,24}?(?:token|secret|password|passwd|pwd|api[_-]?key|access[_-]?key|private[_-]?key|bearer|credential|pass)s?\s*[:=]\s*)["']?([^\s"',;]{6,}))",
            std::regex::icase);
        const std::regex kIpv4(R"((?:^|[^\w.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\w.]))");
        const char *const kHostedIp = "3.143.65.100";

        bool isAddress(const std::smatch &m)
        {
            for (size_t g = 1; g <= 4; ++g)
            {
                const std::string &octet = m[g].str();
                if (octet.size() > 1 && octet[0] == '0')
                    return false;                      // 2.4.1.01: a version, not an address
                if (std::stoi(octet) > 255)
                    return false;                      // 31.0.15.2000: a driver version; 1.2.3.400: a count
            }
            return true;
        }
    }

    std::string scrub(const std::string &text, const std::string &homeDir)
    {
        std::string out = text;
        if (homeDir.size() >= 4)
        {
            // the caller's exact spelling first, so a home outside the conventional directories still goes
            std::string forward = homeDir, backward = homeDir;
            std::replace(forward.begin(), forward.end(), '\\', '/');
            std::replace(backward.begin(), backward.end(), '/', '\\');
            replaceAll(out, homeDir, "~");
            replaceAll(out, forward, "~");
            replaceAll(out, backward, "~");
        }
        out = std::regex_replace(out, kUserDir, "~");
        out = std::regex_replace(out, kCredential, "$1[redacted]");
        // addresses by hand: the hosted box stays, and a match that is not an address (a version) stays too
        std::string masked;
        masked.reserve(out.size());
        auto begin = std::sregex_iterator(out.begin(), out.end(), kIpv4);
        size_t copied = 0;
        for (auto it = begin; it != std::sregex_iterator(); ++it)
        {
            const std::smatch &m = *it;
            const size_t start = static_cast<size_t>(m.position(1));
            const size_t end = static_cast<size_t>(m.position(4) + m.length(4));
            const std::string address = out.substr(start, end - start);
            masked.append(out, copied, start - copied);
            masked += (isAddress(m) && address != kHostedIp) ? std::string("[ip]") : address;
            copied = end;
        }
        masked.append(out, copied, std::string::npos);
        return masked;
    }

    std::string glCapsLines(const std::string &logText)
    {
        const std::string lines = linesStartingWith(logText, {"INFO:     > Vendor:", "INFO:     > Renderer:", "INFO:     > Version:",
                                                              "INFO:     > GLSL:", "[gs-gl] initialised", "[gs-gl] depth mapping",
                                                              "[gs-gl] note", "[gs-gl] switching to the CPU rasterizer"});
        return lines.empty() ? std::string("no GL line in this log\n") : lines;
    }

    std::string crashRecord(const std::string &logText)
    {
        return linesStartingWith(logText, {"[crash]", "[terminate]", "[main] fatal", "[oom]", "[preflight] exit", "[gs-gl] FATAL"});
    }

    // Sprint 9 Goal 3 Task 7: the runner's one [knobs] line -- what was set and honoured, what was ignored without
    // --dev, what was refused -- so a report answers "it ignored my setting" by itself. The line holds no directory
    // (describe() cuts a Path to its file name) and versions.txt is scrubbed like every other entry.
    std::string knobsLine(const std::string &logText)
    {
        const std::string lines = linesStartingWith(logText, {"[knobs]"});
        return lines.empty() ? std::string("no [knobs] line in this log\n") : lines;
    }

    std::string joinClipped(const std::string &head, const std::string &tail, uint64_t omittedBytes)
    {
        return head + "\n[diagnostics] " + std::to_string(omittedBytes) + " bytes omitted here\n" + tail;
    }

    std::string clipLog(const std::string &logText, size_t headBytes, size_t tailBytes)
    {
        if (logText.size() <= headBytes + tailBytes)
            return logText;
        return joinClipped(logText.substr(0, headBytes), logText.substr(logText.size() - tailBytes),
                           logText.size() - headBytes - tailBytes);
    }

    std::string versionsText(const Inputs &in)
    {
        std::string out;
        out += "launcher: " + (in.version.empty() ? std::string("development build") : in.version) + "\n";
        out += "platform: " + (in.platform.empty() ? std::string("unknown") : in.platform) + "\n";
        out += "exit codes known: " + std::to_string(ExitCodes::kTableSize) + " (ps2x/exit_codes.h)\n";
        out += "knobs: " + knobsLine(in.logText);
        if (!in.haveLastExit)
        {
            out += "last exit: no run in this launcher session\n";
            return out;
        }
        const int code = ExitCodes::classify(in.lastExit);
        const ExitCodes::Entry *e = ExitCodes::find(code);
        out += "last exit: " + std::to_string(in.lastExit) + " -> " + std::to_string(code) + " " + (e ? e->slug : "unknown") + ": " +
               ExitCodes::describe(in.lastExit) + "\n";
        return out;
    }

    std::vector<ZipStore::Entry> entries(const Inputs &in)
    {
        std::vector<ZipStore::Entry> out;
        if (!in.logName.empty() || !in.logText.empty())
        {
            std::string name = "log/" + in.logName;
            if (in.logName.empty() || !ZipStore::nameAllowed(name) || in.logName.find('/') != std::string::npos)
                name = "log/run.log";
            out.push_back({name, scrub(clipLog(in.logText), in.homeDir)});
        }
        if (!in.configText.empty())
            out.push_back({"config.json", scrub(sanitizedConfigJson(in.configText), in.homeDir)});
        out.push_back({"gl_caps.txt", scrub(glCapsLines(in.logText), in.homeDir)});
        const std::string record = crashRecord(in.logText);
        if (!record.empty())
            out.push_back({"crash.txt", scrub(record, in.homeDir)});
        out.push_back({"versions.txt", scrub(versionsText(in), in.homeDir)});
        return out;
    }
}
