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
        [Fact] public void AMultiByteTailIsNotSplit() { var s = new string('a', 62) + "é"; Assert.Equal(62, System.Text.Encoding.UTF8.GetByteCount(ChatClamp.Fit(s, 64))); }
    }
}
