"""
Spotify API Wrapper
~~~~~~~~~~~~~~~~~~~

An unofficial asynchronous wrapper to interact with Spotify API

:copyright: (c) 2021 AkshuAgarwal
:license: MIT, see LICENSE for more details.
"""

from .client import *
from .errors import *

__title__ = "aiospotify"
__author__ = "AkshuAgarwal"
__license__ = "MIT"
__copyright__ = "Copyright (c) 2021 AkshuAgarwal"
__version__ = "0.0.1a"

import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())
