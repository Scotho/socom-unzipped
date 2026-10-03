// Ported from PSHome-MultiServer (GPL-3.0), AuxiliaryServices/HorizonService/RT.Models/Lobby/MediusUpdateLadderStatsResponse.cs at 8778e985e4.
using RT.Common;
using Server.Common;

namespace RT.Models
{
    /// <summary>
    /// Medius 1.50 (SOCOM II) ladder stats post result, Lobby 0xCF: 0x1C bytes, MessageID[21], 3 pad, StatusCode
    /// (the client's handler FUN_0064d250).
    /// </summary>
    [MediusMessage(NetMessageTypes.MessageClassLobby, MediusLobbyMessageIds.UpdateLadderStatsResponse)]
    public class MediusUpdateLadderStatsResponse : BaseLobbyMessage, IMediusResponse
    {
        public override byte PacketType => (byte)MediusLobbyMessageIds.UpdateLadderStatsResponse;

        public bool IsSuccess => StatusCode >= 0;

        public MessageId MessageID { get; set; }

        public MediusCallbackStatus StatusCode;

        public override void Deserialize(Server.Common.Stream.MessageReader reader)
        {
            base.Deserialize(reader);
            MessageID = reader.Read<MessageId>();
            reader.ReadBytes(3);
            StatusCode = reader.Read<MediusCallbackStatus>();
        }

        public override void Serialize(Server.Common.Stream.MessageWriter writer)
        {
            base.Serialize(writer);
            writer.Write(MessageID ?? MessageId.Empty);
            writer.Write(new byte[3]);
            writer.Write(StatusCode);
        }

        public override string ToString()
        {
            return base.ToString() + " " +
                $"MessageID: {MessageID} " +
                $"StatusCode: {StatusCode}";
        }
    }
}
