"""Local dashboard: Starlette app serving the packaged Vue build and the /api/ endpoints."""

from aifactory.web.app import STATIC_DIR, create_app, create_multi_app
from aifactory.web.registry import Registry, RepoEntry, RepoError
from aifactory.web.server import HOST, PortInUseError, check_port, dashboard_url, serve

__all__ = [
    "HOST",
    "STATIC_DIR",
    "PortInUseError",
    "Registry",
    "RepoEntry",
    "RepoError",
    "check_port",
    "create_app",
    "create_multi_app",
    "dashboard_url",
    "serve",
]
