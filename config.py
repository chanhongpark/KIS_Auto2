"""
Compatibility shim for legacy imports of config.
Redirects to app_config to prevent 'No module named config' errors.
"""
import sys
import app_config

sys.modules["config"] = app_config
from app_config import *
