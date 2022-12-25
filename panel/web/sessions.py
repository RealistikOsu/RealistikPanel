# A wrapper lib around flask's sessions
from __future__ import annotations

import os

from flask import Flask
from flask import session


def encrypt_session(app: Flask) -> None:
    app.secret_key = os.urandom(24)
