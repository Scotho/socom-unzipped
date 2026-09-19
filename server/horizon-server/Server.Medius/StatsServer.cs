// LOCAL FIX (socom_pc), Sprint 8 Goal 13: live server stats as JSON over HTTP, for s2u.scotho.com.
//
// The snapshot is built on the tick thread (the only thread that mutates the manager's lookups), at most once
// every PublishIntervalMs, and handed to the listener as one immutable string: the HTTP side never touches a
// live ClientObject or Game. Off unless medius.json sets StatsPrefix (e.g. "http://+:10080/"; "+" needs no
// privilege on Linux, use "http://127.0.0.1:10080/" on Windows). What is served is what any player in the lobby
// already sees -- names, games, counts -- and never an address, a session key or an account id.
using Newtonsoft.Json;
using RT.Common;
using Server.Medius.Models;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Text;
using System.Threading.Tasks;

namespace Server.Medius
{
    public static class StatsServer
    {
        const int PublishIntervalMs = 2000;

        static HttpListener _listener;
        static volatile string _json = "{\"status\":\"starting\"}";
        static DateTime _lastPublish = DateTime.MinValue;
        static readonly DateTime _startedUtc = DateTime.UtcNow;

        // Since-start counters, fed by Publish's own diffing so no message handler needs touching.
        static readonly HashSet<int> _seenGameIds = new HashSet<int>();
        static readonly HashSet<string> _seenPlayers = new HashSet<string>();
        static int _peakPlayers;
        static DateTime? _peakPlayersUtc;

        public static void Start(string prefix)
        {
            if (string.IsNullOrWhiteSpace(prefix) || _listener != null)
                return;

            try
            {
                _listener = new HttpListener();
                _listener.Prefixes.Add(prefix);
                _listener.Start();
                _ = Task.Run(ServeAsync);
                Program.LogStats($"Stats listening on {prefix}");
            }
            catch (Exception e)
            {
                _listener = null;
                Program.LogStats($"Stats NOT started on {prefix}: {e.Message}");
            }
        }

        static async Task ServeAsync()
        {
            while (_listener != null && _listener.IsListening)
            {
                HttpListenerContext ctx;
                try { ctx = await _listener.GetContextAsync(); }
                catch { break; }

                try
                {
                    var path = ctx.Request.Url?.AbsolutePath ?? "/";
                    if (ctx.Request.HttpMethod != "GET" || (path != "/stats" && path != "/stats.json"))
                    {
                        ctx.Response.StatusCode = 404;
                    }
                    else
                    {
                        var body = Encoding.UTF8.GetBytes(_json);
                        ctx.Response.StatusCode = 200;
                        ctx.Response.ContentType = "application/json; charset=utf-8";
                        ctx.Response.Headers["Cache-Control"] = "no-store";
                        ctx.Response.ContentLength64 = body.Length;
                        await ctx.Response.OutputStream.WriteAsync(body, 0, body.Length);
                    }
                }
                catch { /* a client that went away mid-reply */ }
                finally { try { ctx.Response.Close(); } catch { } }
            }
        }

        /// <summary>Called from the tick thread. A no-op when nothing listens or the interval has not passed.</summary>
        public static void Publish(MediusManager manager, int[] appIds, string serverName, string location)
        {
            if (_listener == null)
                return;
            var now = DateTime.UtcNow;
            if ((now - _lastPublish).TotalMilliseconds < PublishIntervalMs)
                return;
            _lastPublish = now;

            try
            {
                var clients = manager.GetAllClients().Where(c => c != null && c.IsLoggedIn && appIds.Contains(c.ApplicationId)).ToList();
                var games = manager.GetAllGames().Where(g => g != null && appIds.Contains(g.ApplicationId) && g.WorldStatus != MediusWorldStatus.WorldClosed).ToList();
                var channels = manager.GetAllChannels().Where(c => c != null && c.Type == ChannelType.Lobby).ToList();

                foreach (var g in games) _seenGameIds.Add(g.Id);
                foreach (var c in clients) if (!string.IsNullOrEmpty(c.AccountName)) _seenPlayers.Add(c.AccountName);
                if (clients.Count > _peakPlayers) { _peakPlayers = clients.Count; _peakPlayersUtc = now; }

                var snapshot = new
                {
                    status = "online",
                    server = serverName,
                    location,
                    generatedUtc = now.ToString("o"),
                    startedUtc = _startedUtc.ToString("o"),
                    uptimeSeconds = (long)(now - _startedUtc).TotalSeconds,
                    players = new
                    {
                        online = clients.Count,
                        inGame = clients.Count(c => c.IsInGame),
                        inLobby = clients.Count(c => !c.IsInGame),
                        names = clients.Select(c => c.AccountName).Where(n => !string.IsNullOrEmpty(n)).OrderBy(n => n).ToArray()
                    },
                    games = games.OrderBy(g => g.Id).Select(g => new
                    {
                        name = g.GameName,
                        host = g.Host?.AccountName,
                        players = g.PlayerCount,
                        maxPlayers = g.MaxPlayers,
                        level = g.GameLevel,
                        rules = g.RulesSet,
                        status = g.WorldStatus.ToString(),
                        hasPassword = !string.IsNullOrEmpty(g.GamePassword),
                        createdUtc = g.UtcTimeCreated.ToString("o"),
                        startedUtc = g.UtcTimeStarted?.ToString("o"),
                        playerNames = g.Clients.Where(x => x != null && x.InGame && x.Client != null).Select(x => x.Client.AccountName).ToArray()
                    }).ToArray(),
                    channels = channels.OrderBy(c => c.Id).Select(c => new { name = c.Name, players = c.PlayerCount, games = c.GameCount, maxPlayers = c.MaxPlayers }).ToArray(),
                    sinceStart = new
                    {
                        gamesCreated = _seenGameIds.Count,
                        distinctPlayers = _seenPlayers.Count,
                        peakPlayers = _peakPlayers,
                        peakPlayersUtc = _peakPlayersUtc?.ToString("o")
                    }
                };
                _json = JsonConvert.SerializeObject(snapshot);
            }
            catch (Exception e)
            {
                Program.LogStats($"Stats snapshot failed: {e.Message}");
            }
        }
    }
}
