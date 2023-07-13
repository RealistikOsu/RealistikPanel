# A wrapper lib around flask's sessions
from __future__ import annotations

import os
from copy import copy
from dataclasses import dataclass
from typing import Any
from typing import Callable

from flask import Flask
from flask import session

from panel.constants.privileges import Privileges
from panel.functions import has_privilege_value
from panel.web.responses import no_permission_response


@dataclass
class Session:
    logged_in: bool
    user_id: int
    username: str
    privileges: Privileges


DEFAULT_SESSION = Session(
    logged_in=False,
    user_id=0,
    username="",
    privileges=Privileges(0),
)


def _session_from_dict(s: dict[str, Any]) -> Session:
    return Session(
        logged_in=s["logged_in"],
        user_id=s["user_id"],
        username=s["username"],
        privileges=Privileges(s["privileges"]),
    )


# Insane session management that bypasses the entirety of flask's quirks.
def ensure() -> None:
    """Assigns a default session to the user if they don't have one."""

    if "session" in session:
        return None

    new_session = copy(DEFAULT_SESSION)
    session["session"] = new_session


def get() -> Session:
    """GETS A COPY OF THE SESSION. Ensure you call `ensure` prior to calling this or else this may raise `KeyError`."""

    # Happens when the session was set on this req
    if isinstance(session["session"], Session):
        return session["session"]
    return _session_from_dict(session["session"])


def set(s: Session) -> None:
    session["session"] = s


def encrypt(app: Flask) -> None:
    app.secret_key = os.urandom(24)


def requires_privilege(privilege: Privileges) -> Callable:
    """Decorator around a web handler which performs a privilege check."""

    def wrapper(func: Callable) -> Callable:
        def new_func(**args):
            session = get()
            if (not session.logged_in) or (
                not has_privilege_value(session.user_id, privilege)
            ):
                return no_permission_response(session)
            
            return func(**args)

        new_func.__name__ = func.__name__  # Flask hack.
        return new_func

    return wrapper
