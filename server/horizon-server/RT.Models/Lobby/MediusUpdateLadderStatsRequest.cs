// Ported from PSHome-MultiServer (GPL-3.0), AuxiliaryServices/HorizonService/RT.Models/Lobby/MediusUpdateLadderStatsRequest.cs at 8778e985e4.
using RT.Common;
using Server.Common;

namespace RT.Models
{
    /// <summary>
    /// Medius 1.50 (SOCOM II) ladder stats post, Lobby 0xCE: 0x58 bytes, MessageID[21], 3 pad, LadderType,
    /// Stats[15] (the client's sender FUN_0064b1b8).
    /// </summary>
    [MediusMessage(NetMessageTypes.MessageClassLobby, MediusLobbyMessageIds.UpdateLadderStats)]
    public class MediusUpdateLadderStatsRequest : BaseLobbyMessage, IMediusRequest
    {
        public override byte PacketType => (byte)MediusLobbyMessageIds.UpdateLadderStats;

        public MessageId MessageID { get; set; }

        public MediusLadderType LadderType;
        public int[] Stats = new int[Constants.LADDERSTATS_MAXLEN];

        public override void Deserialize(Server.Common.Stream.MessageReader reader)
        {
            base.Deserialize(reader);
            MessageID = reader.Read<MessageId>();
            reader.ReadBytes(3);
            LadderType = reader.Read<MediusLadderType>();
            for (int i = 0; i < Constants.LADDERSTATS_MAXLEN; ++i) { Stats[i] = reader.ReadInt32(); }
        }

        public override void Serialize(Server.Common.Stream.MessageWriter writer)
        {
            base.Serialize(writer);
            writer.Write(MessageID ?? MessageId.Empty);
            writer.Write(new byte[3]);
            writer.Write(LadderType);
            for (int i = 0; i < Constants.LADDERSTATS_MAXLEN; ++i) { writer.Write(Stats == null || i >= Stats.Length ? 0 : Stats[i]); }
        }

        // LOCAL (socom_pc): IMediusRequest here requires a default failure; MultiServer's interface does not.
        public IMediusResponse GetDefaultFailedResponse(IMediusRequest request)
        {
            return new MediusUpdateLadderStatsResponse()
            {
                MessageID = MessageID,
                StatusCode = MediusCallbackStatus.MediusFail
            };
        }

        public override string ToString()
        {
            return base.ToString() + " " +
                $"MessageID: {MessageID} " +
                $"LadderType: {LadderType} " +
                $"Stats: {string.Join(",", Stats ?? new int[0])}";
        }
    }
}
