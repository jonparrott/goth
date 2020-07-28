# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Transport adapter for Async HTTP (aiohttp)."""

from __future__ import absolute_import

import asyncio
import functools
import logging


import aiohttp
import six


from google.auth import exceptions
from google.auth import transport
from google.auth.transport import requests


_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/appengine.apis",
    "https://www.googleapis.com/auth/userinfo.email",
]

_LOGGER = logging.getLogger(__name__)

# Timeout can be re-defined depending on async requirement. Currently made 60s more than
# sync timeout.
_DEFAULT_TIMEOUT = 180  # in seconds


class _Response(transport.Response):
    """
    Requests transport response adapter.

    Args:
        response (requests.Response): The raw Requests response.
    """

    def __init__(self, response):
        self._response = response

    @property
    def status(self):
        return self._response.status

    @property
    def headers(self):
        return self._response.headers

    @property
    def data(self):
        return self._response.content


class Request(transport.Request):
    """Requests request adapter.

    This class is used internally for making requests using asyncio transports
    in a consistent way. If you use :class:`AuthorizedSession` you do not need
    to construct or use this class directly.

    This class can be useful if you want to manually refresh a
    :class:`~google.auth.credentials.Credentials` instance::

        import google.auth.transport.aiohttp_req
        import aiohttp

        request = google.auth.transport.aiohttp_req.Request()

        credentials.refresh(request)

    Args:
        session (aiohttp.ClientSession): An instance :class: aiohttp.ClientSession used
            to make HTTP requests. If not specified, a session will be created.

    .. automethod:: __call__
    """

    def __init__(self, session=None):

        self.session = None

    async def __call__(
        self,
        url,
        method="GET",
        body=None,
        headers=None,
        timeout=_DEFAULT_TIMEOUT,
        **kwargs
    ):
        """
        Make an HTTP request using aiohttp.

        Args:
            url (str): The URI to be requested.
            method (str): The HTTP method to use for the request. Defaults
                to 'GET'.
            body (bytes): The payload / body in HTTP request.
            headers (Mapping[str, str]): Request headers.
            timeout (Optional[int]): The number of seconds to wait for a
                response from the server. If not specified or if None, the
                requests default timeout will be used.
            kwargs: Additional arguments passed through to the underlying
                requests :meth:`~requests.Session.request` method.

        Returns:
            google.auth.transport.Response: The HTTP response.

        Raises:
            google.auth.exceptions.TransportError: If any exception occurred.
        """

        try:
            if self.session is None:  # pragma: NO COVER
                self.session = aiohttp.ClientSession()  # pragma: NO COVER
            _LOGGER.debug("Making request: %s %s", method, url)
            response = await self.session.request(
                method, url, data=body, headers=headers, timeout=timeout, **kwargs
            )
            return _Response(response)

        except aiohttp.ClientError as caught_exc:
            new_exc = exceptions.TransportError(caught_exc)
            six.raise_from(new_exc, caught_exc)

        except asyncio.TimeoutError as caught_exc:
            new_exc = exceptions.TransportError(caught_exc)
            six.raise_from(new_exc, caught_exc)


