// LOCAL (socom_pc), issue #72: the five requests the Medius 1.50 client (SOCOM II r0001 and r0004) sends that the
// server left unanswered -- Lobby 0x86 VersionServer, 0xB2 FileListFiles, 0xCE UpdateLadderStats,
// 0xEF LadderList_ExtraInfo0 and LobbyExt 0x08 GetBuddyInvitations. The models are ported from PSHome-MultiServer
// (GPL-3.0); the byte counts below are the client's own: each request's size is the length its sender passes
// (FUN_00647548 0x26, FUN_0064b7c8 0xB0, FUN_0064b248 0x58, FUN_0064b128 0x28, the LobbyExt 0x08 sender 0x15),
// each response's the count its handler returns (FUN_0064cbf8 0x4D, FUN_0064d6c8 200, FUN_0064d250 0x1C,
// FUN_0064d210 0x1D4, FUN_0064dad0 0x48), read from the r0001 decomp at handler registration FUN_0064db00.
using System.IO;
using System.Linq;
using RT.Common;
using RT.Models;
using Server.Common;
using Server.Common.Stream;
using Server.Medius;
using Xunit;

namespace Server.Test
{
    public class Medius150MessagesTests
    {
        // The message as the wire carries it: class byte, id byte, then the body.
        static byte[] Wire(BaseMediusMessage message)
        {
            using var ms = new MemoryStream();
            using (var writer = new MessageWriter(ms))
            {
                writer.Write(message.PacketClass);
                writer.Write(message.PacketType);
                message.Serialize(writer);
            }
            return ms.ToArray();
        }

        // Parse through the server's own registry, and say how many body bytes the parse consumed.
        static (BaseMediusMessage message, long consumed) Parse(byte[] wire)
        {
            using var ms = new MemoryStream(wire);
            using var reader = new MessageReader(ms);
            var message = BaseMediusMessage.Instantiate(reader);
            return (message, ms.Position - 2);
        }

        static T Reread<T>(T message) where T : BaseMediusMessage, new()
        {
            using var ms = new MemoryStream(Wire(message).Skip(2).ToArray());
            using var reader = new MessageReader(ms);
            var copy = new T();
            copy.Deserialize(reader);
            Assert.Equal(ms.Length, ms.Position);
            return copy;
        }

        static void AssertHeader(byte[] wire, NetMessageTypes cls, byte id)
        {
            Assert.Equal((byte)cls, wire[0]);
            Assert.Equal(id, wire[1]);
        }

        // ---- requests: registered under the declared id, parsed at exactly the client's size ----

        [Fact]
        public void VersionServerRequestParsesAtTheClientsSize()
        {
            var wire = Wire(new MediusVersionServerRequest { MessageID = new MessageId("71"), SessionKey = "KEY1234" });
            AssertHeader(wire, NetMessageTypes.MessageClassLobby, (byte)MediusLobbyMessageIds.VersionServer);
            Assert.Equal(2 + 0x26, wire.Length);
            var (message, consumed) = Parse(wire);
            var request = Assert.IsType<MediusVersionServerRequest>(message);
            Assert.Equal(0x26, consumed);
            Assert.Equal("71", request.MessageID.Value);
            Assert.Equal("KEY1234", request.SessionKey);
        }

        [Fact]
        public void FileListRequestParsesAtTheClientsSize()
        {
            var sent = new MediusFileListRequest
            {
                FileNameBeginsWith = "WeapProfile_1.dat",
                FilesizeGreaterThan = 0,
                FilesizeLessThan = 5000000,
                OwnerByID = 42,
                NewerThanTimestamp = 7,
                StartingEntryNumber = 0,
                PageSize = 1,
                MessageID = new MessageId("72"),
            };
            var wire = Wire(sent);
            AssertHeader(wire, NetMessageTypes.MessageClassLobby, (byte)MediusLobbyMessageIds.FileListFiles);
            Assert.Equal(2 + 0xB0, wire.Length);
            // The client writes the MessageID last, at body offset 0x98 (FUN_0064b7c8).
            Assert.Equal((byte)'7', wire[2 + 0x98]);
            var (message, consumed) = Parse(wire);
            var request = Assert.IsType<MediusFileListRequest>(message);
            Assert.Equal(0xB0, consumed);
            Assert.Equal("WeapProfile_1.dat", request.FileNameBeginsWith);
            Assert.Equal(5000000u, request.FilesizeLessThan);
            Assert.Equal(42u, request.OwnerByID);
            Assert.Equal(7u, request.NewerThanTimestamp);
            Assert.Equal(1u, request.PageSize);
            Assert.Equal("72", request.MessageID.Value);
        }

