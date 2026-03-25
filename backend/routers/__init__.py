"""CyberLab API Routers."""

from .courses import router as courses
from .challenges import router as challenges
from .grinder import router as grinder
from .progress import router as progress

__all__ = ["courses", "challenges", "grinder", "progress"]
