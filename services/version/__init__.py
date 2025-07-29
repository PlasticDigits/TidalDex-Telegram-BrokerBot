"""
Version management service for the TidalDex Telegram Bot.

This package contains components for managing application versioning
to prevent multiple bot instances from running simultaneously.
"""
from services.version.VersionManager import version_manager

__all__ = [
    'version_manager'
] 