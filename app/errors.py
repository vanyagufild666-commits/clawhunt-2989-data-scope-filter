"""Errors shared by data-scope layer."""


class ConfigError(Exception):
    """Model lacks required scope columns (org_id/site_id/owner field) — startup fail."""
