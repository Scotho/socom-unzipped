namespace Server.Medius
{
    // Sprint 11 milestone S: a forwarded chat field is written fixed-width (Constants.*_MAXLEN) and the client
    // reads it as a C string, so what we forward must always leave room for the terminator. Kept as one small
    // class so it survives the next vendor bump of Horizon: call sites change, this does not.
    public static class ChatClamp
    {
        // Fit returns a single-byte string of at most fieldLen - 1 characters.
        //
        // Both halves of that matter. Server.Common.BinaryWriterExt -- vendored, so we work around it rather
        // than change it -- pads and truncates by CHARACTERS before it encodes, so a character that costs more
        // than one UTF-8 byte makes a fieldLen-character string longer than fieldLen bytes. The game's chat is
        // single byte anyway: its on-screen keyboard cannot produce anything outside printable ASCII, so no
        // legitimate line holds such a character and one that arrives is exactly the case we are clamping.
        // Mapping everything outside 0x20..0x7E to '?' first makes characters and bytes the same count, and
        // the character cut that follows then leaves room for the terminator in bytes as well.
        //
        // This also disposes of surrogate pairs: each half is outside the printable range and becomes its own
        // '?', so a cut can never split a pair.
        public static string Fit(string s, int fieldLen)
        {
            if (string.IsNullOrEmpty(s)) return "";

            int max = fieldLen - 1;
            if (max <= 0) return "";

            // Nothing to map and nothing to cut: hand back what we were given.
            bool asIs = s.Length <= max;
            if (asIs)
            {
                foreach (var c in s)
                {
                    if (IsOutsidePrintableAscii(c)) { asIs = false; break; }
                }
            }
            if (asIs) return s;

            int n = s.Length < max ? s.Length : max;
            var fitted = new char[n];
            for (int i = 0; i < n; ++i)
            {
                var c = s[i];
                fitted[i] = IsOutsidePrintableAscii(c) ? '?' : c;
            }
            return new string(fitted);
        }

        private static bool IsOutsidePrintableAscii(char c) => c < 0x20 || c > 0x7E;
    }
}
