"""
MIT License

Copyright (c) 2021 AkshuAgarwal

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations
from typing import Any, Dict, Optional


class SpotifyException(Exception):
    """Base Exception for all the Spotify related exceptions"""

    pass


class NotAuthorized(SpotifyException):
    """Raised when HTTPClient.authorize is never called and user is trying to make requests."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class HTTPException(SpotifyException):
    """Base Exception for all the HTTP Requests related Exceptions"""

    def __init__(
        self, data: Dict[str, Any], status_code: int, message: Optional[str] = None
    ) -> None:
        fmt = f'{status_code} {data["error"]}'
        if desc := data.get("error_description") is not None:
            fmt += f": {desc}"
        else:
            fmt += f': {data["error"]["message"]}'

        if message is not None:
            fmt += f" ({message})"

        super().__init__(fmt)


class InvalidClientCredentials(HTTPException):
    """The client_id or client_secret is Invalid"""

    pass


class Forbidden(HTTPException):
    """Forbidden (The server understood the request, but is refusing to fulfill it)"""

    pass


class NotFound(HTTPException):
    """Not Found - The requested resource could not be found.
    This error can be due to a temporary or permanent condition.
    """

    pass


class ServerError(HTTPException):
    """Server side error. Possibly nothing we can do for this."""

    pass
