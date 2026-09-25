#include "launcher/bug_report.h"

#include "launcher/diagnostics.h"
#include "ps2x/exit_codes.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace launcher::bugreport
{
    namespace
    {
        // ---- UTF-8 ------------------------------------------------------------------------------------------
        // The length of the valid UTF-8 sequence at s[i], or 0 when the byte there does not start one
        // (overlongs, surrogates and anything past U+10FFFF are not valid).
        size_t utf8SequenceAt(const std::string &s, size_t i)
        {
            const auto b = [&](size_t k) { return static_cast<unsigned char>(s[k]); };
            const unsigned char c = b(i);
            if (c < 0x80)
                return 1;
            size_t n = 0;
            if (c >= 0xC2 && c <= 0xDF)
                n = 2;
            else if (c >= 0xE0 && c <= 0xEF)
                n = 3;
            else if (c >= 0xF0 && c <= 0xF4)
                n = 4;
            else
                return 0;
            if (i + n > s.size())
                return 0;
            for (size_t k = 1; k < n; ++k)
                if ((b(i + k) & 0xC0) != 0x80)
                    return 0;
            if (c == 0xE0 && b(i + 1) < 0xA0)
                return 0;
            if (c == 0xED && b(i + 1) > 0x9F)
                return 0;
            if (c == 0xF0 && b(i + 1) < 0x90)
                return 0;
            if (c == 0xF4 && b(i + 1) > 0x8F)
                return 0;
            return n;
        }

        // The longest prefix of `s` with at most `units` UTF-16 units, never cutting a character.
        std::string cutToUnits(const std::string &s, size_t units)
        {
            size_t used = 0, i = 0;
            while (i < s.size())
            {
                size_t n = utf8SequenceAt(s, i);
                const size_t cost = n == 4 ? 2 : 1;
                if (n == 0)
                    n = 1;
                if (used + cost > units)
                    break;
                used += cost;
                i += n;
            }
            return s.substr(0, i);
        }

        std::string trim(const std::string &s)
        {
            size_t a = 0, b = s.size();
            while (a < b && std::isspace(static_cast<unsigned char>(s[a])))
                ++a;
            while (b > a && std::isspace(static_cast<unsigned char>(s[b - 1])))
                --b;
            return s.substr(a, b - a);
        }

        std::string upper(std::string s)
        {
            for (char &c : s)
                c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
            return s;
        }

        void appendUtf8(std::string &out, unsigned code)
        {
            if (code < 0x80)
                out.push_back(static_cast<char>(code));
            else if (code < 0x800)
            {
                out.push_back(static_cast<char>(0xC0 | (code >> 6)));
                out.push_back(static_cast<char>(0x80 | (code & 0x3F)));
            }
            else if (code < 0x10000)
            {
                out.push_back(static_cast<char>(0xE0 | (code >> 12)));
                out.push_back(static_cast<char>(0x80 | ((code >> 6) & 0x3F)));
                out.push_back(static_cast<char>(0x80 | (code & 0x3F)));
            }
            else
            {
                out.push_back(static_cast<char>(0xF0 | (code >> 18)));
                out.push_back(static_cast<char>(0x80 | ((code >> 12) & 0x3F)));
                out.push_back(static_cast<char>(0x80 | ((code >> 6) & 0x3F)));
                out.push_back(static_cast<char>(0x80 | (code & 0x3F)));
            }
        }

        // ---- a small tolerant JSON reader --------------------------------------------------------------------
        // launcher_config.cpp's reader is a flat one for config.json (a private Parser that fills a Config, no
        // nesting kept, \u above ASCII dropped). Replies and /api/stats need nested objects, arrays and real
        // \u escapes, so this is a second, DOM-shaped one; it trusts nothing and its depth is bounded.
        struct Value
        {
            enum class Type
            {
                Null,
                Bool,
                Number,
                String,
                Array,
                Object
            };
            Type type = Type::Null;
            bool boolean = false;
            double number = 0.0;
            std::string string;
            std::vector<Value> items;
            // An object's members as two parallel lists, NOT a vector of pair<string, Value>: Value is still
            // incomplete here, a vector of an incomplete type is allowed (C++17) and a pair holding one is
            // not. libc++ let the pair through and libstdc++ 14 refused it -- the Linux CI build, 2026-09-19.
            std::vector<std::string> keys;
            std::vector<Value> values;

            const Value *get(const char *key) const;
        };

        const Value *Value::get(const char *key) const
        {
            if (type != Type::Object)
                return nullptr;
            for (size_t k = 0; k < keys.size() && k < values.size(); ++k)
                if (keys[k] == key)
                    return &values[k];
            return nullptr;
        }

        struct Reader
        {
            const std::string &s;
            size_t i = 0;
            static constexpr int kMaxDepth = 32;
            explicit Reader(const std::string &text) : s(text) {}

            void ws()
            {
                while (i < s.size() && (s[i] == ' ' || s[i] == '\t' || s[i] == '\n' || s[i] == '\r'))
                    ++i;
            }
            bool hex4(unsigned &out)
            {
                if (i + 4 > s.size())
                    return false;
                out = 0;
                for (int k = 0; k < 4; ++k)
                {
                    const char c = s[i++];
                    out <<= 4;
                    if (c >= '0' && c <= '9')
                        out |= static_cast<unsigned>(c - '0');
                    else if (c >= 'a' && c <= 'f')
                        out |= static_cast<unsigned>(c - 'a' + 10);
                    else if (c >= 'A' && c <= 'F')
                        out |= static_cast<unsigned>(c - 'A' + 10);
                    else
                        return false;
                }
                return true;
            }
            bool string(std::string &out)
            {
                if (i >= s.size() || s[i] != '"')
                    return false;
                ++i;
                out.clear();
                while (i < s.size())
                {
                    const char c = s[i++];
                    if (c == '"')
                        return true;
                    if (c != '\\')
                    {
                        out.push_back(c);
                        continue;
                    }
                    if (i >= s.size())
                        return false;
                    const char e = s[i++];
                    switch (e)
                    {
                    case '"': out.push_back('"'); break;
                    case '\\': out.push_back('\\'); break;
                    case '/': out.push_back('/'); break;
                    case 'n': out.push_back('\n'); break;
                    case 'r': out.push_back('\r'); break;
                    case 't': out.push_back('\t'); break;
                    case 'b': out.push_back('\b'); break;
                    case 'f': out.push_back('\f'); break;
                    case 'u':
                    {
                        unsigned code = 0;
                        if (!hex4(code))
                            return false;
                        if (code >= 0xD800 && code <= 0xDBFF && i + 1 < s.size() && s[i] == '\\' && s[i + 1] == 'u')
                        {
                            const size_t mark = i;
                            unsigned low = 0;
                            i += 2;
                            if (hex4(low) && low >= 0xDC00 && low <= 0xDFFF)
                                code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00);
                            else
                                i = mark;
                        }
                        if (code >= 0xD800 && code <= 0xDFFF)
                            code = 0xFFFD;   // a lone surrogate
                        appendUtf8(out, code);
                        break;
                    }
                    default: return false;
                    }
                }
                return false;
            }
            bool value(Value &out, int depth)
            {
                if (depth > kMaxDepth)
                    return false;
                ws();
                if (i >= s.size())
                    return false;
                const char c = s[i];
                if (c == '"')
                {
                    out.type = Value::Type::String;
                    return string(out.string);
                }
                if (c == '{')
                {
                    out.type = Value::Type::Object;
                    ++i;
                    ws();
                    if (i < s.size() && s[i] == '}')
                        return ++i, true;
                    for (;;)
                    {
                        ws();
                        std::string key;
                        if (!string(key))
                            return false;
                        ws();
                        if (i >= s.size() || s[i] != ':')
                            return false;
                        ++i;
                        Value member;
                        if (!value(member, depth + 1))
                            return false;
                        out.keys.push_back(std::move(key));
                        out.values.push_back(std::move(member));
                        ws();
                        if (i < s.size() && s[i] == ',')
                        {
                            ++i;
                            continue;
                        }
                        if (i < s.size() && s[i] == '}')
                            return ++i, true;
                        return false;
                    }
                }
                if (c == '[')
                {
                    out.type = Value::Type::Array;
                    ++i;
                    ws();
                    if (i < s.size() && s[i] == ']')
                        return ++i, true;
                    for (;;)
                    {
                        Value item;
                        if (!value(item, depth + 1))
                            return false;
                        out.items.push_back(std::move(item));
                        ws();
                        if (i < s.size() && s[i] == ',')
                        {
                            ++i;
                            continue;
                        }
                        if (i < s.size() && s[i] == ']')
                            return ++i, true;
                        return false;
                    }
                }
                if (s.compare(i, 4, "true") == 0)
                {
                    out.type = Value::Type::Bool;
                    out.boolean = true;
                    i += 4;
                    return true;
                }
                if (s.compare(i, 5, "false") == 0)
                {
                    out.type = Value::Type::Bool;
                    i += 5;
                    return true;
                }
                if (s.compare(i, 4, "null") == 0)
                {
                    i += 4;
                    return true;
                }
                const size_t start = i;
                while (i < s.size() && (std::isdigit(static_cast<unsigned char>(s[i])) || s[i] == '-' || s[i] == '+' ||
                                        s[i] == '.' || s[i] == 'e' || s[i] == 'E'))
                    ++i;
                if (i == start || i - start > 40)
                    return false;
                char *end = nullptr;
                const std::string token = s.substr(start, i - start);
                out.number = std::strtod(token.c_str(), &end);
                if (end == nullptr || *end != '\0')
                    return false;
                out.type = Value::Type::Number;
                return true;
            }
        };

        // The whole text as one JSON value, nothing but whitespace after it.
        bool parseJson(const std::string &text, Value &out)
        {
            Reader r(text);
            if (!r.value(out, 0))
                return false;
            r.ws();
            return r.i == text.size();
        }

        // stats.ts num(): a finite number >= 0, floored; anything else is 0.
        long long count(const Value *v)
        {
            if (v == nullptr || v->type != Value::Type::Number || !std::isfinite(v->number) || v->number < 0.0)
                return 0;
            return v->number > 9.0e15 ? 9000000000000000LL : static_cast<long long>(std::floor(v->number));
        }

        // report.ts: /^BR-\d{8}-[0-9a-f]{6}$/
        bool looksLikeOurId(const std::string &id)
        {
            if (id.size() != 18 || id.compare(0, 3, "BR-") != 0 || id[11] != '-')
                return false;
            for (size_t k = 3; k < 11; ++k)
                if (!std::isdigit(static_cast<unsigned char>(id[k])))
                    return false;
            for (size_t k = 12; k < 18; ++k)
                if (!(std::isdigit(static_cast<unsigned char>(id[k])) || (id[k] >= 'a' && id[k] <= 'f')))
                    return false;
            return true;
        }

        std::string fileNameOf(const std::string &path)
        {
            const size_t slash = path.find_last_of("/\\");
            return slash == std::string::npos ? path : path.substr(slash + 1);
        }

        // "INFO:     > Renderer: NVIDIA ..." out of diagnostics::glCapsLines -> "NVIDIA ..."; "" when there is none.
        std::string rendererIn(const std::string &logText)
        {
            const std::string caps = diagnostics::glCapsLines(logText);
            const char *key = "> Renderer:";
            const size_t at = caps.find(key);
            if (at == std::string::npos)
                return {};
            size_t end = caps.find('\n', at);
            if (end == std::string::npos)
                end = caps.size();
            return trim(caps.substr(at + std::strlen(key), end - at - std::strlen(key)));
        }

        std::string assemble(const Form &form, const Inputs &in, const std::vector<std::pair<std::string, std::string>> &context,
                             const std::string &log)
        {
            std::string j = "{";
            j += "\"title\":" + jsonString(trim(form.title));
            j += ",\"description\":" + jsonString(trim(form.description));
            j += ",\"contact\":" + jsonString(cutToUnits(trim(form.contact), kContactMax));
            j += ",\"source\":\"launcher\"";
            j += ",\"version\":" + jsonString(cutToUnits(diagnostics::scrub(in.version, in.homeDir), kShortMax));
            j += ",\"platform\":" + jsonString(cutToUnits(in.platform, kShortMax));
            j += ",\"context\":{";
            for (size_t k = 0; k < context.size(); ++k)
                j += (k ? "," : "") + jsonString(context[k].first) + ":" + jsonString(context[k].second);
            j += "}";
            if (!log.empty())
                j += ",\"log\":" + jsonString(log);
            // The honeypot: a literal, reachable by no input. A real form leaves it empty.
            j += ",\"website\":\"\"";
            if (form.test)
                j += ",\"test\":true";
            j += "}";
            return j;
        }
    }

    size_t utf16Length(const std::string &utf8)
    {
        size_t units = 0, i = 0;
        while (i < utf8.size())
        {
            const size_t n = utf8SequenceAt(utf8, i);
            units += n == 4 ? 2 : 1;
            i += n == 0 ? 1 : n;
        }
        return units;
    }

    std::string checkForm(const Form &form)
    {
        const size_t title = utf16Length(trim(form.title));
        const size_t description = utf16Length(trim(form.description));
        if (title < kTitleMin || title > kTitleMax)
            return "TITLE: 4 TO 120 CHARACTERS.";
        if (description < kDescriptionMin)
            return "WHAT HAPPENED: AT LEAST 10 CHARACTERS.";
        if (description > kDescriptionMax)
            return "WHAT HAPPENED: AT MOST 4000 CHARACTERS.";
        return {};
    }

    std::string fieldOf(const std::string &message)
    {
        const size_t colon = message.find(':');
        if (colon == std::string::npos)
            return {};
        const std::string head = upper(trim(message.substr(0, colon)));
        if (head == "TITLE")
            return "title";
        if (head == "WHAT HAPPENED" || head == "DESCRIPTION")
            return "description";
        if (head == "CONTACT")
            return "contact";
        if (head == "LOG")
            return "log";
        return {};
    }

    std::string jsonString(const std::string &utf8)
    {
        std::string out = "\"";
        size_t i = 0;
        while (i < utf8.size())
        {
            const unsigned char c = static_cast<unsigned char>(utf8[i]);
            if (c < 0x80)
            {
                switch (c)
                {
                case '"': out += "\\\""; break;
                case '\\': out += "\\\\"; break;
                case '\n': out += "\\n"; break;
                case '\r': out += "\\r"; break;
                case '\t': out += "\\t"; break;
                default:
                    if (c < 0x20)
                    {
                        char buf[8];
                        std::snprintf(buf, sizeof(buf), "\\u%04x", static_cast<unsigned>(c));
                        out += buf;
                    }
                    else
                        out.push_back(static_cast<char>(c));
                    break;
                }
                ++i;
                continue;
            }
            const size_t n = utf8SequenceAt(utf8, i);
            if (n == 0)
            {
                out += "\xEF\xBF\xBD";
                ++i;
                continue;
            }
            out.append(utf8, i, n);
            i += n;
        }
        out.push_back('"');
        return out;
    }

    std::string logAttachment(const std::string &logText, const std::string &homeDir, const std::string &isoPath, size_t maxBytes)
    {
        std::string whole = diagnostics::clipLog(logText);
        // The disc's folder first (it is usually under the home directory, and must go while it still matches).
        const size_t slash = isoPath.find_last_of("/\\");
        if (slash != std::string::npos && slash >= 2)
        {
            std::string asTyped = isoPath.substr(0, slash + 1), forward = asTyped, backward = asTyped;
            std::replace(forward.begin(), forward.end(), '\\', '/');
            std::replace(backward.begin(), backward.end(), '/', '\\');
            for (const std::string &dir : {asTyped, forward, backward})
                for (size_t at = whole.find(dir); at != std::string::npos; at = whole.find(dir, at))
                    whole.replace(at, dir.size(), "");
        }
        whole = diagnostics::scrub(whole, homeDir);
        if (whole.size() <= maxBytes)
            return whole;
        size_t start = whole.size() - maxBytes;
        // On a line boundary when there is one to be had; otherwise on a character.
        if (whole[start - 1] != '\n')
        {
            const size_t nl = whole.find('\n', start);
            if (nl != std::string::npos && nl + 1 < whole.size())
                start = nl + 1;
        }
        while (start < whole.size() && (static_cast<unsigned char>(whole[start]) & 0xC0) == 0x80)
            ++start;
        return whole.substr(start);
    }

    std::vector<std::pair<std::string, std::string>> contextPairs(const Config &config, const Inputs &in)
    {
        std::vector<std::pair<std::string, std::string>> out;
        auto add = [&](const char *key, const std::string &value)
        {
            if (value.empty() || out.size() >= kContextPairs)
                return;
            out.emplace_back(key, cutToUnits(diagnostics::scrub(value, in.homeDir), kContextValueMax));
        };
        // The allowlist. A field that is not named here is not sent, whatever a later build adds to Config.
        add("serverPreset", config.serverPreset);
        add("server", effectiveServer(config));
        add("gsScale", std::to_string(config.gsScale));
        add("windowSize", config.windowSize);
        add("profile", config.profile);
        add("crouchShortcut", config.crouchShortcut);
        add("iso", fileNameOf(config.isoPath));   // diagnostics::sanitizedConfigJson's rule: the name, never the directory
        if (in.haveLastExit)
        {
            const int code = ExitCodes::classify(in.lastExit);
            const ExitCodes::Entry *e = ExitCodes::find(code);
            add("lastExit", std::to_string(code) + " " + (e ? e->slug : "unknown"));
            add("lastExitMeaning", ExitCodes::describe(in.lastExit));
        }
        add("glRenderer", rendererIn(in.logText));
        return out;
    }

    Payload build(const Config &config, const Form &form, const Inputs &in)
    {
        Payload p;
        const auto context = contextPairs(config, in);
        for (const auto &kv : context)
            p.contextKeys.push_back(kv.first);

        std::string log = form.attachLog ? logAttachment(in.logText, in.homeDir, config.isoPath) : std::string();
        p.json = assemble(form, in, context, log);
        // The 96 KB guard: escaping can double a log (every backslash, every newline), so the body is
        // measured as it will be sent and the log gives way from its head, a line at a time. The
        // description is the player's own words and is never cut.
        while (p.json.size() > kBodyMax && !log.empty())
        {
            // Whole lines off the head, counted as they are escaped, until the excess is gone.
            const size_t excess = p.json.size() - kBodyMax;
            size_t dropped = 0, pos = 0;
            while (pos < log.size() && dropped < excess)
            {
                const size_t nl = log.find('\n', pos);
                const size_t end = nl == std::string::npos ? log.size() : nl + 1;
                dropped += jsonString(log.substr(pos, end - pos)).size() - 2;
                pos = end;
            }
            log.erase(0, pos);
            p.json = assemble(form, in, context, log);
        }
        p.logBytes = log.size();
        return p;
    }

    std::string previewLine(const Payload &payload, const Form &form)
    {
        (void)form;
        std::string line = "SEND will send " + std::to_string(payload.json.size()) +
                           " bytes: your title, what happened and contact; the launcher's version and platform; ";
        if (payload.contextKeys.empty())
            line += "no settings; ";
        else
        {
            line += "these settings (";
            for (size_t k = 0; k < payload.contextKeys.size(); ++k)
                line += (k ? ", " : "") + payload.contextKeys[k];
            line += "); ";
        }
        line += payload.logBytes == 0 ? std::string("no log.")
                                      : std::to_string(payload.logBytes) + " bytes of the last run's log, your home folder's name removed.";
        return line;
    }

    Reply parseReply(int status, const std::string &body, int retryAfterSeconds)
    {
        Reply r;
        Value v;
        const bool json = parseJson(body, v) && v.type == Value::Type::Object;
        if (status == 201 && json)
        {
            const Value *ok = v.get("ok");
            if (ok != nullptr && ok->type == Value::Type::Bool && ok->boolean)
            {
                r.kind = Reply::Kind::Sent;
                const Value *id = v.get("id");
                if (id != nullptr && id->type == Value::Type::String && looksLikeOurId(id->string))
                    r.id = upper(id->string);
                r.text = r.id.empty() ? std::string("REPORT RECEIVED.") : "REPORT RECEIVED. REFERENCE " + r.id + ".";
                return r;
            }
        }
        if (status == 429)
        {
            r.kind = Reply::Kind::RateLimited;
            r.retryAfterSeconds = retryAfterSeconds > 0 ? retryAfterSeconds : 0;
            if (r.retryAfterSeconds > 0)
            {
                const int minutes = (r.retryAfterSeconds + 59) / 60;
                r.text = "NOT SENT. TOO MANY REPORTS FROM HERE; TRY AGAIN IN " + std::to_string(minutes) +
                         (minutes == 1 ? " MINUTE." : " MINUTES.");
            }
            else
                r.text = "NOT SENT. TOO MANY REPORTS FROM HERE; TRY AGAIN IN AN HOUR.";
            return r;
        }
        if (status == 400 && json)
        {
            const Value *error = v.get("error");
            if (error != nullptr && error->type == Value::Type::String)
            {
                r.kind = Reply::Kind::FieldError;
                r.field = fieldOf(error->string);
                r.text = "NOT SENT. " + upper(cutToUnits(error->string, 80));
                return r;
            }
        }
        r.kind = Reply::Kind::Failed;
        r.text = status == 413 ? "NOT SENT. THE REPORT WAS TOO LARGE; YOUR TEXT IS STILL HERE."
                               : "NOT SENT. THE REPORT SERVICE DID NOT ANSWER; YOUR TEXT IS STILL HERE.";
        return r;
    }

    std::string savedLocallyLine(const std::string &path)
    {
        return "SAVED ON THIS MACHINE INSTEAD: " + path;
    }

    std::string githubLine(const std::string &referenceId)
    {
        if (referenceId.empty())
            return {};
        return kGithubIssueLine;
    }

    std::string statusLine(const std::string &statsJson)
    {
        Value v;
        if (!parseJson(statsJson, v) || v.type != Value::Type::Object)
            return {};
        const Value *status = v.get("status");
        const Value *players = v.get("players");
        const bool online = status != nullptr && status->type == Value::Type::String && status->string == "online" &&
                            players != nullptr && players->type == Value::Type::Object;
        if (!online)
            return "SOCOM Unzipped: offline";
        const long long n = count(players->get("online"));
        long long games = 0;
        if (const Value *list = v.get("games"); list != nullptr && list->type == Value::Type::Array)
            for (const Value &g : list->items)
                if (g.type == Value::Type::Object && games < 32)   // stats.ts MAX_GAMES
                    ++games;
        return "SOCOM Unzipped: online, " + std::to_string(n) + (n == 1 ? " player, " : " players, ") +
               std::to_string(games) + (games == 1 ? " game" : " games");
    }

    std::string apiBase(const char *envValue)
    {
        if (envValue == nullptr)
            return kDefaultApiBase;
        std::string v = envValue;
        if (!v.empty() && v.back() == '/')
            v.pop_back();
        for (const char *prefix : {"http://127.0.0.1:", "http://localhost:"})
        {
            const size_t n = std::strlen(prefix);
            if (v.compare(0, n, prefix) != 0)
                continue;
            const std::string port = v.substr(n);
            if (port.empty() || port.size() > 5)
                break;
            bool digits = true;
            for (char c : port)
                digits = digits && std::isdigit(static_cast<unsigned char>(c));
            if (digits && std::atoi(port.c_str()) > 0 && std::atoi(port.c_str()) <= 65535)
                return v;
            break;
        }
        return kDefaultApiBase;
    }

    bool formFromJson(const std::string &text, Form &out)
    {
        Value v;
        if (!parseJson(text, v) || v.type != Value::Type::Object)
            return false;
        auto str = [&](const char *key)
        {
            const Value *m = v.get(key);
            return m != nullptr && m->type == Value::Type::String ? m->string : std::string();
        };
        auto flag = [&](const char *key, bool fallback)
        {
            const Value *m = v.get(key);
            return m != nullptr && m->type == Value::Type::Bool ? m->boolean : fallback;
        };
        out.title = str("title");
        out.description = str("description");
        out.contact = str("contact");
        out.attachLog = flag("attachLog", false);
        out.test = flag("test", true);   // the headless mode is for proofs
        return true;
    }

    std::string savedFileName(const std::string &stamp)
    {
        return "bugreport_" + stamp + ".json";
    }
}
