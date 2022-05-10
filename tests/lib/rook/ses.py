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
            self.workspace.working_dir, 'rook/ceph')
        self.helm_dir = os.path.join(
            self.workspace.working_dir, 'helm/rook-ceph')
        self.rook_chart = settings(
            f"SES.{settings.SES.TARGET}.rook_ceph_chart")

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
        self._get_rook()
        self._fix_yaml()
        self.enable_discovery_daemon()
        self._fix_chart_values()

    def _get_rook(self):
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

    def _fix_chart_values(self):
        # Replacements are to point container paths and/or versions to the
        # expected ones to test.
        replacements = settings(
            f'SES.{settings.SES.TARGET}.helm_values_substitutions')
        recursive_replace(self.helm_dir, replacements)

    def enable_discovery_daemon(self):
        replacements = {
            "enableDiscoveryDaemon: false": "enableDiscoveryDaemon: true",
        }
        recursive_replace(self.helm_dir, replacements)

    def _get_charts(self):
        super()._get_charts()
        logger.info(f"Grabbing chart {self.rook_chart}")
        # self.kubernetes.helm(f"chart pull {self.rook_chart}")
        self.kubernetes.helm(f"chart export {self.rook_chart}"
                             f" -d {self.workspace.helm_dir}")

    def _get_helm(self):
        super()._get_helm()
        logger.info('Helm binary is installed via package on ses')

    def _install_operator_helm(self):
        logger.info(
            "Installing rook operator with helm "
            f"{self.workspace.helm_dir}/rook-ceph with values"
            f"{self.workspace.helm_dir}/rook-ceph/values.yaml"
        )
        self.kubernetes.helm(
            f"install -n rook-ceph rook-ceph "
            f"{self.workspace.helm_dir}/rook-ceph"
            f" -f {self.workspace.helm_dir}/rook-ceph/values.yaml")
