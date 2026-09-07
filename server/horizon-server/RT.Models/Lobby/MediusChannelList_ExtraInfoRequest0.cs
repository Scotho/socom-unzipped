using RT.Common;
using Server.Common;

namespace RT.Models
{
    /// <summary>
    /// Medius 1.50 (SOCOM II) channel list request on the Lobby class (0xEC). 26 bytes:
    /// MessageID[21], 1 pad byte, PageID u16, PageSize u16 (matches the 1.50 client's sender FUN_0064b098).
    /// </summary>
    [MediusMessage(NetMessageTypes.MessageClassLobby, MediusLobbyMessageIds.ChannelList_ExtraInfo0)]
    public class MediusChannelList_ExtraInfoRequest0 : BaseLobbyMessage, IMediusRequest
    {
        public override byte PacketType => (byte)MediusLobbyMessageIds.ChannelList_ExtraInfo0;

        public MessageId MessageID { get; set; }
        public ushort PageID;
        public ushort PageSize;

        public override void Deserialize(Server.Common.Stream.MessageReader reader)
        {
            base.Deserialize(reader);
            MessageID = reader.Read<MessageId>();
            reader.ReadBytes(1);
            PageID = reader.ReadUInt16();
            PageSize = reader.ReadUInt16();
        }

        public override void Serialize(Server.Common.Stream.MessageWriter writer)
        {
            base.Serialize(writer);
            writer.Write(MessageID ?? MessageId.Empty);
            writer.Write(new byte[1]);
            writer.Write(PageID);
            writer.Write(PageSize);
        }

        public IMediusResponse GetDefaultFailedResponse(IMediusRequest request)
        {
            return new MediusChannelList_ExtraInfoResponse0()
            {
                MessageID = MessageID,
                StatusCode = MediusCallbackStatus.MediusFail,
                EndOfList = true
            };
        }

        public override string ToString()
        {
            return base.ToString() + $" MessageID:{MessageID} PageID:{PageID} PageSize:{PageSize}";
        }
    }
}
