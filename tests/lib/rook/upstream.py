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
import wget


from tests.config import settings
from tests.lib.common import execute
from tests.lib.rook.base import RookBase

logger = logging.getLogger(__name__)


class RookCluster(RookBase):
    def __init__(self, workspace, kubernetes):
        super().__init__(workspace, kubernetes)
        self._rook_built = False
        self.builddir = os.path.join(self.workspace.working_dir, 'rook_build')
        os.mkdir(self.builddir)
        self.go_tmpdir = os.path.join(self.workspace.working_dir, 'tmp')
        os.mkdir(self.go_tmpdir)

    def build(self):
        super().build()
        logger.info("[build_rook] Download go")
        wget.download(
            "https://dl.google.com/go/go1.13.9.linux-amd64.tar.gz",
            os.path.join(self.builddir, 'go-amd64.tar.gz'),
            bar=None,
        )

        logger.info("[build_rook] Unpack go")
        execute(
            "tar -C %s -xzf %s"
            % (self.builddir, os.path.join(self.builddir, 'go-amd64.tar.gz'))
        )

        # TODO(jhesketh): Allow setting rook version
        logger.info("[build_rook] Checkout rook")
        execute(
            "mkdir -p %s"
            % os.path.join(self.builddir, 'src/github.com/rook/rook')
        )
        execute(
            "git clone https://github.com/rook/rook.git %s"
            % os.path.join(self.builddir, 'src/github.com/rook/rook'),
            log_stderr=False
        )
        # TODO(jhesketh): Allow testing various versions of rook
        execute(
            "cd %s && git checkout v1.3.1"
            % os.path.join(self.builddir, 'src/github.com/rook/rook'),
            log_stderr=False
        )

        if settings.as_bool('BUILD_ROOK_FROM_GIT'):
            logger.info("[build_rook] Make rook")
            execute(
                "PATH={builddir}/go/bin:$PATH GOPATH={builddir} "
                "TMPDIR={tmpdir} "
                "make --directory='{builddir}/src/github.com/rook/rook' "
                "-j BUILD_REGISTRY='rook-build' IMAGES='ceph' "
                "build".format(builddir=self.builddir,
                            tmpdir=self.go_tmpdir),
                log_stderr=False,
                logger_name="make -j BUILD_REGISTRY='rook-build' IMAGES='ceph'",
            )

            logger.info("[build_rook] Tag image")
            execute('docker tag "rook-build/ceph-amd64" rook/ceph:master')

            logger.info("[build_rook] Save image tar")
            # TODO(jhesketh): build arch may differ
            execute(
                "docker save rook/ceph:master | gzip > %s"
                % os.path.join(self.builddir, 'rook-ceph.tar.gz')
            )

        self.ceph_dir = os.path.join(
            self.builddir,
            'src/github.com/rook/rook/cluster/examples/kubernetes/ceph'
        )

        self._rook_built = True

    def preinstall(self):
        super().preinstall()
        if not settings.as_bool('BUILD_ROOK_FROM_GIT'):
            return
        self.upload_rook_image()

    def upload_rook_image(self):
        self.kubernetes.hardware.ansible_run_playbook("playbook_rook.yaml")
