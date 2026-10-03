using System;
using System.Collections.Generic;
using System.Text;

namespace RT.Common
{
    public static class Constants
    {
        public const int MESSAGEID_MAXLEN = 21;
        public const int SESSIONKEY_MAXLEN = 17;
        public const int ACCOUNTNAME_MAXLEN = 32;
        public const int ACCOUNTSTATS_MAXLEN = 256;
        public const int CLANNAME_MAXLEN = 32;
        public const int CLANSTATS_MAXLEN = 256;
        public const int CLANMSG_MAXLEN = 200;
        public const int PASSWORD_MAXLEN = 32;
        public const int WORLDNAME_MAXLEN = 64;
        public const int WORLDPASSWORD_MAXLEN = 32;
        public const int LOBBYNAME_MAXLEN = 64;
        public const int LOBBYPASSWORD_MAXLEN = WORLDPASSWORD_MAXLEN;
        public const int GAMENAME_MAXLEN = 64;
        public const int GAMEPASSWORD_MAXLEN = 32;
        public const int GAMESTATS_MAXLEN = 256;
        public const int WINNINGTEAM_MAXLEN = 64;
        public const int DNASSIGNATURE_MAXLEN = 32;
        public const int ANNOUNCEMENT_MAXLEN = 1000;
        public const int MEDIUS_GENERIC_CHAT_FILTER_BYTES_LEN = 16;
        public const int MEDIUS_MESSAGE_MAXLEN = 512;
        public const int MEDIUS_UDP_MESSAGE_MAXLEN = 584;
        public const int NEWS_MAXLEN = 256;
        public const int POLICY_MAXLEN = 256;
        public const int PLAYERNAME_MAXLEN = 32;
        public const int APPNAME_MAXLEN = 32;
        public const int CHATMESSAGE_MAXLEN = 64;
        public const int BINARYMESSAGE_MAXLEN = 400;
        public const int IP_MAXLEN = 20;
        public const int MEDIUS_TOKEN_MAXSIZE = 8;
        public const int LOCATIONNAME_MAXLEN = 64;

        public const int UNIVERSENAME_MAXLEN = 128;
        public const int UNIVERSEDNS_MAXLEN = 128;
        public const int UNIVERSEDESCRIPTION_MAXLEN = 256;
        public const int UNIVERSE_BSP_MAXLEN = 8;
        public const int UNIVERSE_BSP_NAME_MAXLEN = 128;
        public const int UNIVERSE_EXTENDED_INFO_MAXLEN = 128;
        public const int UNIVERSE_SVO_URL_MAXLEN = 128;

        public const int LADDERSTATSWIDE_MAXLEN = 100;
        // LOCAL (socom_pc), #72: from PSHome-MultiServer's RT.Common/Constants.cs (GPL-3.0) at 8778e985e4; the Medius
        // 1.50 client's VersionServerResponse is MessageID + 56 bytes (0x4D), its UpdateLadderStats request 15 stats (0x58).
        public const int VERSIONSERVER_MAXLEN = 56;
        public const int LADDERSTATS_MAXLEN = 15;

        public const int NET_SESSION_KEY_LEN = 17;
        public const int NET_ACCESS_KEY_LEN = 17;
        public const int NET_MAX_NETADDRESS_LENGTH = 16;
        public const int NET_ADDRESS_LIST_COUNT = 2;

        public const int RSA_SIZE_DWORD = 16;

        public const int MGCL_MESSAGEID_MAXLEN = 21;
        public const int MGCL_SERVERVERSION_MAXLEN = 16;
        public const int MGCL_GAMENAME_MAXLEN = 64;
        public const int MGCL_GAMESTATS_MAXLEN = 256;
        public const int MGCL_GAMEPASSWORD_MAXLEN = 32;
        public const int MGCL_SERVERIP_MAXLEN = 20;
        public const int MGCL_ACCESSKEY_MAXLEN = 17;
        public const int MGCL_SESSIONKEY_MAXLEN = 17;

        public const int MEDIUS_FILE_MAX_DOWNLOAD_DATA_SIZE = 464;
        public const int MEDIUS_FILE_MAX_FILENAME_LENGTH = 128;
        public const int MEDIUS_FILE_CHECKSUM_NUMBYTES = 16;
        public const int MEDIUS_FILE_MAX_DESCRIPTION_LENGTH = 256;

        public const int DME_FRAGMENT_MAX_PAYLOAD_SIZE = 484;
        public const int DME_VERSION_LENGTH = 16;

        public const int BUFFER_SIZE = 1500;
    }
}
