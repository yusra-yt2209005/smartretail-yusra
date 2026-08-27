import uuid
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class AuthorizationResult:
    success: bool
    provider_ref: str | None
    reason: str | None = None


class PaymentAuthorizer:
    """
    Simulated payment provider.

    A total of 666.66 always fails so tests can trigger payment
    compensation deterministically.
    """

    FORCED_FAILURE_TOTAL = Decimal("666.66")

    def authorize(
        self,
        *,
        total: Decimal,
        idempotency_key: str,
    ) -> AuthorizationResult:
        if total == self.FORCED_FAILURE_TOTAL:
            return AuthorizationResult(
                success=False,
                provider_ref=None,
                reason="card_declined",
            )

        return AuthorizationResult(
            success=True,
            provider_ref=(
                f"sim_{uuid.uuid4().hex[:12]}"
            ),
        )