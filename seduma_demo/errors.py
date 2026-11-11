"""Expected failures for bad input. These are not broker errors."""


class PracticeError(Exception):
    """A decision file, price file, or practice setting cannot be used."""


class AdapterError(PracticeError):
    """An agent decision file does not match the adapter."""


class PriceError(PracticeError):
    """The local price CSV cannot be used for a simulated fill."""