        [Fact]
        public void UpdateLadderStatsRequestParsesAtTheClientsSize()
        {
            var stats = Enumerable.Range(1, Constants.LADDERSTATS_MAXLEN).ToArray();
            var wire = Wire(new MediusUpdateLadderStatsRequest
            {
                MessageID = new MessageId("73"),
                LadderType = MediusLadderType.MediusLadderTypeClan,
                Stats = stats,
            });
            AssertHeader(wire, NetMessageTypes.MessageClassLobby, (byte)MediusLobbyMessageIds.UpdateLadderStats);
            Assert.Equal(2 + 0x58, wire.Length);
            var (message, consumed) = Parse(wire);
            var request = Assert.IsType<MediusUpdateLadderStatsRequest>(message);
            Assert.Equal(0x58, consumed);
            Assert.Equal("73", request.MessageID.Value);
            Assert.Equal(MediusLadderType.MediusLadderTypeClan, request.LadderType);
            Assert.Equal(stats, request.Stats);
        }

        [Fact]
        public void LadderListExtraInfo0RequestParsesAtTheClientsSize()
        {
            var wire = Wire(new MediusLadderList_ExtraInfoRequest0
            {
                MessageID = new MessageId("74"),
                LadderStatIndex = 0,
                SortOrder = MediusSortOrder.MEDIUS_DESCENDING,
                StartPosition = 11,
                PageSize = 20,
            });
            AssertHeader(wire, NetMessageTypes.MessageClassLobby, (byte)MediusLobbyMessageIds.LadderList_ExtraInfo0);
            Assert.Equal(2 + 0x28, wire.Length);
            var (message, consumed) = Parse(wire);
            var request = Assert.IsType<MediusLadderList_ExtraInfoRequest0>(message);
            Assert.Equal(0x28, consumed);
            Assert.Equal("74", request.MessageID.Value);
            Assert.Equal(MediusSortOrder.MEDIUS_DESCENDING, request.SortOrder);
            Assert.Equal(11u, request.StartPosition);
            Assert.Equal(20u, request.PageSize);
        }

        [Fact]
        public void GetBuddyInvitationsRequestParsesAtTheClientsSize()
        {
            var wire = Wire(new MediusGetBuddyInvitationsRequest { MessageID = new MessageId("75") });
            AssertHeader(wire, NetMessageTypes.MessageClassLobbyExt, (byte)MediusLobbyExtMessageIds.GetBuddyInvitations);
            Assert.Equal(2 + 0x15, wire.Length);
            var (message, consumed) = Parse(wire);
            var request = Assert.IsType<MediusGetBuddyInvitationsRequest>(message);
            Assert.Equal(0x15, consumed);
            Assert.Equal("75", request.MessageID.Value);
        }

        // ---- responses: the declared id, the client's byte count, a lossless round trip ----

        [Fact]
        public void VersionServerResponseIs0x4DBytesAndRoundTrips()
        {
            var sent = new MediusVersionServerResponse { MessageID = new MessageId("71"), VersionServer = "Medius Lobby Server Version 3.05" };
            var wire = Wire(sent);
            AssertHeader(wire, NetMessageTypes.MessageClassLobby, (byte)MediusLobbyMessageIds.VersionServerResponse);
            Assert.Equal(2 + 0x4D, wire.Length);
            var copy = Reread(sent);
            Assert.Equal("71", copy.MessageID.Value);
            Assert.Equal(sent.VersionServer, copy.VersionServer);
        }

        [Fact]
        public void FileListResponseIs200BytesAndRoundTrips()
        {
            var sent = new MediusFileListResponse
            {
                MediusFileToList = new MediusFile { Filename = "WeapProfile_1.dat", FileID = 3, FileSize = 640, OwnerID = 42 },
                StatusCode = MediusCallbackStatus.MediusSuccess,
                MessageID = new MessageId("72"),
                EndOfList = true,
            };
            var wire = Wire(sent);
            AssertHeader(wire, NetMessageTypes.MessageClassLobby, (byte)MediusLobbyMessageIds.FileListFilesResponse);
            Assert.Equal(2 + 200, wire.Length);
            // The client reads StatusCode at 0xAC, the MessageID at 0xB0 and EndOfList at 0xC5 (FUN_00305230).
            Assert.Equal((byte)'7', wire[2 + 0xB0]);
            Assert.Equal(1, wire[2 + 0xC5]);
            var copy = Reread(sent);
            Assert.Equal("WeapProfile_1.dat", copy.MediusFileToList.Filename);
            Assert.Equal(640u, copy.MediusFileToList.FileSize);
            Assert.Equal(42u, copy.MediusFileToList.OwnerID);
            Assert.Equal(MediusCallbackStatus.MediusSuccess, copy.StatusCode);
            Assert.Equal("72", copy.MessageID.Value);
            Assert.True(copy.EndOfList);
        }

