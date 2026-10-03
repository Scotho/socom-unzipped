// LOCAL (socom_pc), issue #72: the answers to the five requests the Medius 1.50 client (SOCOM II, r0001 and r0004)
// sends that the server used to leave unanswered. The answers follow PSHome-MultiServer's MLS handlers (GPL-3.0,
// Servers/Horizon/SERVER/Medius/MLS.cs at 8778e985e4, the cases at lines 1293, 1908, 2369, 2821 and 7819) with
// nothing behind them: we keep no file store, no ladder table and no buddy invitations, so every list answers
// "nothing to report" and a stats post is acknowledged and dropped. MLS.cs checks the session, then queues these.
using System.Collections.Generic;
using RT.Common;
using RT.Models;

namespace Server.Medius
{
    public static class Medius150Replies
    {
        // What MultiServer answers an app id it has no entry for (MediusServerVersionOverride, its default). The
        // 1.50 client's VersionServer callback does nothing with it; the request only needs an answer.
        public const string LobbyServerVersion = "Medius Lobby Server Version 3.05.201109161400";

        // The answer to one of the five requests, or null when the message is not one of them.
        public static List<BaseMediusMessage> Answer(BaseMediusMessage request)
        {
            switch (request)
            {
                case MediusVersionServerRequest versionServer:
                    return One(new MediusVersionServerResponse()
                    {
                        MessageID = versionServer.MessageID,
                        VersionServer = LobbyServerVersion,
                        StatusCode = MediusCallbackStatus.MediusSuccess,
                    });

                // MultiServer reads its file table; with no rows it answers NoResult with an empty, final entry.
                case MediusFileListRequest fileList:
                    return One(new MediusFileListResponse()
                    {
                        MessageID = fileList.MessageID,
                        StatusCode = MediusCallbackStatus.MediusNoResult,
                        MediusFileToList = new MediusFile(),
                        EndOfList = true,
                    });

                // MultiServer posts the stats to its database and answers Success; we keep no ladder table.
                case MediusUpdateLadderStatsRequest updateLadderStats:
                    return One(new MediusUpdateLadderStatsResponse()
                    {
                        MessageID = updateLadderStats.MessageID,
                        StatusCode = MediusCallbackStatus.MediusSuccess,
                    });

                // MultiServer answers an empty leaderboard with NoResult and EndOfList, in its 0xF0 class; the 1.50
                // client needs the 0x1D4-byte layout, MediusLadderList_ExtraInfoResponse0.
                case MediusLadderList_ExtraInfoRequest0 ladderList0:
                    return One(new MediusLadderList_ExtraInfoResponse0()
                    {
                        MessageID = ladderList0.MessageID,
                        StatusCode = MediusCallbackStatus.MediusNoResult,
                        EndOfList = true,
                    });

                // MultiServer answers no pending invitations with NoResult and EndOfList.
                case MediusGetBuddyInvitationsRequest buddyInvitations:
                    return One(new MediusGetBuddyInvitationsResponse()
                    {
                        MessageID = buddyInvitations.MessageID,
                        StatusCode = MediusCallbackStatus.MediusNoResult,
                        EndOfList = true,
                    });

                default:
                    return null;
            }
        }

        static List<BaseMediusMessage> One(BaseMediusMessage message) => new List<BaseMediusMessage> { message };
    }
}
