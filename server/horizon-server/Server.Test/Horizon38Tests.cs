// LOCAL (socom_pc), LATER 86: guards for the port of upstream Horizon-Private-Server/horizon-server PR #38
// (e9aeb4b, "Cryptography + DME improvements"): CipherService's table is concurrent, and the DME's per-client
// UDP servers share one static event loop group.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using DotNetty.Transport.Channels;
using RT.Cryptography;
using Xunit;

namespace Server.Test
{
    public class Horizon38Tests
    {
        sealed class FakeCipher : ICipher
        {
            public FakeCipher(CipherContext context) { Context = context; }
            public CipherContext Context { get; }
            public bool Decrypt(byte[] input, byte[] hash, out byte[] plain) { plain = input; return true; }
            public bool Encrypt(byte[] input, out byte[] cipher, out byte[] hash) { cipher = input; hash = new byte[4]; return true; }
            public void Hash(byte[] input, out byte[] hash) { hash = new byte[4]; }
            public bool IsHashValid(byte[] hash) { return true; }
            public byte[] GetPublicKey() { return new byte[0]; }
        }

        // With the plain Dictionary, ContainsKey-then-Add races (ArgumentException: the key was already added) and
        // concurrent inserts can lose entries or trip .NET's concurrent-use detection. Not deterministic: a
        // regression guard that reds with high probability over the iterations.
        [Fact]
        public async Task TheCipherTableSurvivesConcurrentGetsAndSets()
        {
            var contexts = (CipherContext[])Enum.GetValues(typeof(CipherContext));
            const int Threads = 8, Iterations = 2000;
            var errors = new List<Exception>();

            for (int it = 0; it < Iterations && errors.Count == 0; ++it)
            {
                var svc = new CipherService(null);
                using var start = new Barrier(Threads);
                var tasks = Enumerable.Range(0, Threads).Select(t => Task.Factory.StartNew(() =>
                {
                    try
                    {
                        start.SignalAndWait();
                        for (int k = 0; k < contexts.Length; ++k)
                        {
                            var ctx = contexts[(k + t) % contexts.Length];
                            svc.SetCipher(ctx, new FakeCipher(ctx));
                            svc.HasKey(contexts[(k + t + 1) % contexts.Length]);
                            svc.Encrypt(ctx, new byte[] { 1 }, out _, out _);
                        }
                    }
                    catch (Exception e) { lock (errors) errors.Add(e); }
                }, TaskCreationOptions.LongRunning)).ToArray();

                await Task.WhenAll(tasks).WaitAsync(TimeSpan.FromSeconds(30)); // a TimeoutException: the table hung
                if (errors.Count == 0)
                    foreach (var ctx in contexts)
                        Assert.True(svc.HasKey(ctx), $"iteration {it}: {ctx} was lost");
            }

            Assert.Empty(errors);
        }

        // Observable without sockets: the group is a static, read-only field, so every UdpServer construction
        // sees the same instance (upstream made one per Start and shut it down per Stop).
        [Fact]
        public void TheDmeUdpServersShareOneEventLoopGroup()
        {
            var field = typeof(Server.Dme.UdpServer).GetField("_workerGroup",
                BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance);
            Assert.NotNull(field);
            Assert.True(field.IsStatic, "_workerGroup is per instance");
            Assert.True(field.IsInitOnly, "_workerGroup can be replaced");
            var first = field.GetValue(null) as IEventLoopGroup;
            Assert.NotNull(first);
            Assert.Same(first, field.GetValue(null));
        }
    }
}
