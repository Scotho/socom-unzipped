using Org.BouncyCastle.Crypto.Generators;
using Org.BouncyCastle.Crypto.Parameters;
using Org.BouncyCastle.Math;
using Org.BouncyCastle.Security;
using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;

namespace RT.Cryptography
{
    public class PS2CipherFactory : ICipherFactory
    {
        private static Random RNG = new Random();

        public ICipher CreateNew(CipherContext context)
        {
            if (context == CipherContext.RSA_AUTH)
                return CreateAsym();

            return CreateSym(context);
        }

        public ICipher CreateNew(CipherContext context, byte[] publicKey)
        {
            if (context == CipherContext.RSA_AUTH)
                return CreateAsymFromPublicKey(publicKey);

            return CreateSymFromPublicKey(context, publicKey);
        }

        public ICipher CreateNew(RsaKeyPair rsaKeyPair)
        {
            return rsaKeyPair?.ToPS2();
        }

        private ICipher CreateSym(CipherContext context)
        {
            // generate random series of bytes
            var b = new byte[0x40];
            RNG.NextBytes(b);
            // The client session key travels RSA-encrypted under the client's 512-bit modulus N.
            // RSA only round-trips plaintexts < N, and a uniformly random 512-bit key is >= N with
            // probability (2^512 - N) / 2^512 (about 8% for the SOCOM II client's key), which then
            // broke every message after CRYPTKEY_PEER ("Unable to decrypt RT_MSG_CLIENT_CONNECT_TCP").
            // Keep the key below 2^511 whichever end is the most significant byte.
            b[0] &= 0x7F;
            b[0x3F] &= 0x7F;

            return new PS2_RC4(b, context);
        }

        private ICipher CreateSymFromPublicKey(CipherContext context, byte[] publicKey)
        {
            return new PS2_RC4(publicKey, context);
        }

        private ICipher CreateAsym()
        {
            // generate key
            RsaKeyPairGenerator rsa = new RsaKeyPairGenerator();
            BigInteger e = new BigInteger("17");

            var param = new RsaKeyGenerationParameters(
                e,
                new SecureRandom(),
                512,
                5
                );
            rsa.Init(param);
            var keypair = rsa.GenerateKeyPair();

            // pull modulus and private exp
            var n = (BigInteger)keypair.Public.GetType().GetProperty("Modulus").GetValue(keypair.Public);
            var d = (BigInteger)keypair.Private.GetType().GetProperty("Exponent").GetValue(keypair.Private);

            // 
            return new PS2_RSA(n, e, d);
        }

        private ICipher CreateAsymFromPublicKey(byte[] publicKey)
        {
            BigInteger e = new BigInteger("17");
            return new PS2_RSA(new BigInteger(1, publicKey), e, e);
        }
    }
}
