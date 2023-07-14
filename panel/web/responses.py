from __future__ import annotations

from typing import TYPE_CHECKING

from flask import redirect
from flask import render_template
from flask import request

from panel import web
from panel.config import config
from panel.functions import load_dashboard_data

if TYPE_CHECKING:
    from web.sessions import Session

# Template inject imports.
from panel.constants.privileges import Privileges
from panel.common import utils

# Automatically assigned their default name.
TEMPLATE_GLOBALS = [
    utils.halve_list,
    Privileges,
]

# Pre-cache these as they will be used on every page load.
_TEMPLATE_MAP_CACHE = {item.__name__: item for item in TEMPLATE_GLOBALS}


def load_panel_template(file: str, title: str, **kwargs) -> str:
    """Creates a JINJA template response, forwarding the necessary information into the
    template.

    Note:
        This passes the `title`, `session`, `data` (dash data) and `config`.

    Args:
        file (str): The location of the html file within the `templates` directory.
        title (str): The title of the page (as displayed to the user).
    """

    return render_template(
        file,
        title=title,
        session=web.sessions.get(),
        data=load_dashboard_data(),
        config=config,
        **kwargs,
        **_TEMPLATE_MAP_CACHE,
    )


def no_permission_response(session: Session):
    """If not logged it, returns redirect to login. Else 403s. This is for convienience when page is reloaded after restart."""
    if session.logged_in:
        return render_template("errors/403.html")

    return redirect(f"/login?redirect={request.path}")