        [Fact]
        public void AnEmptyFileListResponseIsStill200Bytes()
        {
            Assert.Equal(2 + 200, Wire(new MediusFileListResponse { MessageID = new MessageId("1"), EndOfList = true }).Length);
        }

        [Fact]
        public void UpdateLadderStatsResponseIs0x1CBytesAndRoundTrips()
        {
            var sent = new MediusUpdateLadderStatsResponse { MessageID = new MessageId("73"), StatusCode = MediusCallbackStatus.MediusSuccess };
            var wire = Wire(sent);
            AssertHeader(wire, NetMessageTypes.MessageClassLobby, (byte)MediusLobbyMessageIds.UpdateLadderStatsResponse);
            Assert.Equal(2 + 0x1C, wire.Length);
            var copy = Reread(sent);
            Assert.Equal("73", copy.MessageID.Value);
            Assert.Equal(MediusCallbackStatus.MediusSuccess, copy.StatusCode);
        }

        [Fact]
        public void LadderPageEntryRoundTripsAtTheClientsSize()
        {
            var sent = new MediusLadderList_ExtraInfoResponse0
            {
                MessageID = new MessageId("74"),
                StatusCode = MediusCallbackStatus.MediusSuccess,
                LadderPosition = 3,
                LadderStat = 1200,
                AccountName = "seal",
                AccountStats = Enumerable.Range(0, Constants.ACCOUNTSTATS_MAXLEN).Select(i => (byte)i).ToArray(),
                OnlineState = new MediusPlayerOnlineState { ConnectStatus = MediusPlayerStatus.MediusPlayerInChatWorld, MediusLobbyWorldID = 5, MediusGameWorldID = -1, LobbyName = "Alpha", GameName = "" },
                EndOfList = true,
            };
            var wire = Wire(sent);
            // The 1.50 response is Lobby/0xF0, the id Types.cs declares as LadderList_ExtraInfoResponse.
            AssertHeader(wire, NetMessageTypes.MessageClassLobby, (byte)MediusLobbyMessageIds.LadderList_ExtraInfoResponse);
            Assert.Equal(2 + 0x1D4, wire.Length);
            // The client's callback FUN_002eb6a0/FUN_002ebe50: StatusCode 0x18, position 0x1C, stat 0x20,
            // AccountName 0x24, AccountStats 0x44, OnlineState 0x144, EndOfList 0x1D0.
            Assert.Equal((byte)'s', wire[2 + 0x24]);
            Assert.Equal(1, wire[2 + 0x1D0]);
            var copy = Reread(sent);
            Assert.Equal("74", copy.MessageID.Value);
            Assert.Equal(3u, copy.LadderPosition);
            Assert.Equal(1200, copy.LadderStat);
            Assert.Equal("seal", copy.AccountName);
            Assert.Equal(sent.AccountStats, copy.AccountStats);
            Assert.Equal("Alpha", copy.OnlineState.LobbyName);
            Assert.Equal(5, copy.OnlineState.MediusLobbyWorldID);
            Assert.True(copy.EndOfList);
        }

        [Fact]
        public void AnEmptyLadderPageEntryKeepsItsSize()
        {
            Assert.Equal(2 + 0x1D4, Wire(new MediusLadderList_ExtraInfoResponse0 { MessageID = new MessageId("1"), EndOfList = true }).Length);
        }

