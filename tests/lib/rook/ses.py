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

import logging
import os

from tests.lib.common import execute, recursive_replace
from tests.lib.rook.base import RookBase

from tests.config import settings

logger = logging.getLogger(__name__)


class RookSes(RookBase):
    def __init__(self, workspace, kubernetes):
        super().__init__(workspace, kubernetes)
        self.ceph_dir = os.path.join(
            self.workspace.working_dir, 'rook', 'ceph')

    def build(self):
        super().build()
        logger.info('SES based rook does not require building')

    def preinstall(self):
        super().preinstall()
        repo_vars = {
            'ses_repositories':
                settings(f'SES.{settings.SES.TARGET}.repositories')
        }
        self.kubernetes.hardware.ansible_run_playbook(
            'playbook_rook_ses.yaml', extra_vars=repo_vars)
        self._get_rook_files()
        self._fix_yaml()

    def _get_rook_files(self):
        # TODO (bleon)
        # This is not optima. Need to retrieve RPM directly and extract files
        # out of it. RPM URL should be configurable
        execute(f"rsync -avr -e 'ssh -i {self.workspace.private_key}'"
                f" {settings.NODE_IMAGE_USER}"
                f"@{self.kubernetes.hardware.masters[0].get_ssh_ip()}"
                f":/usr/share/k8s-yaml/rook {self.workspace.working_dir}")

    def _fix_yaml(self):
        # Replacements are to point container paths and/or versions to the
        # expected ones to test.
        replacements = settings(
            f'SES.{settings.SES.TARGET}.yaml_substitutions')
        recursive_replace(self.ceph_dir, replacements)
