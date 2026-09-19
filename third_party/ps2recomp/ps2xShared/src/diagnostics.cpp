#include "launcher/diagnostics.h"

#include "launcher/launcher_config.h"
#include "ps2x/exit_codes.h"

#include <algorithm>
#include <initializer_list>

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
        return toJson(config);
    }

    std::string scrub(const std::string &text, const std::string &homeDir)
    {
        if (homeDir.size() < 4)
            return text;
        std::string out = text;
        std::string forward = homeDir, backward = homeDir;
        std::replace(forward.begin(), forward.end(), '\\', '/');
        std::replace(backward.begin(), backward.end(), '/', '\\');
        replaceAll(out, homeDir, "~");
        replaceAll(out, forward, "~");
        replaceAll(out, backward, "~");
        return out;
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
