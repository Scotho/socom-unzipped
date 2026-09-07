using RT.Common;
using Server.Common;

namespace RT.Models
{
    /// <summary>
    /// Medius 1.50 universe list entry: MessageClassLobbyExt / 0x04. Byte layout taken from the SOCOM II
    /// client's parser (FUN_002fdaf0): MessageID[21]+pad[3] @0x00, StatusCode @0x18, UniverseName[128] @0x1c,
    /// DNS[128] @0x9c, Port @0x11c, UniverseDescription[256] @0x120, Status @0x220, UserCount @0x224,
    /// MaxUsers @0x228, 8 unknown bytes @0x22c, UniverseBilling[128] @0x234, EndOfList (byte) @0x2b4,
    /// ExtendedInfo[128] @0x2b5 (key=value text the client scans), 3 pad bytes.
    /// </summary>
    [MediusMessage(NetMessageTypes.MessageClassLobbyExt, MediusLobbyExtMessageIds.UniverseStatusList_ExtraInfoResponse)]
    public class MediusUniverseStatusList_ExtraInfoResponse : BaseLobbyExtMessage, IMediusResponse
    {
        public override byte PacketType => (byte)MediusLobbyExtMessageIds.UniverseStatusList_ExtraInfoResponse;
        public bool IsSuccess => StatusCode >= 0;
        public MessageId MessageID { get; set; }
        public MediusCallbackStatus StatusCode;
        public string UniverseName;
        public string DNS;
        public int Port;
        public string UniverseDescription;
        public int Status;
        public int UserCount;
        public int MaxUsers;
        public string UniverseBilling;
        public bool EndOfList;
        public string ExtendedInfo;

        public override void Deserialize(Server.Common.Stream.MessageReader reader)
        {
            base.Deserialize(reader);
            MessageID = reader.Read<MessageId>();
            reader.ReadBytes(3);
            StatusCode = reader.Read<MediusCallbackStatus>();
            UniverseName = reader.ReadString(Constants.UNIVERSENAME_MAXLEN);
            DNS = reader.ReadString(Constants.UNIVERSEDNS_MAXLEN);
            Port = reader.ReadInt32();
            UniverseDescription = reader.ReadString(Constants.UNIVERSEDESCRIPTION_MAXLEN);
            Status = reader.ReadInt32();
            UserCount = reader.ReadInt32();
            MaxUsers = reader.ReadInt32();
            reader.ReadBytes(8);
            UniverseBilling = reader.ReadString(128);
            EndOfList = reader.ReadBoolean();
            ExtendedInfo = reader.ReadString(128);
            reader.ReadBytes(3);
        }

        public override void Serialize(Server.Common.Stream.MessageWriter writer)
        {
            base.Serialize(writer);
            writer.Write(MessageID ?? MessageId.Empty);
            writer.Write(new byte[3]);
            writer.Write(StatusCode);
            writer.Write(UniverseName, Constants.UNIVERSENAME_MAXLEN);
            writer.Write(DNS, Constants.UNIVERSEDNS_MAXLEN);
            writer.Write(Port);
            writer.Write(UniverseDescription, Constants.UNIVERSEDESCRIPTION_MAXLEN);
            writer.Write(Status);
            writer.Write(UserCount);
            writer.Write(MaxUsers);
            writer.Write(new byte[8]);
            writer.Write(UniverseBilling, 128);
            writer.Write(EndOfList);
            writer.Write(ExtendedInfo, 128);
            writer.Write(new byte[3]);
        }

        public override string ToString()
        {
            return base.ToString() + $" MessageID:{MessageID} StatusCode:{StatusCode} UniverseName:{UniverseName} DNS:{DNS} Port:{Port} Status:{Status} Users:{UserCount}/{MaxUsers} EndOfList:{EndOfList}";
        }
    }
}
