// Ported from PSHome-MultiServer (GPL-3.0), AuxiliaryServices/HorizonService/RT.Models/Lobby/MediusVersionServerResponse.cs at 8778e985e4.
using RT.Common;
using Server.Common;

namespace RT.Models
{
    /// <summary>
    /// Version string of currently connected Medius Server.
    /// Medius 1.50 (SOCOM II): 0x4D bytes, MessageID[21] then VersionServer[56] (the client's handler FUN_0064cbf8).
    /// StatusCode is not on the wire, in MultiServer's model as in the 1.50 client's; it only sets IsSuccess.
    /// </summary>
    [MediusMessage(NetMessageTypes.MessageClassLobby, MediusLobbyMessageIds.VersionServerResponse)]
    public class MediusVersionServerResponse : BaseLobbyMessage, IMediusResponse
    {
        public override byte PacketType => (byte)MediusLobbyMessageIds.VersionServerResponse;

        public bool IsSuccess => StatusCode >= 0;
        public MediusCallbackStatus StatusCode;

        public MessageId MessageID { get; set; }
        public string VersionServer; // VERSIONSERVER_MAXLEN, including null termination

        public override void Deserialize(Server.Common.Stream.MessageReader reader)
        {
            base.Deserialize(reader);
            MessageID = reader.Read<MessageId>();
            VersionServer = reader.ReadString(Constants.VERSIONSERVER_MAXLEN);
        }

        public override void Serialize(Server.Common.Stream.MessageWriter writer)
        {
            base.Serialize(writer);
            writer.Write(MessageID ?? MessageId.Empty);
            writer.Write(VersionServer, Constants.VERSIONSERVER_MAXLEN);
        }

        public override string ToString()
        {
            return base.ToString() + " " +
                $"MessageID: {MessageID} " +
                $"Returning: {VersionServer}";
        }
    }
}
