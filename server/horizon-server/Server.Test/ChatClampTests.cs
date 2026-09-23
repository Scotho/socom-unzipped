using Server.Medius;
using Xunit;

namespace Server.Test
{
    public class ChatClampTests
    {
        [Fact] public void A64ByteMessageIsCutTo63() { Assert.Equal(63, ChatClamp.Fit(new string('x', 64), 64).Length); }
        [Fact] public void AShortMessageIsUnchanged() { Assert.Equal("gg", ChatClamp.Fit("gg", 64)); }
        [Fact] public void A63ByteMessageIsUnchanged() { var s = new string('y', 63); Assert.Same(s, ChatClamp.Fit(s, 64)); }
        [Fact] public void NullBecomesEmpty() { Assert.Equal("", ChatClamp.Fit(null, 64)); }

        // The fixed-width writer pads and truncates by characters, so what we forward has to be single byte:
        // one character must cost exactly one byte, and there must be at most fieldLen - 1 of them.
        [Fact] public void AnAccentedLineIsSingleByte() { AssertFitsTheField(ChatClamp.Fit("héllo", 64)); }
        [Fact] public void ThreeByteCharactersAreSingleByte() { AssertFitsTheField(ChatClamp.Fit(new string('中', 21), 64)); }
        [Fact] public void AnEmojiSurrogatePairIsSingleByte() { AssertFitsTheField(ChatClamp.Fit("gg 😀 wp", 64)); }

        static void AssertFitsTheField(string result)
        {
            Assert.Equal(result.Length, System.Text.Encoding.UTF8.GetByteCount(result));
            Assert.True(result.Length <= 63, $"expected at most 63 characters, got {result.Length}");
            Assert.All(result, c => Assert.True(c <= 0x7F, $"expected only single-byte characters, got U+{(int)c:X4}"));
        }
    }
}
