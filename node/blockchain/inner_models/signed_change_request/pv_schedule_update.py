from ..signed_change_request_message.pv_schedule_update import PVScheduleUpdateSignedChangeRequestMessage
from .base import SignedChangeRequest


class PVScheduleUpdateSignedChangeRequest(SignedChangeRequest):
    message: PVScheduleUpdateSignedChangeRequestMessage