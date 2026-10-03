// Ported from PSHome-MultiServer (GPL-3.0), AuxiliaryServices/HorizonService/RT.Models/Lobby/MediusLadderList_ExtraInfoRequest0.cs
// (and the fields of its base, MediusLadderList_ExtraInfoRequest.cs) at 8778e985e4.
using RT.Common;
using Server.Common;

namespace RT.Models
{
    /// <summary>
    /// Medius 1.50 (SOCOM II) ladder list request on the Lobby class (0xEF): 0x28 bytes, MessageID[21], 3 pad,
    /// LadderStatIndex, SortOrder, StartPosition, PageSize (the client's sender FUN_0064b128, filled by FUN_002eb510).
    /// LOCAL (socom_pc): a Lobby-class message of its own; MultiServer derives it from the LobbyExt request, whose
    /// PacketClass would write it back under the wrong class. Answered with MediusLadderList_ExtraInfoResponse0.
    /// </summary>
    [MediusMessage(NetMessageTypes.MessageClassLobby, MediusLobbyMessageIds.LadderList_ExtraInfo0)]
    public class MediusLadderList_ExtraInfoRequest0 : BaseLobbyMessage, IMediusRequest
    {
        public override byte PacketType => (byte)MediusLobbyMessageIds.LadderList_ExtraInfo0;

        public MessageId MessageID { get; set; }

        public int LadderStatIndex;
        public MediusSortOrder SortOrder;
        public uint StartPosition;
        public uint PageSize;

        public override void Deserialize(Server.Common.Stream.MessageReader reader)
        {
            base.Deserialize(reader);
            MessageID = reader.Read<MessageId>();
            reader.ReadBytes(3);
            LadderStatIndex = reader.ReadInt32();
            SortOrder = reader.Read<MediusSortOrder>();
            StartPosition = reader.ReadUInt32();
            PageSize = reader.ReadUInt32();
        }

        public override void Serialize(Server.Common.Stream.MessageWriter writer)
        {
            base.Serialize(writer);
            writer.Write(MessageID ?? MessageId.Empty);
            writer.Write(new byte[3]);
            writer.Write(LadderStatIndex);
            writer.Write(SortOrder);
            writer.Write(StartPosition);
            writer.Write(PageSize);
        }

        public IMediusResponse GetDefaultFailedResponse(IMediusRequest request)
        {
            return new MediusLadderList_ExtraInfoResponse0()
            {
                MessageID = MessageID,
                StatusCode = MediusCallbackStatus.MediusFail,
                EndOfList = true
            };
        }

        public override string ToString()
        {
            return base.ToString() + " " +
                $"MessageID:{MessageID} " +
                $"LadderStatIndex:{LadderStatIndex} " +
                $"SortOrder:{SortOrder} " +
                $"StartPosition:{StartPosition} " +
                $"PageSize:{PageSize}";
        }
    }
}
