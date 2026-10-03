// Ported from PSHome-MultiServer (GPL-3.0), AuxiliaryServices/HorizonService/RT.Models/Lobby/MediusFileListRequest.cs at 8778e985e4.
using RT.Common;
using Server.Common;

namespace RT.Models
{
    /// <summary>
    /// Medius 1.50 (SOCOM II) file list request, Lobby 0xB2: 0xB0 bytes, FileNameBeginsWith[128], six u32 filters,
    /// then MessageID[21] at 0x98 and 3 pad bytes (the client's sender FUN_0064b7c8; SOCOM II asks for WeapProfile_1.dat).
    /// </summary>
    [MediusMessage(NetMessageTypes.MessageClassLobby, MediusLobbyMessageIds.FileListFiles)]
    public class MediusFileListRequest : BaseLobbyMessage, IMediusRequest
    {
        public override byte PacketType => (byte)MediusLobbyMessageIds.FileListFiles;

        public string FileNameBeginsWith; // MEDIUS_FILE_MAX_FILENAME_LENGTH
        public uint FilesizeGreaterThan;
        public uint FilesizeLessThan;
        public uint OwnerByID;
        public uint NewerThanTimestamp;
        public uint StartingEntryNumber;
        public uint PageSize;
        public MessageId MessageID { get; set; }

        public override void Deserialize(Server.Common.Stream.MessageReader reader)
        {
            base.Deserialize(reader);
            FileNameBeginsWith = reader.ReadString(Constants.MEDIUS_FILE_MAX_FILENAME_LENGTH);
            FilesizeGreaterThan = reader.ReadUInt32();
            FilesizeLessThan = reader.ReadUInt32();
            OwnerByID = reader.ReadUInt32();
            NewerThanTimestamp = reader.ReadUInt32();
            StartingEntryNumber = reader.ReadUInt32();
            PageSize = reader.ReadUInt32();
            MessageID = reader.Read<MessageId>();
            reader.ReadBytes(3);
        }

        public override void Serialize(Server.Common.Stream.MessageWriter writer)
        {
            base.Serialize(writer);
            // LOCAL (socom_pc): the name at its fixed width (MultiServer's Serialize writes a length-prefixed string).
            writer.Write(FileNameBeginsWith, Constants.MEDIUS_FILE_MAX_FILENAME_LENGTH);
            writer.Write(FilesizeGreaterThan);
            writer.Write(FilesizeLessThan);
            writer.Write(OwnerByID);
            writer.Write(NewerThanTimestamp);
            writer.Write(StartingEntryNumber);
            writer.Write(PageSize);
            writer.Write(MessageID ?? MessageId.Empty);
            writer.Write(new byte[3]);
        }

        // LOCAL (socom_pc): IMediusRequest here requires a default failure; MultiServer's interface does not.
        public IMediusResponse GetDefaultFailedResponse(IMediusRequest request)
        {
            return new MediusFileListResponse()
            {
                MessageID = MessageID,
                StatusCode = MediusCallbackStatus.MediusFail,
                EndOfList = true
            };
        }

        public override string ToString()
        {
            return base.ToString() + " " +
                $"FileNameBeginsWith: {FileNameBeginsWith} " +
                $"FilesizeGreaterThan: {FilesizeGreaterThan} " +
                $"FilesizeLessThan: {FilesizeLessThan} " +
                $"OwnerByID: {OwnerByID} " +
                $"NewerThanTimestamp: {NewerThanTimestamp} " +
                $"StartingEntryNumber: {StartingEntryNumber} " +
                $"PageSize: {PageSize} " +
                $"MessageID: {MessageID}";
        }
    }
}
