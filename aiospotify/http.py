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
from typing import Any, ClassVar, Dict, List, Literal, Optional, Tuple, TYPE_CHECKING

import asyncio
import aiohttp
import base64
import datetime
import six
import logging

from .errors import (
    HTTPException,
    InvalidClientCredentials,
    Forbidden,
    NotFound,
    ServerError,
    NotAuthorized,
)
from .types._spotify import ID, MARKETS

try:
    import orjson

    _from_json = orjson.loads
except ImportError:
    import json

    _from_json = json.loads


__all__: Tuple[str] = ("HTTPClient",)


log = logging.getLogger(__name__)

PARAMS = Dict[str, Any]
RESPONSE = Dict[str, Any]


class Route:
    __slots__ = ("path", "method", "url", "params")

    BASE: ClassVar[str] = "https://api.spotify.com/v1/"

    def __init__(self, method: str, path: str, params: Optional[PARAMS] = None) -> None:
        self.path: str = path
        self.method: str = method
        self.url: str = self.BASE + self.path
        self.params: Optional[Dict[str, str]] = params if params else None


class HTTPClient:
    """The Base Internal Class to make HTTP Requests to the API.
    This is meant to be used internally only.
    """

    ACCOUNT_BASE: ClassVar[str] = "https://accounts.spotify.com/api/"

    if TYPE_CHECKING:
        _access_token: str
        _expires_at: datetime.datetime
        _session: aiohttp.ClientSession

    def __init__(
        self, client_id: str, client_secret: str, *, loop: asyncio.AbstractEventLoop
    ) -> None:
        self.client_id: str = client_id
        self.client_secret: str = client_secret

        self.loop: asyncio.AbstractEventLoop = loop
        self.lock: asyncio.Lock = asyncio.Lock(loop=self.loop)

    async def request(self, route: Route) -> RESPONSE:
        """The base method to make all requests. This method do not handle login/authorization"""

        if not hasattr(
            self, "_session"
        ):  # User didn't call authorize before making request
            raise NotAuthorized(
                "You need to authorize first before making any requests"
            )

        method = route.method
        url = route.url
        params = route.params

        # Check if the access_token expired or not. If yes, authorize again
        if (
            datetime.datetime.utcnow() - self._expires_at
        ).seconds <= 10:  # 10 second extra delay
            await self.authorize()

        headers: Dict[str, str] = {"Authorization": f"Bearer {self._access_token}"}

        async with self.lock:
            log.debug("Dispatching %s request on %s with %s", method, url, params)
            async with self._session.request(
                method, url, headers=headers, params=params
            ) as response:
                log.debug(
                    "%s on %s with %s has responded with %s",
                    method,
                    url,
                    params,
                    response.status,
                )

                data: Dict[str, Any] = await response.json(
                    encoding="utf-8", loads=_from_json
                )

                if 200 <= response.status < 300:  # Successful
                    log.debug("Received data from (%s) %s: %s", method, url, data)
                    return data

                if response.status == 401:  # Unauthorized (Reauthorize and try again)
                    await self.authorize()
                    return await self.request(route)

                if response.status == 403:
                    raise Forbidden(data, response.status)
                if response.status == 404:
                    raise NotFound(data, response.status)

                if response.status == 429:  # Rate Limited
                    ...  # TODO: Later

                if response.status in {500, 502, 503}:
                    raise ServerError(data, response.status)

                # Handles: 304, 400
                raise HTTPException(data, response.status)

    async def authorize(self) -> None:
        """Authorize to the API and gets the Authorization Token to make requests.
        This method must be called before making any requests to the API, else it'll result to unhandled Exceptions.
        """

        if not hasattr(self, "_session"):
            self._session = aiohttp.ClientSession(loop=self.loop)

        auth_url: str = self.ACCOUNT_BASE + "token/"
        body = {"grant_type": "client_credentials"}
        encoded: bytes = base64.b64encode(
            six.text_type(self.client_id + ":" + self.client_secret).encode("ascii")
        )
        headers: Dict[str, str] = {"Authorization": f'Basic {encoded.decode("ascii")}'}

        response = aiohttp.ClientResponse = await self._session.post(
            auth_url, headers=headers, data=body
        )
        data: Dict[str, Any] = await response.json()

        try:
            assert response.status == 200  # Successful
            self._access_token = data["access_token"]
            self._expires_at = datetime.datetime.utcnow() + datetime.timedelta(
                seconds=data["expires_in"]
            )

        except AssertionError:
            if response.status in {
                201,
                202,
                204,
                304,
                401,
                404,
            }:  # TODO: Idk in what cases it raises exceptions (maybe later)
                log.error("Received %s with %s on authorization", response.status, data)
                return

            if response.status == 400:
                log.critical(
                    "Received %s while trying to authorize: %s", response.status, data
                )
                raise InvalidClientCredentials(data, response.status)

            if response.status == 403:
                raise HTTPException(data, response.status)

            if response.status in {500, 502, 503}:  # server error
                log.critical(
                    "Server Error: Received %s while trying to authorize: %s",
                    response.status,
                    data,
                )
                raise ServerError(data, response.status)

    async def destroy(self) -> None:
        """Destroys and cleans the sessions"""

        if self._session and not self._session.closed:
            await self._session.close()
            log.debug("Closed aiohttp session")

    # Albums API (https://developer.spotify.com/documentation/web-api/reference/#category-albums)

    async def get_multiple_albums(
        self, ids: List[ID], *, market: Optional[MARKETS] = None
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-multiple-albums

        params: PARAMS = {"ids": ",".join(id for id in ids)}
        if market:
            params["market"] = market

        return await self.request(Route("GET", "albums", params))

    async def get_album(self, id: ID, *, market: Optional[MARKETS] = None) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-an-album

        params: PARAMS = {}
        if market:
            params["market"] = market

        return await self.request(Route("GET", f"albums/{id}", params))

    async def get_album_tracks(
        self,
        id: ID,
        *,
        market: Optional[MARKETS] = None,
        limit: Optional[int] = 20,
        offset: Optional[int] = 0,
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-an-albums-tracks

        params: PARAMS = {}
        if market:
            params["market"] = market
        params["limit"] = limit
        params["offset"] = offset

        return await self.request(Route("GET", f"albums/{id}/tracks", params))

    # Artists API (https://developer.spotify.com/documentation/web-api/reference/#category-artists)

    async def get_multiple_artists(self, ids: List[ID]) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-multiple-artists

        params: PARAMS = {"ids": ",".join(id for id in ids)}

        return await self.request(Route("GET", "artists", params))

    async def get_artist(self, id: ID) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-an-artist

        return await self.request(Route("GET", f"artists/{id}"))

    async def get_artist_top_tracks(self, id: ID, *, market: MARKETS) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-an-artists-top-tracks

        params: PARAMS = {"market": market}
        return await self.request(Route("GET", f"artists/{id}/top-tracks", params))

    async def get_artist_related_artists(self, id: ID) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-an-artists-related-artists

        return await self.request(Route("GET", f"artists/{id}/related-artists"))

    async def get_artist_albums(
        self,
        id: ID,
        *,
        include_groups: Optional[
            List[Literal["album", "single", "appears_on", "compilation"]]
        ] = None,
        market: Optional[MARKETS] = None,
        limit: Optional[int] = 20,
        offset: Optional[int] = 0,
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-an-artists-albums

        params: PARAMS = {}

        if include_groups:
            params["include_groups"] = ",".join(group for group in include_groups)
        if market:
            params["market"] = market
        params["limit"] = limit
        params["offset"] = offset

        return await self.request(Route("GET", f"artists/{id}/albums", params))

    # Browse API (https://developer.spotify.com/documentation/web-api/reference/#category-browse)

    async def get_all_new_releases(
        self,
        *,
        country: Optional[MARKETS] = None,
        limit: Optional[int] = 20,
        offset: Optional[int] = 0,
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-new-releases

        params: PARAMS = {}

        if country:
            params["country"] = country
        params["limit"] = limit
        params["offset"] = offset

        return await self.request(Route("GET", "browse/new-releases", params))

    async def get_all_featured_playlists(
        self,
        *,
        country: Optional[MARKETS] = None,
        locale: Optional[str] = None,
        timestamp: Optional[str] = None,
        limit: Optional[int] = 20,
        offset: Optional[int] = 0,
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-featured-playlists

        params: PARAMS = {}
        if country:
            params["country"] = country
        if locale:
            params["locale"] = locale
        if timestamp:
            params["timestamp"] = timestamp
        params["limit"] = limit
        params["offset"] = offset

        return await self.request(Route("GET", "browse/featured-playlists", params))

    async def get_all_categories(
        self,
        *,
        country: Optional[MARKETS] = None,
        locale: Optional[str] = None,
        limit: Optional[int] = 20,
        offset: Optional[int] = 0,
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-categories

        params: PARAMS = {}
        if country:
            params["country"] = country
        if locale:
            params["locale"] = locale
        params["limit"] = limit
        params["offset"] = offset

        return await self.request(Route("GET", "browse/categories", params))

    async def get_category(
        self,
        category_id: ID,
        *,
        country: Optional[str] = None,
        locale: Optional[str] = None,
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-a-category

        params: PARAMS = {}
        if country:
            params["country"] = country
        if locale:
            params["locale"] = locale

        return await self.request(
            Route("GET", f"browse/categories/{category_id}", params)
        )

    async def get_category_playlists(
        self,
        category_id: ID,
        *,
        country: Optional[str] = None,
        limit: Optional[int] = 20,
        offset: Optional[int] = 0,
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-a-categories-playlists

        params: PARAMS = {}
        if country:
            params["country"] = country
        params["limit"] = limit
        params["offset"] = offset

        return await self.request(
            Route("GET", f"browse/categories/{category_id}/playlists", params)
        )

    async def get_recommendations(
        self,
        *,
        seed_artists: List[ID],
        seed_genres: List[str],
        seed_tracks: List[ID],
        limit: Optional[int] = 20,
        market: Optional[MARKETS] = None,
        min_acousticness: Optional[float] = None,
        max_acousticness: Optional[float] = None,
        target_acousticness: Optional[float] = None,
        min_danceability: Optional[float] = None,
        max_danceability: Optional[float] = None,
        target_danceability: Optional[float] = None,
        min_duration_ms: Optional[int] = None,
        max_duration_ms: Optional[int] = None,
        target_duration_ms: Optional[int] = None,
        min_energy: Optional[float] = None,
        max_energy: Optional[float] = None,
        target_energy: Optional[float] = None,
        min_instrumentalness: Optional[float] = None,
        max_instrumentalness: Optional[float] = None,
        target_instrumentalness: Optional[float] = None,
        min_key: Optional[int] = None,
        max_key: Optional[int] = None,
        target_key: Optional[int] = None,
        min_liveness: Optional[float] = None,
        max_liveness: Optional[float] = None,
        target_liveness: Optional[float] = None,
        min_loudness: Optional[float] = None,
        max_loudness: Optional[float] = None,
        target_loudness: Optional[float] = None,
        min_mode: Optional[int] = None,
        max_mode: Optional[int] = None,
        target_mode: Optional[int] = None,
        min_popularity: Optional[int] = None,
        max_popularity: Optional[int] = None,
        target_popularity: Optional[int] = None,
        min_speechiness: Optional[float] = None,
        max_speechiness: Optional[float] = None,
        target_speechiness: Optional[float] = None,
        min_tempo: Optional[float] = None,
        max_tempo: Optional[float] = None,
        target_tempo: Optional[float] = None,
        min_time_signature: Optional[int] = None,
        max_time_signature: Optional[int] = None,
        target_time_signature: Optional[int] = None,
        min_valence: Optional[float] = None,
        max_valence: Optional[float] = None,
        target_valence: Optional[float] = None,
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-recommendations

        params: PARAMS = {}
        params["seed_artists"] = seed_artists
        params["seed_genres"] = seed_genres
        params["seed_tracks"] = seed_tracks
        params["limit"] = limit
        params["market"] = market
        params["min_acousticness"] = min_acousticness
        params["max_acousticness"] = max_acousticness
        params["target_acousticness"] = target_acousticness
        params["min_danceability"] = min_danceability
        params["max_danceability"] = max_danceability
        params["target_danceability"] = target_danceability
        params["min_duration_ms"] = min_duration_ms
        params["max_duration_ms"] = max_duration_ms
        params["target_duration_ms"] = target_duration_ms
        params["min_energy"] = min_energy
        params["max_energy"] = max_energy
        params["target_energy"] = target_energy
        params["min_instrumentalness"] = min_instrumentalness
        params["max_instrumentalness"] = max_instrumentalness
        params["target_instrumentalness"] = target_instrumentalness
        params["min_key"] = min_key
        params["max_key"] = max_key
        params["target_key"] = target_key
        params["min_liveness"] = min_liveness
        params["max_liveness"] = max_liveness
        params["target_liveness"] = target_liveness
        params["min_loudness"] = min_loudness
        params["max_loudness"] = max_loudness
        params["target_loudness"] = target_loudness
        params["min_mode"] = min_mode
        params["max_mode"] = max_mode
        params["target_mode"] = target_mode
        params["min_popularity"] = min_popularity
        params["max_popularity"] = max_popularity
        params["target_popularity"] = target_popularity
        params["min_speechiness"] = min_speechiness
        params["max_speechiness"] = max_speechiness
        params["target_speechiness"] = target_speechiness
        params["min_tempo"] = min_tempo
        params["max_tempo"] = max_tempo
        params["target_tempo"] = target_tempo
        params["min_time_signature"] = min_time_signature
        params["max_time_signature"] = max_time_signature
        params["target_time_signature"] = target_time_signature
        params["min_valence"] = min_valence
        params["max_valence"] = max_valence

        for key, value in params.items():
            if value is None:
                params.pop(key)

        return await self.request(Route("GET", "recommendations", params))

    async def get_recommendation_genres(self) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-recommendation-genres

        return await self.request(Route("GET", "recommendations/available-genre-seeds"))

    # Episodes API (https://developer.spotify.com/documentation/web-api/reference/#category-episodes)

    async def get_multiple_episodes(
        self, ids: List[ID], *, market: Optional[MARKETS] = None
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-multiple-episodes

        params: PARAMS = {}
        if market:
            params["market"] = market

        return await self.request(Route("GET", "episodes", params))

    async def get_episode(
        self, id: ID, *, market: Optional[MARKETS] = None
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-an-episode

        params: PARAMS = {}
        if market:
            params["market"] = market

        return await self.request(Route("GET", f"episodes/{id}", params))

    # Follow API (https://developer.spotify.com/documentation/web-api/reference/#category-follow)
    # All routes are not covered since they can't be accessed with Client Credentials Grant

    async def check_if_users_follow_playlist(
        self, playlist_id: ID, ids: List[ID]
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-check-if-user-follows-playlist

        params: PARAMS = {"ids": ",".join(id for id in ids)}

        return await self.request(
            Route("GET", f"playlists/{playlist_id}/followers/contains", params)
        )

    # Library API (https://developer.spotify.com/documentation/web-api/reference/#category-library)
    # No routes are covered  for this endpoint since none of them can't be accessed with Client Credentials Grant

    # Markets API (https://developer.spotify.com/documentation/web-api/reference/#category-markets)

    async def get_available_markets(self) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-available-markets

        return await self.request(Route("GET", "markets"))

    # Personalization API (https://developer.spotify.com/documentation/web-api/reference/#category-personalization)
    # No routes are covered  for this endpoint since none of them can't be accessed with Client Credentials Grant

    # Player API (https://developer.spotify.com/documentation/web-api/reference/#category-player)
    # No routes are covered  for this endpoint since none of them can't be accessed with Client Credentials Grant

    # Playlists API (https://developer.spotify.com/documentation/web-api/reference/#category-playlists)

    async def get_user_playlists(
        self, user_id: ID, *, limit: Optional[int] = 20, offset: Optional[int] = 0
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-list-users-playlists

        params: PARAMS = {"limit": limit, "offset": offset}

        return await self.request(Route("GET", f"users/{user_id}/playlists", params))

    async def get_playlist(
        self,
        playlist_id: ID,
        *,
        market: Optional[MARKETS] = None,
        fields: Optional[str] = None,
        additional_types: Optional[List[Literal["track", "episode"]]] = None,
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-playlist

        params: PARAMS = {}
        if market:
            params["market"] = market
        if fields:
            params["fields"] = fields
        if additional_types:
            params["additional_types"] = ",".join(t for t in additional_types)

        return await self.request(Route("GET", f"playlists/{playlist_id}", params))

    async def get_playlist_items(
        self,
        playlist_id: ID,
        *,
        market: Optional[MARKETS] = None,
        limit: Optional[int] = 20,
        offset: Optional[int] = 0,
        fields: Optional[str] = None,
        additional_types: Optional[List[Literal["track", "episode"]]] = None,
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-playlists-tracks

        params: PARAMS = {}
        if market:
            params["market"] = market
        params["limit"] = limit
        params["offset"] = offset
        if fields:
            params["fields"] = fields
        if additional_types:
            params["additional_types"] = ",".join(t for t in additional_types)

        return await self.request(
            Route("GET", f"playlists/{playlist_id}/tracks", params)
        )

    # Search API (https://developer.spotify.com/documentation/web-api/reference/#category-search)

    async def search(
        self,
        query: str,
        _type: Literal["album", "artist", "playlist", "track", "show", "episode"],
        *,
        market: Optional[MARKETS] = None,
        limit: Optional[int] = 20,
        offset: Optional[int] = 0,
        include_external: Optional[Literal["audio"]] = None,
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-search

        params: PARAMS = {"query": query.replace(" ", "+"), "type": _type}
        if market:
            params["market"] = market
        params["limit"] = limit
        params["offset"] = offset
        if include_external:
            params["include_external"] = include_external

        return await self.request(Route("GET", "search", params))

    # Shows API (https://developer.spotify.com/documentation/web-api/reference/#category-shows)

    async def get_shows(
        self, ids: List[ID], *, market: Optional[MARKETS] = None
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#category-shows

        params: PARAMS = {"ids": ",".join(id for id in ids)}
        if market:
            params["market"] = market

        return await self.request(Route("GET", "shows", params))

    async def get_show(self, id: ID, *, market: Optional[MARKETS] = None) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-a-show

        params: PARAMS = {}
        if market:
            params["market"] = market

        return await self.request(Route("GET", f"shows/{id}", params))

    async def get_show_episodes(
        self,
        id: ID,
        *,
        market: Optional[MARKETS] = None,
        limit: Optional[int] = 20,
        offset: Optional[int] = 0,
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-a-shows-episodes

        params: PARAMS = {}
        if market:
            params["market"] = market
        params["limit"] = limit
        params["offset"] = offset

        return await self.request(Route("GET", f"shows/{id}/episodes", params))

    # Tracks API (https://developer.spotify.com/documentation/web-api/reference/#category-tracks)

    async def get_tracks(
        self, ids: List[ID], *, market: Optional[MARKETS] = None
    ) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-several-tracks

        params: PARAMS = {"ids": ",".join(id for id in ids)}
        if market:
            params["market"] = market

        return await self.request(Route("GET", "tracks", params))

    async def get_track(self, id: ID, *, market: Optional[MARKETS] = None) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-track

        params: PARAMS = {}
        if market:
            params["market"] = market

        return await self.request(Route("GET", f"tracks/{id}", params))

    async def get_audio_features_of_tracks(self, ids: List[ID]) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-several-audio-features

        params: PARAMS = {"ids": ",".join(id for id in ids)}

        return await self.request(Route("GET", "audio-features", params))

    async def get_audio_features_of_track(self, id: ID) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-audio-features

        return await self.request(Route("GET", f"audio-features/{id}"))

    async def get_audio_analysis_of_track(self, id: ID) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-audio-analysis

        return await self.request(Route("GET", f"audio-analysis/{id}"))

    # Users Profile API (https://developer.spotify.com/documentation/web-api/reference/#category-users-profile)

    async def get_user_profile(self, user_id: ID) -> RESPONSE:
        # https://developer.spotify.com/documentation/web-api/reference/#endpoint-get-users-profile

        return await self.request(Route("GET", f"users/{user_id}"))
