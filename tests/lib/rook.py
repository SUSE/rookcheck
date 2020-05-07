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
import re
import subprocess
import time
import wget

from tests import config
from tests.lib import common


logger = logging.getLogger(__name__)


class UploadRook():
    def upload_image_play(self, buildpath):
        tasks = []

        tasks.append(
            dict(
                name="Copy Rook Ceph image to cluster nodes",
                action=dict(
                    module='copy',
                    args=dict(
                        src=os.path.join(buildpath, "rook-ceph.tar.gz"),
                        dest="/root/.images/"
                    )
                )
            )
        )

        # TODO(jhesketh): build arch may differ
        tasks.append(
            dict(
                name="Load rook ceph image",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd='docker load '
                            '--input /root/.images/rook-ceph.tar.gz'
                    )
                )
            )
        )

        play_source = dict(
            name="Upload rook image",
            hosts="all",
            tasks=tasks,
            gather_facts="no",
            # Temporary workaround for mitogen failing to copy files or
            # templates.
            strategy="free" if config._USE_FREE_STRATEGY else "linear",
        )
        return play_source


class RookCluster():
    def __init__(self, kubernetes):
        self.kubernetes = kubernetes
        self.toolbox_pod = None
        self.ceph_dir = None
        self._rook_built = False
        self.builddir = os.path.join(
            self.kubernetes.hardware.working_dir, 'rook_build')
        os.mkdir(self.builddir)

        logger.info(f"rook init on {self.kubernetes.hardware}")

    def destroy(self, skip=True):
        logger.info(f"rook destroy on {self.kubernetes.hardware}")
        if skip:
            # We can skip in most cases since the kubernetes cluster, if not
            # the nodes themselves will be destroyed instead.
            return
        # TODO(jhesketh): Uninstall rook
        pass

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy()

    def build_rook(self):
        def _execute(command):
            try:
                out = subprocess.run(
                    command,
                    shell=True, check=True, universal_newlines=True,
                    capture_output=True
                )
            except subprocess.CalledProcessError as e:
                logger.exception(f"Command `{command}` failed")
                logger.error(f"STDOUT: {e.stdout}")
                logger.error(f"STDERR: {e.stderr}")
                raise
            return out

        logger.info("[build_rook] Download go")
        wget.download(
            "https://dl.google.com/go/go1.13.9.linux-amd64.tar.gz",
            os.path.join(self.builddir, 'go-amd64.tar.gz')
        )

        logger.info("[build_rook] Unpack go")
        _execute(
            "tar -C %s -xzf %s"
            % (self.builddir, os.path.join(self.builddir, 'go-amd64.tar.gz'))
        )

        # TODO(jhesketh): Allow setting rook version
        logger.info("[build_rook] Checkout rook")
        _execute(
            "mkdir -p %s"
            % os.path.join(self.builddir, 'src/github.com/rook/rook')
        )
        _execute(
            "git clone https://github.com/rook/rook.git %s"
            % os.path.join(self.builddir, 'src/github.com/rook/rook')
        )
        # TODO(jhesketh): Allow testing various versions of rook
        _execute(
            "pushd %s && git checkout v1.3.1 && popd"
            % os.path.join(self.builddir, 'src/github.com/rook/rook')
        )

        logger.info("[build_rook] Make rook")
        _execute(
            "PATH={builddir}/go/bin:$PATH GOPATH={builddir} "
            "make --directory='{builddir}/src/github.com/rook/rook' "
            "-j BUILD_REGISTRY='rook-build' IMAGES='ceph' "
            "build".format(builddir=self.builddir)
        )

        logger.info("[build_rook] Tag image")
        _execute('docker tag "rook-build/ceph-amd64" rook/ceph:master')

        logger.info("[build_rook] Save image tar")
        # TODO(jhesketh): build arch may differ
        _execute(
            "docker save rook/ceph:master | gzip > %s"
            % os.path.join(self.builddir, 'rook-ceph.tar.gz')
        )

        self.ceph_dir = os.path.join(
            self.builddir,
            'src/github.com/rook/rook/cluster/examples/kubernetes/ceph'
        )

        self._rook_built = True

    def upload_rook_image(self):
        d = UploadRook()

        r = self.kubernetes.hardware.execute_ansible_play(
            d.upload_image_play(self.builddir))

        if r.host_failed or r.host_unreachable:
            # TODO(jhesketh): Provide some more useful feedback and/or checking
            raise Exception("One or more hosts failed")

    def install_rook(self):
        if not self._rook_built:
            raise Exception("Rook must be built before being installed")
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

        time.sleep(10)

        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'csi/rbd/storageclass.yaml'))

        logger.info("Wait for OSD prepare to complete "
                    "(this may take a while...)")
        pattern = re.compile(r'.*rook-ceph-osd-prepare.*Completed')

        common.wait_for_result(
            self.kubernetes.kubectl, "--namespace rook-ceph get pods",
            matcher=common.regex_count_matcher(pattern, 3),
            attempts=90, interval=10)

        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'filesystem.yaml'))

        logger.info("Wait for 2 mdses to start")
        pattern = re.compile(r'.*rook-ceph-mds-myfs.*Running')

        common.wait_for_result(
            self.kubernetes.kubectl, "--namespace rook-ceph get pods",
            matcher=common.regex_count_matcher(pattern, 2),
            attempts=20, interval=5)

        logger.info("Wait for myfs to be active")
        pattern = re.compile(r'.*active')

        common.wait_for_result(
            self.execute_in_ceph_toolbox, "ceph fs status myfs",
            matcher=common.regex_matcher(pattern),
            attempts=20, interval=5)

    def execute_in_ceph_toolbox(self, command):
        if not self.toolbox_pod:
            self.toolbox_pod = self.kubernetes.get_pod_by_app_label(
                "rook-ceph-tools")

        return self.kubernetes.execute_in_pod(command, self.toolbox_pod)
