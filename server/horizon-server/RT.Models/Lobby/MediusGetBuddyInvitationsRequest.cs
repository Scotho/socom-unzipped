// Ported from PSHome-MultiServer (GPL-3.0), AuxiliaryServices/HorizonService/RT.Models/Lobby/MediusGetBuddyInvitationsRequest.cs at 8778e985e4.
using RT.Common;
using Server.Common;

namespace RT.Models
{
    /// <summary>
    /// Pending buddy invitations, LobbyExt 0x08. Medius 1.50 (SOCOM II): 0x15 bytes, the MessageID alone.
    /// </summary>
    [MediusMessage(NetMessageTypes.MessageClassLobbyExt, MediusLobbyExtMessageIds.GetBuddyInvitations)]
    public class MediusGetBuddyInvitationsRequest : BaseLobbyExtMessage, IMediusRequest
    {
        public override byte PacketType => (byte)MediusLobbyExtMessageIds.GetBuddyInvitations;

        public MessageId MessageID { get; set; }

        public override void Deserialize(Server.Common.Stream.MessageReader reader)
        {
            base.Deserialize(reader);
            MessageID = reader.Read<MessageId>();
        }

        public override void Serialize(Server.Common.Stream.MessageWriter writer)
        {
            base.Serialize(writer);
            writer.Write(MessageID ?? MessageId.Empty);
        }

        // LOCAL (socom_pc): IMediusRequest here requires a default failure; MultiServer's interface does not.
        public IMediusResponse GetDefaultFailedResponse(IMediusRequest request)
        {
            return new MediusGetBuddyInvitationsResponse()
            {
                MessageID = MessageID,
                StatusCode = MediusCallbackStatus.MediusFail,
                EndOfList = true
            };
        }

        public override string ToString()
        {
            return base.ToString() + " " +
                $"MessageID: {MessageID}";
        }
    }
}
