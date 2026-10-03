// Ported from PSHome-MultiServer (GPL-3.0), AuxiliaryServices/HorizonService/RT.Models/Lobby/MediusFileListResponse.cs at 8778e985e4.
using RT.Common;
using Server.Common;

namespace RT.Models
{
    /// <summary>
    /// Medius 1.50 (SOCOM II) file list entry, Lobby 0xB3: 200 bytes, MediusFile (0xAC), StatusCode at 0xAC,
    /// MessageID[21] at 0xB0, EndOfList at 0xC5, 2 pad bytes (the client's handler FUN_0064d6c8 and the game's
    /// callback FUN_00305230, which looks its pending request up by the MessageID).
    /// </summary>
    [MediusMessage(NetMessageTypes.MessageClassLobby, MediusLobbyMessageIds.FileListFilesResponse)]
    public class MediusFileListResponse : BaseLobbyMessage, IMediusResponse
    {
        public override byte PacketType => (byte)MediusLobbyMessageIds.FileListFilesResponse;

        public bool IsSuccess => StatusCode >= 0;

        // LOCAL (socom_pc): never null -- a null field would serialize as nothing and shorten the message.
        public MediusFile MediusFileToList = new MediusFile();
        public MediusCallbackStatus StatusCode;
        public MessageId MessageID { get; set; }
        public bool EndOfList;

        public override void Deserialize(Server.Common.Stream.MessageReader reader)
        {
            base.Deserialize(reader);
            MediusFileToList = reader.Read<MediusFile>();
            StatusCode = reader.Read<MediusCallbackStatus>();
            MessageID = reader.Read<MessageId>();
            EndOfList = reader.ReadBoolean();
            reader.ReadBytes(2);
        }

        public override void Serialize(Server.Common.Stream.MessageWriter writer)
        {
            base.Serialize(writer);
            writer.Write(MediusFileToList ?? new MediusFile());
            writer.Write(StatusCode);
            writer.Write(MessageID ?? MessageId.Empty);
            writer.Write(EndOfList);
            writer.Write(new byte[2]);
        }

        public override string ToString()
        {
            return base.ToString() + " " +
                $"MediusFileToList: {MediusFileToList} " +
                $"StatusCode: {StatusCode} " +
                $"MessageID: {MessageID} " +
                $"EndOfList: {EndOfList}";
        }
    }
}
