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

"""Identity Pool Credentials.

This module provides credentials that are initialized using external_account
arguments which are typically loaded from the external credentials file.
Unlike other Credentials that can be initialized with a list of explicit
arguments, secrets or credentials, external account clients use the
environment and hints/guidelines provided by the external_account JSON
file to retrieve credentials and exchange them for Google access tokens.

Identity Pool Credentials are used with external credentials (eg. OIDC
ID tokens) retrieved from a file location, typical for K8s workloads
registered with Hub with Hub workload identity enabled.
"""

import io
import json
import os

from google.auth import _helpers
from google.auth import exceptions
from google.auth import external_account
from six.moves import http_client
from six.moves import urllib


class Credentials(external_account.Credentials):
    """File-sourced external account credentials.
    This is typically used to exchange OIDC ID tokens in K8s (file-sourced
    credentials) for Google access tokens.
    """

    def __init__(
        self,
        audience,
        subject_token_type,
        token_url,
        credential_source,
        service_account_impersonation_url=None,
        client_id=None,
        client_secret=None,
        quota_project_id=None,
        scopes=None,
        success_codes=(http_client.OK,),
    ):
        """Instantiates a file-sourced external account credentials object.

        Args:
            audience (str): The STS audience field.
            subject_token_type (str): The subject token type.
            token_url (str): The STS endpoint URL.
            credential_source (Mapping): The credential source dictionary used to
                provide instructions on how to retrieve external credential to be
                exchanged for Google access tokens..
            service_account_impersonation_url (Optional[str]): The optional service account
                impersonation getAccessToken URL.
            client_id (Optional[str]): The optional client ID.
            client_secret (Optional[str]): The optional client secret.
            quota_project_id (Optional[str]): The optional quota project ID.
            scopes (Optional[Sequence[str]]): Optional scopes to request during the
                authorization grant.

        Raises:
            google.auth.exceptions.RefreshError: If an error is encountered during
                access token retrieval logic.
            ValueError: For invalid parameters.

        .. note:: Typically one of the helper constructors
            :meth:`from_file` or
            :meth:`from_info` are used instead of calling the constructor directly.
        """

        super(Credentials, self).__init__(
            audience=audience,
            subject_token_type=subject_token_type,
            token_url=token_url,
            credential_source=credential_source,
            service_account_impersonation_url=service_account_impersonation_url,
            client_id=client_id,
            client_secret=client_secret,
            quota_project_id=quota_project_id,
            scopes=scopes,
        )
        if not isinstance(credential_source, dict):
            self._credential_source_file = None
            self._credential_source_url = None
        else:
            self._credential_source_file = credential_source.get("file")
            self._credential_source_url = credential_source.get("url")
            self._credential_source_headers = credential_source.get("headers")
            self._success_codes = success_codes
            credential_source_format = credential_source.get("format") or {}
            # Get credential_source format type. When not provided, this
            # defaults to text.
            self._credential_source_format_type = (
                credential_source_format.get("type") or "text"
            )
            if self._credential_source_format_type not in ["text", "json"]:
                raise ValueError(
                    "Invalid credential_source format '{}'".format(
                        self._credential_source_format_type
                    )
                )
            # For JSON types, get the required subject_token field name.
            if self._credential_source_format_type == "json":
                self._credential_source_field_name = credential_source_format.get(
                    "subject_token_field_name"
                )
                if self._credential_source_field_name is None:
                    raise ValueError(
                        "Missing subject_token_field_name for JSON credential_source format"
                    )
            else:
                self._credential_source_field_name = None

        if self._credential_source_file and self._credential_source_url:
            raise ValueError("Ambiguous credential_source")
        if not self._credential_source_file and not self._credential_source_url:
            raise ValueError("Missing credential_source")

    @_helpers.copy_docstring(external_account.Credentials)
    def retrieve_subject_token(self, request):
        return self._parse_token_data(
            self._get_token_data(),
            self._credential_source_format_type,
            self._credential_source_field_name,
        )

    def _get_token_data(self):
        if self._credential_source_file:
            return self._get_file_data(self._credential_source_file)
        if self._credential_source_url:
            return self._get_url_data(self._credential_source_url)

    def _get_file_data(self, filename):
        if not os.path.exists(filename):
            raise exceptions.RefreshError("File '{}' was not found.".format(filename))

        with io.open(filename, "r", encoding="utf-8") as file_obj:
            return file_obj.read(), filename

    def _get_url_data(self, url):
        response = urllib.request.urlopen(url)
        if response.status not in self._success_codes:
            raise exceptions.RefreshError("Url '{}' was not found.".format(url))
        return response.read(), url

    def _parse_token_data(
        self,
        token_content,
        format_type="text",
        subject_token_field_name=None
    ):
        content, filename = token_content
        if format_type == "text":
            token = content
        else:
            try:
                # Parse file content as JSON.
                response_data = json.loads(content)
                # Get the subject_token.
                token = response_data[subject_token_field_name]
            except (KeyError, ValueError):
                raise exceptions.RefreshError(
                    "Unable to parse subject_token from JSON file '{}' using key '{}'".format(
                        filename, subject_token_field_name
                    )
                )
        if not token:
            raise exceptions.RefreshError(
                "Missing subject_token in the credential_source file"
            )
        return token

    @classmethod
    def from_info(cls, info, **kwargs):
        """Creates an Identity Pool Credentials instance from parsed external account info.

        Args:
            info (Mapping[str, str]): The Identity Pool external account info in Google
                format.
            kwargs: Additional arguments to pass to the constructor.

        Returns:
            google.auth.identity_pool.Credentials: The constructed
                credentials.

        Raises:
            ValueError: For invalid parameters.
        """
        return cls(
            audience=info.get("audience"),
            subject_token_type=info.get("subject_token_type"),
            token_url=info.get("token_url"),
            service_account_impersonation_url=info.get(
                "service_account_impersonation_url"
            ),
            client_id=info.get("client_id"),
            client_secret=info.get("client_secret"),
            credential_source=info.get("credential_source"),
            quota_project_id=info.get("quota_project_id"),
            **kwargs
        )

    @classmethod
    def from_file(cls, filename, **kwargs):
        """Creates an IdentityPool Credentials instance from an external account json file.

        Args:
            filename (str): The path to the IdentityPool external account json file.
            kwargs: Additional arguments to pass to the constructor.

        Returns:
            google.auth.identity_pool.Credentials: The constructed
                credentials.
        """
        with io.open(filename, "r", encoding="utf-8") as json_file:
            data = json.load(json_file)
            return cls.from_info(data, **kwargs)
