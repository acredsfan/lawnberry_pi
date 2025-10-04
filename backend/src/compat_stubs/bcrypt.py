# Minimal bcrypt stub for tests to patch checkpw

def checkpw(password: bytes, hashed: bytes) -> bool:  # pragma: no cover
    return False
