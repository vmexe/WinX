"""Content pages (one per navigation entry)."""

from .actions import ActionsPage, ToolsPage
from .apps import AppsPage
from .cleaner import CleanerPage
from .dashboard import DashboardPage
from .disks import DisksPage
from .drivers import DriversPage
from .settings import SettingsPage
from .startup import StartupPage
from .systeminfo import SystemInfoPage
from .tweaks import TweaksPage

__all__ = [
    "ActionsPage",
    "AppsPage",
    "CleanerPage",
    "DashboardPage",
    "DisksPage",
    "DriversPage",
    "SettingsPage",
    "StartupPage",
    "SystemInfoPage",
    "ToolsPage",
    "TweaksPage",
]
