// Ported from PSHome-MultiServer (GPL-3.0), AuxiliaryServices/HorizonService/RT.Models/Lobby/MediusVersionServerRequest.cs at 8778e985e4.
using RT.Common;
using Server.Common;

namespace RT.Models
{
    /// <summary>
    /// Sent as request to retrieve version string of current connected Medius Server.
    /// Medius 1.50 (SOCOM II): 0x26 bytes, MessageID[21] then SessionKey[17] (the client's sender FUN_00647548).
    /// </summary>
    [MediusMessage(NetMessageTypes.MessageClassLobby, MediusLobbyMessageIds.VersionServer)]
    public class MediusVersionServerRequest : BaseLobbyMessage, IMediusRequest
    {
        public override byte PacketType => (byte)MediusLobbyMessageIds.VersionServer;

        public MessageId MessageID { get; set; }
        public string SessionKey; // SESSIONKEY_MAXLEN

        public override void Deserialize(Server.Common.Stream.MessageReader reader)
        {
            base.Deserialize(reader);
            MessageID = reader.Read<MessageId>();
            SessionKey = reader.ReadString(Constants.SESSIONKEY_MAXLEN);
        }

        public override void Serialize(Server.Common.Stream.MessageWriter writer)
        {
            base.Serialize(writer);
            writer.Write(MessageID ?? MessageId.Empty);
            writer.Write(SessionKey, Constants.SESSIONKEY_MAXLEN);
        }

        // LOCAL (socom_pc): IMediusRequest here requires a default failure; MultiServer's interface does not.
        public IMediusResponse GetDefaultFailedResponse(IMediusRequest request)
        {
            return new MediusVersionServerResponse()
            {
                MessageID = MessageID,
                StatusCode = MediusCallbackStatus.MediusFail,
            };
        }

        public override string ToString()
        {
            return base.ToString() + " " +
                $"MessageID: {MessageID} " +
                $"SessionKey: {SessionKey}";
        }
    }
}
