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
from dynaconf.utils.parse_conf import get_converter


settings_dir = os.path.realpath(os.path.join(
    pathlib.Path(__file__).parent.absolute(), '../config'))

settings = Dynaconf(
    envvar_prefix='ROOKCHECK',
    load_dotenv=True,
    settings_files=[
        os.path.join(settings_dir, 'settings.toml'),
        os.path.join(settings_dir, 'openstack.toml'),
        os.path.join(settings_dir, 'libvirt.toml'),
        os.path.join(settings_dir, 'aws_ec2.toml'),
        os.path.join(settings_dir, 'rook_upstream.toml'),
        os.path.join(settings_dir, 'ses.toml'),
    ],
)


# NOTE(jhesketh): Dynaconf's casting does not handle nested dicts properly.
#                 Instead provide the converter to use directly.
def converter(converter_key, value, box_settings=None):
    return get_converter(converter_key, value, box_settings)
