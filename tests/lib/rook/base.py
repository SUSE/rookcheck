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
import requests

from tests.config import settings, converter
from tests.lib import common
from tests.lib.common import execute
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class RookBase(ABC):
    def __init__(self, workspace, kubernetes):
        self._workspace = workspace
        self.kubernetes = kubernetes
        self.toolbox_pod = None
        self.ceph_dir = None
        self.rook_image = None
        self.build_dir = os.path.join(self.workspace.build_dir, 'rook')
        logger.info(f"rook init on {self.kubernetes.hardware}")

    @property
    def workspace(self):
        return self._workspace

    @abstractmethod
    def build(self):
        self.get_rook()

        self.get_golang()
        logger.info("Compiling rook...")
        execute(
            command=f"make --directory {self.build_dir} "
                    f"-j BUILD_REGISTRY='rook-build' IMAGES='ceph'",
            env={"PATH": f"{self.workspace.bin_dir}/go/bin:"
                         f"{os.environ['PATH']}",
                 "TMPDIR": self.workspace.tmp_dir,
                 "GOCACHE": self.workspace.tmp_dir,
                 "GOPATH": self.workspace.build_dir},
            log_stderr=False)

        logger.info(f"Tag image as {self.rook_image}")
        execute(f'docker tag "rook-build/ceph-amd64" {self.rook_image}')

        logger.info("Save image tar")
        # TODO(jhesketh): build arch may differ
        execute(f"docker save {self.rook_image} | gzip > %s"
                % os.path.join(self.build_dir, 'rook-ceph.tar.gz'))
        self._rook_built = True

    @abstractmethod
    def preinstall(self):
        if settings.OPERATOR_INSTALLER == "helm":
            self._get_helm()
            self._get_charts()

    def destroy(self, skip=True):
        if skip:
            # We can skip in most cases since the kubernetes cluster, if not
            # the nodes themselves will be destroyed instead.
            return

        if settings.as_bool('_TEAR_DOWN_CLUSTER_CONFIRM'):
            common.handle_cleanup_input("pause before cleanup rook")

        # TODO(jhesketh): Uninstall rook
        logger.info(f"rook destroy on {self.kubernetes.hardware}")
        pass

    def execute_in_ceph_toolbox(self, command, log_stdout=False):
        if not self.toolbox_pod:
            toolbox_pods = self.kubernetes.get_pods_by_app_label(
                "rook-ceph-tools")
            self.toolbox_pod = toolbox_pods[0]

        return self.kubernetes.execute_in_pod(
            command, self.toolbox_pod, log_stdout=False)

    @abstractmethod
    def get_rook(self):
        pass

    @abstractmethod
    def _get_charts(self):
        pass

    @abstractmethod
    def _get_helm(self):
        pass

    @abstractmethod
    def _install_operator_helm(self):
        pass

    @abstractmethod
    def upload_rook_image(self):
        if converter('@bool', settings.UPSTREAM_ROOK.BUILD_ROOK_FROM_GIT):
            pass
        else:
            return

    def install(self):
        self.kubernetes.kubectl("create namespace rook-ceph")
        self._install_operator()

        # CRDs are in an own file in rook >= 1.5
        if os.path.isfile(os.path.join(self.ceph_dir, 'crds.yaml')):
            self.kubernetes.kubectl_apply(
                os.path.join(self.ceph_dir, 'crds.yaml'))

        # reduce wait time to discover devices
        self.kubernetes.kubectl(
            "-n rook-ceph set env "
            "deployment/rook-ceph-operator ROOK_DISCOVER_DEVICES_INTERVAL=2m")

        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'cluster.yaml'))
        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'toolbox.yaml'))

        logger.info("Wait for OSD prepare to complete "
                    "(this may take a while...)")
        pattern = re.compile(r'.*rook-ceph-osd-prepare.*Completed')
        common.wait_for_result(
            self.kubernetes.kubectl, "-n rook-ceph get pods"
            " -l app=rook-ceph-osd-prepare",
            matcher=common.regex_count_matcher(pattern, 3),
            attempts=120, interval=15)

        logger.info("Wait for rook-ceph-tools running")
        pattern = re.compile(r'.*rook-ceph-tools.*Running')
        common.wait_for_result(
            self.kubernetes.kubectl, "-n rook-ceph get pods",
            matcher=common.regex_count_matcher(pattern, 1),
            attempts=30, interval=10)

        logger.info("Wait for Ceph HEALTH_OK")
        pattern = re.compile(r'.*HEALTH_OK')
        common.wait_for_result(
            self.execute_in_ceph_toolbox, "ceph status",
            matcher=common.regex_matcher(pattern),
            attempts=60, interval=10)

        logger.info("Rook successfully installed and ready!")

    def _install_operator(self):
        """
        Install operator using either kubectl of helm
        """
        if (settings.OPERATOR_INSTALLER == "helm" and not
                converter('@bool',
                          settings.UPSTREAM_ROOK.BUILD_ROOK_FROM_GIT)):
            logger.info('Deploying rook operator - using Helm')
            self._install_operator_helm()
        else:
            logger.info('Deploying rook operator - using kubectl apply ...')
            self._install_operator_kubectl()

        logger.info("Wait for rook-ceph-operator running")
        pattern = re.compile(r'.*rook-ceph-operator.*Running')
        common.wait_for_result(
            self.kubernetes.kubectl, "-n rook-ceph get pods",
            matcher=common.regex_count_matcher(pattern, 1),
            attempts=30, interval=10)

        # set operator log level
        self.kubernetes.kubectl(
            "--namespace rook-ceph set env "
            "deployment/rook-ceph-operator ROOK_LOG_LEVEL=DEBUG")

    def _install_operator_kubectl(self):
        logger.info('Deploying rook operator - using kubectl apply ...')
        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'common.yaml'))
        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'operator.yaml'))

    # TODO: need to check this in details
    # but Ceph features methods should belong to rook base class
    def deploy_rbd(self):
        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'csi/rbd/storageclass.yaml'))

    def deploy_filesystem(self):
        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'filesystem.yaml'))
        logger.info("Wait for 2 mdses to start")
        pattern = re.compile(r'.*rook-ceph-mds-myfs.*Running')
        common.wait_for_result(
            self.kubernetes.kubectl, "-n rook-ceph get pods",
            log_stdout=False,
            matcher=common.regex_count_matcher(pattern, 2),
            attempts=120, interval=10)

        logger.info("Wait for myfs to be active")
        pattern = re.compile(r'.*active')
        common.wait_for_result(
            self.execute_in_ceph_toolbox, "ceph fs status myfs",
            log_stdout=False,
            matcher=common.regex_matcher(pattern),
            attempts=120, interval=10)
        logger.info("Ceph FS successfully installed and ready!")

    def get_number_of_osds(self):
        # get number of osds
        osds = self.kubernetes.get_pods_by_app_label("rook-ceph-osd")
        osds = len(osds)
        logger.info("cluster has %s osd pods running", osds)
        return osds

    def get_number_of_mons(self):
        # get number of mons
        mons = self.kubernetes.get_pods_by_app_label("rook-ceph-mon")
        mons = len(mons)
        logger.info("cluster has %s mon pods running", mons)
        return mons

    def get_golang(self):
        url = 'https://golang.org/VERSION?m=text'
        version = requests.get(url).content.decode("utf-8")
        self.workspace.get_unpack(
            "https://dl.google.com/go/%s.linux-amd64.tar.gz" % version,
            unpack_folder=self.workspace.bin_dir
        )

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy(skip=not settings.as_bool('_TEAR_DOWN_CLUSTER'))