        [Fact]
        public void GetBuddyInvitationsResponseIs0x48BytesAndRoundTrips()
        {
            var sent = new MediusGetBuddyInvitationsResponse
            {
                MessageID = new MessageId("75"),
                StatusCode = MediusCallbackStatus.MediusSuccess,
                AccountID = 9,
                AccountName = "buddy",
                AddType = MediusBuddyAddType.AddSymmetric,
                EndOfList = true,
            };
            var wire = Wire(sent);
            AssertHeader(wire, NetMessageTypes.MessageClassLobbyExt, (byte)MediusLobbyExtMessageIds.GetBuddyInvitationsResponse);
            Assert.Equal(2 + 0x48, wire.Length);
            var copy = Reread(sent);
            Assert.Equal("75", copy.MessageID.Value);
            Assert.Equal(9, copy.AccountID);
            Assert.Equal("buddy", copy.AccountName);
            Assert.Equal(MediusBuddyAddType.AddSymmetric, copy.AddType);
            Assert.True(copy.EndOfList);
        }

        // ---- the MLS answers (Medius150Replies, called by the five MLS cases) ----

        [Fact]
        public void VersionServerIsAnsweredWithTheServerVersion()
        {
            var reply = Assert.IsType<MediusVersionServerResponse>(Assert.Single(Medius150Replies.Answer(new MediusVersionServerRequest { MessageID = new MessageId("81") })));
            Assert.Equal("81", reply.MessageID.Value);
            Assert.Equal(Medius150Replies.LobbyServerVersion, reply.VersionServer);
            Assert.True(reply.IsSuccess);
        }

        [Fact]
        public void FileListFilesIsAnsweredWithAnEmptyEndOfList()
        {
            var reply = Assert.IsType<MediusFileListResponse>(Assert.Single(Medius150Replies.Answer(new MediusFileListRequest { MessageID = new MessageId("82"), FileNameBeginsWith = "WeapProfile_1.dat" })));
            Assert.Equal("82", reply.MessageID.Value);
            Assert.Equal(MediusCallbackStatus.MediusNoResult, reply.StatusCode);
            Assert.True(reply.EndOfList);
            Assert.NotNull(reply.MediusFileToList);
        }

        [Fact]
        public void UpdateLadderStatsIsAnsweredWithSuccess()
        {
            var reply = Assert.IsType<MediusUpdateLadderStatsResponse>(Assert.Single(Medius150Replies.Answer(new MediusUpdateLadderStatsRequest { MessageID = new MessageId("83") })));
            Assert.Equal("83", reply.MessageID.Value);
            Assert.Equal(MediusCallbackStatus.MediusSuccess, reply.StatusCode);
        }

        [Fact]
        public void Ladder0IsAnsweredWithAnEmpty150Page()
        {
            var reply = Assert.IsType<MediusLadderList_ExtraInfoResponse0>(Assert.Single(Medius150Replies.Answer(new MediusLadderList_ExtraInfoRequest0 { MessageID = new MessageId("84"), StartPosition = 1, PageSize = 10 })));
            Assert.Equal("84", reply.MessageID.Value);
            Assert.Equal(MediusCallbackStatus.MediusNoResult, reply.StatusCode);
            Assert.True(reply.EndOfList);
        }

        [Fact]
        public void GetBuddyInvitationsIsAnsweredWithAnEmptyEndOfList()
        {
            var reply = Assert.IsType<MediusGetBuddyInvitationsResponse>(Assert.Single(Medius150Replies.Answer(new MediusGetBuddyInvitationsRequest { MessageID = new MessageId("85") })));
            Assert.Equal("85", reply.MessageID.Value);
            Assert.Equal(MediusCallbackStatus.MediusNoResult, reply.StatusCode);
            Assert.True(reply.EndOfList);
        }

        [Fact]
        public void AnyOtherRequestIsNotAnswered()
        {
            Assert.Null(Medius150Replies.Answer(new MediusChannelList_ExtraInfoRequest0 { MessageID = new MessageId("86") }));
        }

        [Fact]
        public void EachRequestsDefaultFailureIsItsOwnResponse()
        {
            Assert.IsType<MediusVersionServerResponse>(new MediusVersionServerRequest().GetDefaultFailedResponse(null));
            Assert.IsType<MediusFileListResponse>(new MediusFileListRequest().GetDefaultFailedResponse(null));
            Assert.IsType<MediusUpdateLadderStatsResponse>(new MediusUpdateLadderStatsRequest().GetDefaultFailedResponse(null));
            Assert.IsType<MediusLadderList_ExtraInfoResponse0>(new MediusLadderList_ExtraInfoRequest0().GetDefaultFailedResponse(null));
            Assert.IsType<MediusGetBuddyInvitationsResponse>(new MediusGetBuddyInvitationsRequest().GetDefaultFailedResponse(null));
        }
    }
}
