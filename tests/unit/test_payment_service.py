from decimal import Decimal

from app.services.payment_service import PaymentAuthorizer


def test_payment_authorization_succeeds():
    authorizer = PaymentAuthorizer()

    result = authorizer.authorize(
        total=Decimal("99.99"),
        idempotency_key="success-test",
    )

    assert result.success is True
    assert result.provider_ref is not None
    assert result.provider_ref.startswith("sim_")
    assert result.reason is None


def test_payment_authorization_can_be_forced_to_fail():
    authorizer = PaymentAuthorizer()

    result = authorizer.authorize(
        total=Decimal("666.66"),
        idempotency_key="failure-test",
    )

    assert result.success is False
    assert result.provider_ref is None
    assert result.reason == "card_declined"