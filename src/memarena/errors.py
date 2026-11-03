"""User-facing errors. The CLI prints these without a traceback."""


class MemarenaError(Exception):
    """An error with a message that tells the user what to do next."""


class MissingKeyError(MemarenaError):
    pass


class ProviderUnreachableError(MemarenaError):
    pass


class ModelNotFoundError(MemarenaError):
    pass


class BudgetExceededError(MemarenaError):
    pass


class OptionalDependencyError(MemarenaError):
    pass
