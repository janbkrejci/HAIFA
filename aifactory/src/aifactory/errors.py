"""Input errors shared by domain services and the dashboard."""


class UsageError(Exception):
    """A request the service does not understand (``usage_error``)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
