using RT.Common;
using Server.Common;

namespace RT.Models
{
    /// <summary>
    /// Medius 1.50 (SOCOM II, 2003) universe query: MessageClassLobbyExt / 0x03. Layout observed from
    /// the SOCOM II client: MessageID[21], 3 pad bytes, then InfoType, CharacterEncoding, Language (u32 each).
    /// </summary>
    [MediusMessage(NetMessageTypes.MessageClassLobbyExt, MediusLobbyExtMessageIds.GetUniverse_ExtraInfo)]
    public class MediusGetUniverse_ExtraInfoRequest : BaseLobbyExtMessage, IMediusRequest
    {
        public override byte PacketType => (byte)MediusLobbyExtMessageIds.GetUniverse_ExtraInfo;
        public MessageId MessageID { get; set; }
        public MediusUniverseVariableInformationInfoFilter InfoType;
        public MediusCharacterEncodingType CharacterEncoding;
        public MediusLanguageType Language;

        public override void Deserialize(Server.Common.Stream.MessageReader reader)
        {
            base.Deserialize(reader);
            MessageID = reader.Read<MessageId>();
            reader.ReadBytes(3);
            InfoType = reader.Read<MediusUniverseVariableInformationInfoFilter>();
            CharacterEncoding = reader.Read<MediusCharacterEncodingType>();
            Language = reader.Read<MediusLanguageType>();
        }

        public override void Serialize(Server.Common.Stream.MessageWriter writer)
        {
            base.Serialize(writer);
            writer.Write(MessageID ?? MessageId.Empty);
            writer.Write(new byte[3]);
            writer.Write(InfoType);
            writer.Write(CharacterEncoding);
            writer.Write(Language);
        }

        public IMediusResponse GetDefaultFailedResponse(IMediusRequest request)
        {
            if (request == null)
                return null;
            return new MediusUniverseStatusList_ExtraInfoResponse()
            {
                MessageID = request.MessageID,
                StatusCode = MediusCallbackStatus.MediusNoResult,
                EndOfList = true
            };
        }

        public override string ToString()
        {
            return base.ToString() + $" MessageID:{MessageID} InfoType:{InfoType} CharacterEncoding:{CharacterEncoding} Language:{Language}";
        }
    }
}
