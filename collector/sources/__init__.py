class Blocked(Exception):
    """A site pushed back (rate limit, captcha): stop that source for this run.
    `partial` holds the jobs finished before the block, so they are still saved."""

    def __init__(self, message, partial=None):
        super().__init__(message)
        self.partial = partial or []
