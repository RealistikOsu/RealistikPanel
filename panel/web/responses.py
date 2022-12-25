from __future__ import annotations

from flask import render_template
from flask import session

from panel.config import config
from panel.functions import load_dashboard_data


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
        session=session,
        data=load_dashboard_data(),
        config=config,
        **kwargs,
    )
