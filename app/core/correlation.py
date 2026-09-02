from contextvars import ContextVar, Token


correlation_id_var: ContextVar[str] = ContextVar(
    "correlation_id",
    default="-",
)


def get_correlation_id() -> str:
    return correlation_id_var.get()


def set_correlation_id(
    correlation_id: str,
) -> Token:
    return correlation_id_var.set(
        correlation_id
    )


def reset_correlation_id(
    token: Token,
) -> None:
    correlation_id_var.reset(token)