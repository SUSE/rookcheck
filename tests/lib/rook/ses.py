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
import filecmp
import time
import re

from tests.lib import common
from tests.lib.common import execute
from tests.lib.rook.base import RookBase

logger = logging.getLogger(__name__)


class RookSes(RookBase):
    def __init__(self, workspace, kubernetes):
        super().__init__(workspace, kubernetes)
        self.ceph_dir = os.path.join(
            self.workspace.working_dir, 'rook', 'ceph')

    def _get_rook_files(self):
        # TODO (bleon)
        # This is not optima. Need to retrieve RPM directly and extract files
        # out of it. RPM URL should be configurable
        execute(f"rsync -avr -e 'ssh -i {self.workspace.private_key}'"
                f" sles@{self.kubernetes.hardware.masters[0].get_ssh_ip()}"
                f":/usr/share/k8s-yaml/rook {self.workspace.working_dir}")

    # TODO: DISCUSS how to handle registry.suse.com vs registry.suse.de
    def _fix_yaml(self):
        # 'suse.com': 'suse.de/devel/storage/7.0/containers',
        replacements = {
            'suse.com': 'suse.de/suse/containers/ses/6/containers',
            '# ROOK_CSI_CEPH_IMAGE': 'ROOK_CSI_CEPH_IMAGE'
        }
        for root, dirs, files in os.walk(self.ceph_dir):
            for name in files:
                src = os.path.join(root, name)
                tmp = os.path.join(root, f'{name}_tmp')
                with open(src, 'r') as f:
                    lines = f.readlines()
                with open(tmp, 'w') as f:
                    for line in lines:
                        for k, v in replacements.items():
                            line = line.replace(k, v)
                        f.write(line)
                if filecmp.cmp(src, tmp):
                    os.remove(tmp)
                else:
                    os.rename(src, f'{src}.back')
                    os.rename(tmp, src)

    def preinstall(self):
        self.kubernetes.hardware.ansible_run_playbook('playbook_ses.yaml')
        self._get_rook_files()
        self._fix_yaml()

    def install(self):
        # TODO(jhesketh): We may want to provide ways for tests to override
        #                 these
        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'common.yaml'))
        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'operator.yaml'))

        # TODO(jhesketh): Check if sleeping is necessary
        time.sleep(10)

        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'cluster.yaml'))
        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'toolbox.yaml'))

        logger.info("Wait for OSD prepare to complete "
                    "(this may take a while...)")
        pattern = re.compile(r'.*rook-ceph-osd-prepare.*Completed')

        common.wait_for_result(
            self.kubernetes.kubectl, "--namespace rook-ceph get pods",
            matcher=common.regex_count_matcher(pattern, 3),
            attempts=90, interval=10)

        logger.info("Wait for Ceph HEALTH_OK")
        pattern = re.compile(r'.*HEALTH_OK')

        common.wait_for_result(
            self.execute_in_ceph_toolbox, "ceph status",
            matcher=common.regex_matcher(pattern),
            attempts=20, interval=5)

        logger.info("Rook successfully installed and ready!")
