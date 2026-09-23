namespace Server.Medius
{
    // Sprint 11 milestone S: a forwarded chat field is written fixed-width (Constants.*_MAXLEN) and the client
    // reads it as a C string, so what we forward must always leave room for the terminator. Kept as one small
    // class so it survives the next vendor bump of Horizon: call sites change, this does not.
    public static class ChatClamp
    {
        public static string Fit(string s, int fieldLen)
        {
            if (string.IsNullOrEmpty(s)) return "";
            var utf8 = System.Text.Encoding.UTF8;
            if (utf8.GetByteCount(s) <= fieldLen - 1) return s;
            // Walk back by characters until the encoded length fits fieldLen - 1 bytes.
            int n = s.Length;
            while (n > 0 && utf8.GetByteCount(s, 0, n) > fieldLen - 1) --n;
            return s.Substring(0, n);
        }
    }
}
