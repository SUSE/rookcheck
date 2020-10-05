# Copyright (c) 2019 SUSE LINUX GmbH
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import pathlib

from dynaconf import Dynaconf


settings_dir = os.path.realpath(os.path.join(
    pathlib.Path(__file__).parent.absolute(), '../config'))

settings = Dynaconf(
    ENVVAR_PREFIX_FOR_DYNACONF='ROOKCHECK',
    settings_files=[
        os.path.join(settings_dir, 'settings.toml'),
        os.path.join(settings_dir, 'openstack.toml'),
        os.path.join(settings_dir, 'aws_ec2.toml'),
        os.path.join(settings_dir, 'rook_upstream.toml'),
        os.path.join(settings_dir, 'ses.toml'),
    ],
)
