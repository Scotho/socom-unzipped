using DotNetty.Common.Internal.Logging;
using Newtonsoft.Json;
using Server.NAT.Config;
using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;

namespace Server.NAT
{
    public class Program
    {
        private static string CONFIG_DIRECTIORY = "./";
        public static string CONFIG_FILE => Path.Combine(CONFIG_DIRECTIORY, "nat.json");

        public static ServerSettings Settings = new ServerSettings();
        public static NAT NATServer = new NAT();

        static readonly IInternalLogger Logger = InternalLoggerFactory.GetInstance<Program>();


        public static async Task Main(string[] args)
        {
            // get path to config directory from first argument
            if (args.Length > 0)
                CONFIG_DIRECTIORY = args[0];

            // 
            Initialize();

            Logger.Info($"Starting NAT on port {NATServer.Port}.");
            var task = NATServer.Start();
            Logger.Info($"NAT started.");

            await task;

            // LOCAL FIX (socom_pc): Start() completes as soon as the UDP socket is bound and DotNetty's event-loop
            // threads are background threads, so a standalone Server.NAT process exited immediately after binding
            // (it only stayed alive inside Server.Unified.Launcher). Keep the process alive until killed.
            await Task.Delay(Timeout.Infinite);
        }

        static void Initialize()
        {
            // 
            var serializerSettings = new JsonSerializerSettings()
            {
                MissingMemberHandling = MissingMemberHandling.Ignore
            };

            // Load settings
            if (File.Exists(CONFIG_FILE))
            {
                // Populate existing object
                JsonConvert.PopulateObject(File.ReadAllText(CONFIG_FILE), Settings, serializerSettings);
            }
            else
            {
                // Save defaults
                File.WriteAllText(CONFIG_FILE, JsonConvert.SerializeObject(Settings, Formatting.Indented));
            }
        }
    }
}
