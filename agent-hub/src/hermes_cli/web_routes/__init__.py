"""Hermes Dashboard REST route modules."""

from __future__ import annotations

from fastapi import FastAPI

from hermes_cli.web_routes import credentials, memory, files, status, gateway, config, sessions, oauth_messaging, cron, mcp, pairing_webhooks, ops, skills, profiles, misc, dashboard_plugins


def register_routes(app: FastAPI) -> None:
    """Mount modular dashboard routers onto the Hermes app."""
    for module in (
    credentials,
    memory,
    files,
    status,
    gateway,
    config,
    sessions,
    oauth_messaging,
    cron,
    mcp,
    pairing_webhooks,
    ops,
    skills,
    profiles,
    misc,
    dashboard_plugins,
    ):
        app.include_router(module.router)
