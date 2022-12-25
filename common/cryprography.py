from __future__ import annotations

import hashlib

import bcrypt


def hash_md5(plaintext: str) -> str:
    return hashlib.md5(
        plaintext.encode(),
    ).hexdigest()


def compare_password(plaintext: str, hash: str) -> bool:
    """Compares a plaintext password to an osu hash (md5 + bcrypt)

    Args:
        plaintext (str): The plaintext password.
        hash (str): The hashed password.

    Returns:
        bool: Result of the comparison.
    """

    # Try-catch is necessary as some passwords have malformed values.
    try:
        return bcrypt.checkpw(
            hash_md5(plaintext).encode(),
            hash.encode(),
        )
    except Exception:
        return False
