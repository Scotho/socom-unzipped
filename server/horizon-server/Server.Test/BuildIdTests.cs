// LOCAL (socom_pc), Sprint 13 Task O3: the build id the stats JSON serves as "build" (/api/stats on the site).
using System.IO;
using Server.Medius;
using Xunit;

namespace Server.Test
{
    public class BuildIdTests
    {
        [Fact] public void ACommitIsKept() { Assert.Equal("b1f087b6a1c2", StatsServer.CleanBuildId("b1f087b6a1c2\n")); }
        [Fact] public void ADirtyMarkIsKept() { Assert.Equal("b1f087b6a1c2-dirty", StatsServer.CleanBuildId("  b1f087b6a1c2-dirty \r\n")); }
        [Fact] public void OnlyTheFirstLineCounts() { Assert.Equal("abc", StatsServer.CleanBuildId("abc\nsecond line")); }
        [Fact] public void EmptyIsRefused() { Assert.Null(StatsServer.CleanBuildId(" \n")); }
        [Fact] public void MarkupIsRefused() { Assert.Null(StatsServer.CleanBuildId("<script>")); }
        [Fact] public void TooLongIsRefused() { Assert.Null(StatsServer.CleanBuildId(new string('a', 65))); }

        [Fact]
        public void TheFirstFolderWithAGoodFileWins()
        {
            var root = Directory.CreateTempSubdirectory("buildid").FullName;
            try
            {
                var bad = Directory.CreateDirectory(Path.Combine(root, "bad")).FullName;
                var good = Directory.CreateDirectory(Path.Combine(root, "good")).FullName;
                var empty = Directory.CreateDirectory(Path.Combine(root, "empty")).FullName;
                File.WriteAllText(Path.Combine(bad, StatsServer.BuildIdFile), "not a build id!");
                File.WriteAllText(Path.Combine(good, StatsServer.BuildIdFile), "0123456789ab\n");
                Assert.Equal("0123456789ab", StatsServer.ReadBuildId(new[] { empty, bad, good }));
            }
            finally { Directory.Delete(root, true); }
        }

        [Fact]
        public void NoFileSaysUnknown()
        {
            var root = Directory.CreateTempSubdirectory("buildid").FullName;
            try { Assert.Equal("unknown", StatsServer.ReadBuildId(new[] { root, Path.Combine(root, "missing") })); }
            finally { Directory.Delete(root, true); }
        }
    }
}