class AuthorizedSession(aiohttp.ClientSession):
    """This is an async implementation of the Authorized Session class. We utilize an
    aiohttp transport instance, and the interface mirrors the google.auth.transport.requests
    Authorized Session class, except for the change in the transport used in the async use case.

    A Requests Session class with credentials.

    This class is used to perform requests to API endpoints that require
    authorization::

        import google.auth.transport.aiohttp_req

        async with aiohttp_req.AuthorizedSession(credentials) as authed_session:
            response = await authed_session.request(
                'GET', 'https://www.googleapis.com/storage/v1/b')

    The underlying :meth:`request` implementation handles adding the
    credentials' headers to the request and refreshing credentials as needed.

    Args:
        credentials (google.auth.credentials_async.Credentials): The credentials to
            add to the request.
        refresh_status_codes (Sequence[int]): Which HTTP status codes indicate
            that credentials should be refreshed and the request should be
            retried.
        max_refresh_attempts (int): The maximum number of times to attempt to
            refresh the credentials and retry the request.
        refresh_timeout (Optional[int]): The timeout value in seconds for
            credential refresh HTTP requests.
        auth_request (google.auth.transport.aiohttp_req.Request):
            (Optional) An instance of
            :class:`~google.auth.transport.aiohttp_req.Request` used when
            refreshing credentials. If not passed,
            an instance of :class:`~google.auth.transport.aiohttp_req.Request`
            is created.
    """

    def __init__(
        self,
        credentials,
        refresh_status_codes=transport.DEFAULT_REFRESH_STATUS_CODES,
        max_refresh_attempts=transport.DEFAULT_MAX_REFRESH_ATTEMPTS,
        refresh_timeout=None,
        auth_request=None,
    ):
        super(AuthorizedSession, self).__init__()
        self.credentials = credentials
        self._refresh_status_codes = refresh_status_codes
        self._max_refresh_attempts = max_refresh_attempts
        self._refresh_timeout = refresh_timeout
        self._is_mtls = False
        self._auth_request = auth_request
        self._auth_request_session = None
        self._loop = asyncio.get_event_loop()
        self._refresh_lock = asyncio.Lock()

    async def request(
        self,
        method,
        url,
        data=None,
        headers=None,
        max_allowed_time=None,
        timeout=_DEFAULT_TIMEOUT,
        **kwargs
    ):

        """Implementation of Authorized Session aiohttp request.

        Args:
            method: The http request method used (e.g. GET, PUT, DELETE)

            url: The url at which the http request is sent.

            data, headers: These fields parallel the associated data and headers
            fields of a regular http request. Using the aiohttp client session to
            send the http request allows us to use this parallel corresponding structure
            in our Authorized Session class.

            timeout (Optional[Union[float, Tuple[float, float]]]):
                The amount of time in seconds to wait for the server response
                with each individual request.

                Can also be passed as a tuple (connect_timeout, read_timeout).
                See :meth:`requests.Session.request` documentation for details.

            max_allowed_time (Optional[float]):
                If the method runs longer than this, a ``Timeout`` exception is
                automatically raised. Unlike the ``timeout` parameter, this
                value applies to the total method execution time, even if
                multiple requests are made under the hood.

                Mind that it is not guaranteed that the timeout error is raised
                at ``max_allowed_time`. It might take longer, for example, if
                an underlying request takes a lot of time, but the request
                itself does not timeout, e.g. if a large file is being
                transmitted. The timout error will be raised after such
                request completes.
        """

        async with aiohttp.ClientSession() as self._auth_request_session:
            auth_request = Request(self._auth_request_session)
            self._auth_request = auth_request

            # Use a kwarg for this instead of an attribute to maintain
            # thread-safety.
            _credential_refresh_attempt = kwargs.pop("_credential_refresh_attempt", 0)
            # Make a copy of the headers. They will be modified by the credentials
            # and we want to pass the original headers if we recurse.
            request_headers = headers.copy() if headers is not None else {}

            # Do not apply the timeout unconditionally in order to not override the
            # _auth_request's default timeout.
            auth_request = (
                self._auth_request
                if timeout is None
                else functools.partial(self._auth_request, timeout=timeout)
            )

            remaining_time = max_allowed_time

            with requests.TimeoutGuard(remaining_time, asyncio.TimeoutError) as guard:
                await self.credentials.before_request(
                    auth_request, method, url, request_headers
                )

            with requests.TimeoutGuard(remaining_time, asyncio.TimeoutError) as guard:
                response = await super(AuthorizedSession, self).request(
                    method,
                    url,
                    data=data,
                    headers=request_headers,
                    timeout=timeout,
                    **kwargs
                )

            remaining_time = guard.remaining_timeout

            if (
                response.status in self._refresh_status_codes
                and _credential_refresh_attempt < self._max_refresh_attempts
            ):

                _LOGGER.info(
                    "Refreshing credentials due to a %s response. Attempt %s/%s.",
                    response.status,
                    _credential_refresh_attempt + 1,
                    self._max_refresh_attempts,
                )

                # Do not apply the timeout unconditionally in order to not override the
                # _auth_request's default timeout.
                auth_request = (
                    self._auth_request
                    if timeout is None
                    else functools.partial(self._auth_request, timeout=timeout)
                )

                with requests.TimeoutGuard(
                    remaining_time, asyncio.TimeoutError
                ) as guard:
                    async with self._refresh_lock:
                        await self._loop.run_in_executor(
                            None, self.credentials.refresh, auth_request
                        )

                remaining_time = guard.remaining_timeout

                return await self.request(
                    method,
                    url,
                    data=data,
                    headers=headers,
                    max_allowed_time=remaining_time,
                    timeout=timeout,
                    _credential_refresh_attempt=_credential_refresh_attempt + 1,
                    **kwargs
                )

        return response