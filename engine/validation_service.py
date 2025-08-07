from abc import abstractmethod
from enums import MarketType, Side
from .event_service import EventService


class ValidationService:
    @abstractmethod
    def _validate_new(self, payload: dict) -> bool: ...


class FuturesValidationService(ValidationService):
    def _validate_new(self, db_payload: dict) -> bool:
        if self._payload_store.get(db_payload["order_id"]) is not None:
            return False

        if db_payload["order_id"] in self._positions:
            return False

        return True


class SpotValidationService(ValidationService):
    def _validate_new(self, db_payload: dict) -> bool:
        if self._payload_store.get(db_payload["order_id"]) is not None:
            return False

        _, bal_manager = self._instrument_manager.get(
            db_payload["instrument"], MarketType.SPOT
        )

        if (
            db_payload["side"] == Side.ASK
            and bal_manager.get_balance(db_payload) < db_payload["quantity"]
        ):
            EventService.log_rejection(
                db_payload, asset_balance=bal_manager.get_balance(db_payload)
            )
            return False
        
        return True
