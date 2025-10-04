# Minimal pyotp stub for tests to patch TOTP.verify

class TOTP:  # pragma: no cover
    def __init__(self, *args, **kwargs):
        pass
    def verify(self, code: str) -> bool:
        return False
