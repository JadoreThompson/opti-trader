from enums import MarketType, Side
from .event_service import EventService


class ValidationService:
    def __init__(self, payloads: dict | None = None, **kw) -> None:
        self._payloads = payloads or {}
        super().__init__(**kw)

    def _validate_new(self, payload: dict) -> bool:
        return payload["order_id"] not in self._payloads


class FuturesValidationService(ValidationService):
    pass


class SpotValidationService(ValidationService):
    def _validate_new(self, payload: dict) -> bool:
        exists = super()._validate_new(payload)

        if exists:
            return exists

        _, bal_manager = self._instrument_manager.get(
            payload["instrument"], MarketType.SPOT
        )

        if (
            payload["side"] == Side.ASK
            and bal_manager.get_balance(payload["user_id"]) < payload["quantity"]
        ):
            EventService.log_rejection(
                payload, asset_balance=bal_manager.get_balance(payload["user_id"])
            )
            return False

        return True
