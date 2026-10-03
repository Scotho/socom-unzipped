// LOCAL (socom_pc), #72: the project's own, not ported. The Medius 1.50 layout of the Lobby/0xF0 ladder entry.
using RT.Common;
using Server.Common;

namespace RT.Models
{
    /// <summary>
    /// Medius 1.50 (SOCOM II) ladder list entry, Lobby class 0xF0, the answer to Lobby/0xEF. The client's handler
    /// FUN_0064d210 consumes exactly 0x1D4 bytes, four fewer than MediusLadderList_ExtraInfoResponse: the 1.50
    /// entry has no AccountID. MessageID[21], 3 pad, StatusCode 0x18, LadderPosition 0x1C, LadderStat 0x20,
    /// AccountName[32] 0x24, AccountStats[256] 0x44, OnlineState 0x144, EndOfList 0x1D0, 3 pad (offsets read by
    /// the game's callbacks FUN_002eb6a0 and FUN_002ebe50).
    /// </summary>
    // No [MediusMessage] attribute: Lobby/0xF0 is already registered by MediusLadderList_ExtraInfoResponse for
    // parsing; this class is only serialized, and PacketType supplies the id.
    public class MediusLadderList_ExtraInfoResponse0 : BaseLobbyMessage, IMediusResponse
    {
        public override byte PacketType => (byte)MediusLobbyMessageIds.LadderList_ExtraInfoResponse;

        public bool IsSuccess => StatusCode >= 0;

        public MessageId MessageID { get; set; }
        public MediusCallbackStatus StatusCode;
        public uint LadderPosition;
        public int LadderStat;
        public string AccountName; // ACCOUNTNAME_MAXLEN
        public byte[] AccountStats = new byte[Constants.ACCOUNTSTATS_MAXLEN];
        // Never null: a null field would serialize as nothing and shorten the message.
        public MediusPlayerOnlineState OnlineState = new MediusPlayerOnlineState();
        public bool EndOfList;

        public override void Deserialize(Server.Common.Stream.MessageReader reader)
        {
            base.Deserialize(reader);
            MessageID = reader.Read<MessageId>();
            reader.ReadBytes(3);
            StatusCode = reader.Read<MediusCallbackStatus>();
            LadderPosition = reader.ReadUInt32();
            LadderStat = reader.ReadInt32();
            AccountName = reader.ReadString(Constants.ACCOUNTNAME_MAXLEN);
            AccountStats = reader.ReadBytes(Constants.ACCOUNTSTATS_MAXLEN);
            OnlineState = reader.Read<MediusPlayerOnlineState>();
            EndOfList = reader.ReadBoolean();
            reader.ReadBytes(3);
        }

        public override void Serialize(Server.Common.Stream.MessageWriter writer)
        {
            base.Serialize(writer);
            writer.Write(MessageID ?? MessageId.Empty);
            writer.Write(new byte[3]);
            writer.Write(StatusCode);
            writer.Write(LadderPosition);
            writer.Write(LadderStat);
            writer.Write(AccountName, Constants.ACCOUNTNAME_MAXLEN);
            writer.Write(AccountStats, Constants.ACCOUNTSTATS_MAXLEN);
            writer.Write(OnlineState ?? new MediusPlayerOnlineState());
            writer.Write(EndOfList);
            writer.Write(new byte[3]);
        }

        public override string ToString()
        {
            return base.ToString() + " " +
                $"MessageID:{MessageID} StatusCode:{StatusCode} LadderPosition:{LadderPosition} " +
                $"LadderStat:{LadderStat} AccountName:{AccountName} OnlineState:{OnlineState} EndOfList:{EndOfList}";
        }
    }
}
