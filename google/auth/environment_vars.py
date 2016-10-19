# Copyright 2016 Google Inc.
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

"""Environment variables used by google.auth."""


PROJECT = 'GOOGLE_CLOUD_PROJECT'
"""Environment variable defining default project."""

CREDENTIALS = 'GOOGLE_APPLICATION_CREDENTIALS'
"""Environment variable defining the location of Google application default
credentials."""

# The environment variable name which can replace ~/.config if set.
CLOUD_SDK_CONFIG_DIR = 'CLOUDSDK_CONFIG'
"""Environment variable defines the location of Google Cloud SDK's config
files."""