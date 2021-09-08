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
from typing import Optional, Tuple

import asyncio

from .http import HTTPClient


__all__: Tuple[str] = ("SpotifyClient",)


class SpotifyClient:
    """The Base class to connect and utilise the Spotify API.

    Currently, the wrapper only supports authorization with client_id and client_secret,
    because of which, some endpoints may be unavailable.

    Examples
    ---------

    Making a request: ::

        import asyncio
        from aiospotify import SpotifyClient

        spotify_client = SpotifyClient('client_id', 'client_secret')

        async def main():
            await spotify_client.authorize() # This function must be called before making any requests
            # TODO: Later
            await spotify_client.close()

        asyncio.run(main())

    Parameters
    -----------
    client_id: :class:`str`
        The unique Client ID provided by the Spotify while creating an application.
    client_secret: :class:`str`
        The unique Client Secret Key provided by the Spotify while creating an application.
    loop: Optional[:class:`asyncio.AbstractEventLoop`]
        The :class:`asyncio.AbstractEventLoop` to use for asynchronous operations.
        Defaults to ``None``. If not provided, the default event loop is used via
        :func:`asyncio.get_event_loop()`.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

        if not loop:
            loop = asyncio.get_event_loop()

        self.http = HTTPClient(client_id, client_secret, loop=loop)

    async def authorize(self) -> None:
        """The method which authorizes to the API. This should be called first
        before making any requests to the API.

        Raises
        -------
        :exc:`.InvalidClientCredentials`
            Wrong credentials are passed.
        :exc:`.HTTPException`
            An unknown HTTP related exception occured,
            usually when it isn't 200 or unknown.
        :exc:`.ServeError`
            Spotify Server Side errors.
            Most of the time we can do nothing about it.
        """
        await self.http.authorize()

    async def close(self) -> None:
        """Closes all the sessions and connections."""
        await self.http.destroy()
