from ..objects import NewsBulletin
from ..protobuf.CancelNewsBulletins_pb2 import (
    CancelNewsBulletins as CancelNewsBulletinsProto,
)
from ..protobuf.NewsBulletin_pb2 import NewsBulletin as NewsBulletinProto
from ..protobuf.NewsBulletinsRequest_pb2 import (
    NewsBulletinsRequest as NewsBulletinsRequestProto,
)


def createNewsBulletinsRequestProto(allMessages: bool) -> NewsBulletinsRequestProto:
    newsBulletinsRequestProto = NewsBulletinsRequestProto()
    if allMessages:
        newsBulletinsRequestProto.allMessages = allMessages
    return newsBulletinsRequestProto


def createCancelNewsBulletinsProto() -> CancelNewsBulletinsProto:
    cancelNewsBulletinsProto = CancelNewsBulletinsProto()
    return cancelNewsBulletinsProto


def createNewsBulletin(newsBulletinProto: NewsBulletinProto) -> NewsBulletin:
    msgId = (
        newsBulletinProto.newsMsgId if newsBulletinProto.HasField("newsMsgId") else 0
    )
    msgType = (
        newsBulletinProto.newsMsgType
        if newsBulletinProto.HasField("newsMsgType")
        else 0
    )
    message = (
        newsBulletinProto.newsMessage
        if newsBulletinProto.HasField("newsMessage")
        else ""
    )
    originExch = (
        newsBulletinProto.originatingExch
        if newsBulletinProto.HasField("originatingExch")
        else ""
    )

    return NewsBulletin(msgId, msgType, message, originExch)
