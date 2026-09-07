using RT.Common;
using Server.Common;

namespace RT.Models
{
    /// <summary>
    /// Medius 1.50 (SOCOM II) channel list entry, Lobby class 0xED. The client's handler requires
    /// exactly 0x70 bytes: MessageID[21], 3 pad, StatusCode, MediusWorldID, PlayerCount u16,
    /// MaxPlayers u16, SecurityLevel, GenericField1, LobbyName[64], EndOfList, 3 pad
    /// (offsets read by the game's callback FUN_002e3b00).
    /// </summary>
    // No [MediusMessage] attribute: Lobby/0xED is already registered by MediusChannelList_ExtraInfoResponse
    // for parsing; this class is only serialized, and PacketType supplies the id.
    public class MediusChannelList_ExtraInfoResponse0 : BaseLobbyMessage, IMediusResponse
    {
        public override byte PacketType => (byte)MediusLobbyMessageIds.ChannelList_ExtraInfoResponse;

        public bool IsSuccess => StatusCode >= 0;

        public MessageId MessageID { get; set; }
        public MediusCallbackStatus StatusCode;
        public int MediusWorldID;
        public ushort PlayerCount;
        public ushort MaxPlayers;
        public MediusWorldSecurityLevelType SecurityLevel;
        public uint GenericField1;
        public string LobbyName; // LOBBYNAME_MAXLEN
        public bool EndOfList;

        public override void Deserialize(Server.Common.Stream.MessageReader reader)
        {
            base.Deserialize(reader);
            MessageID = reader.Read<MessageId>();
            reader.ReadBytes(3);
            StatusCode = reader.Read<MediusCallbackStatus>();
            MediusWorldID = reader.ReadInt32();
            PlayerCount = reader.ReadUInt16();
            MaxPlayers = reader.ReadUInt16();
            SecurityLevel = reader.Read<MediusWorldSecurityLevelType>();
            GenericField1 = reader.ReadUInt32();
            LobbyName = reader.ReadString(Constants.LOBBYNAME_MAXLEN);
            EndOfList = reader.ReadBoolean();
            reader.ReadBytes(3);
        }

        public override void Serialize(Server.Common.Stream.MessageWriter writer)
        {
            base.Serialize(writer);
            writer.Write(MessageID ?? MessageId.Empty);
            writer.Write(new byte[3]);
            writer.Write(StatusCode);
            writer.Write(MediusWorldID);
            writer.Write(PlayerCount);
            writer.Write(MaxPlayers);
            writer.Write(SecurityLevel);
            writer.Write(GenericField1);
            writer.Write(LobbyName, Constants.LOBBYNAME_MAXLEN);
            writer.Write(EndOfList);
            writer.Write(new byte[3]);
        }

        public override string ToString()
        {
            return base.ToString() + $" MessageID:{MessageID} StatusCode:{StatusCode} MediusWorldID:{MediusWorldID} " +
                $"PlayerCount:{PlayerCount} MaxPlayers:{MaxPlayers} SecurityLevel:{SecurityLevel} " +
                $"GenericField1:{GenericField1} LobbyName:{LobbyName} EndOfList:{EndOfList}";
        }
    }
}
