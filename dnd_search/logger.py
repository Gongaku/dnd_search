"""Logging configuration for dnd-search."""

import logging
import sys


def setup(verbosity: int = 0, debug: bool = False) -> None:
    """Configure root logger based on verbosity level.

    Verbosity 0 = WARNING (default, errors, and warnings only)
    Verbosity 1 = INFO    (-v)
    Verbosity 2 = DEBUG   (-vv)
    Verbosity 3 = DEBUG + HTTP tracing (-vvv)
    debug=True  = DEBUG regardless of verbosity
    """
    if debug or verbosity >= 2:
        level = logging.DEBUG
    elif verbosity == 1:
        level = logging.INFO
    else:
        level = logging.WARNING

    fmt = (
        "%(levelname)s %(name)s: %(message)s"
        if verbosity >= 1 or debug
        else "%(levelname)s: %(message)s"
    )

    logging.basicConfig(
        level=level,
        format=fmt,
        stream=sys.stderr,
        force=True,
    )

    # Enable HTTP-level tracing at -vvv
    if verbosity >= 3:
        import http.client

        http.client.HTTPConnection.debuglevel = 1
        logging.getLogger("urllib3").setLevel(logging.DEBUG)
    else:
        logging.getLogger("urllib3").setLevel(logging.WARNING)
