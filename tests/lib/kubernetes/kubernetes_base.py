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


# This module should take care of deploying kubernetes. There will likely be
# multiple variations of an abstract base class to do so. However, the
# implementation may need to require a certain base OS. For example, skuba
# would require SLE and can raise an exception if that isn't provided.

from abc import ABC, abstractmethod
import os
import subprocess
import kubernetes
import logging

from tests.lib.hardware.hardware_base import HardwareBase
from tests.lib.workspace import Workspace


logger = logging.getLogger(__name__)


class KubernetesBase(ABC):
    def __init__(self, workspace: Workspace, hardware: HardwareBase):
        self._workspace = workspace
        self._hardware = hardware
        # TODO(toabctl): Make it configurable?
        self._kubeconfig = os.path.join(self.workspace.working_dir,
                                        'kubeconfig')
        self._kubectl_exec = os.path.join(
            self.workspace.working_dir, 'kubectl')
        self.v1 = None
        logger.info(f"kube init on hardware {self.hardware}")

    @abstractmethod
    def install_kubernetes(self):
        pass

    @property
    def workspace(self):
        return self._workspace

    @property
    def hardware(self):
        return self._hardware

    @property
    def kubeconfig(self):
        return self._kubeconfig

    @property
    def kubectl_exec(self):
        return self._kubectl_exec

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy()

    def _configure_kubernetes_client(self):
        kubernetes.config.load_kube_config(self.kubeconfig)
        self.v1 = kubernetes.client.CoreV1Api()

    def kubectl(self, command, surpress_logging=False):
        """
        Run a kubectl command
        """
        try:
            out = subprocess.run(
                "%s --kubeconfig %s %s"
                % (self.kubectl_exec, self.kubeconfig, command),
                shell=True, check=True, universal_newlines=True,
                capture_output=True
            )
        except subprocess.CalledProcessError as e:
            if not surpress_logging:
                logger.exception(f"Command `{command}` failed")
                logger.error(f"STDOUT: {e.stdout}")
                logger.error(f"STDERR: {e.stderr}")
            raise
        return out

    def kubectl_apply(self, yaml_file):
        return self.kubectl("apply -f %s" % yaml_file)

    def untaint_master(self):
        self.kubectl(
            "taint nodes --all node-role.kubernetes.io/master-",
            surpress_logging=True
        )

    def execute_in_pod(self, command, pod, namespace="rook-ceph"):
        return self.kubectl(
            '--namespace %s exec -t "%s" -- bash -c "$(cat <<\'EOF\'\n'
            '%s'
            '\nEOF\n)"'
            % (namespace, pod, command)
        )

    def get_pod_by_app_label(self, label, namespace="rook-ceph"):
        return self.kubectl(
            '--namespace %s get pod -l app="%s"'
            ' --output custom-columns=name:metadata.name --no-headers'
            % (namespace, label)
        ).stdout.strip()

    def execute_in_pod_by_label(self, command, label, namespace="rook-ceph"):
        # Note(jhesketh): The pod isn't cached, so if running multiple commands
        #                 in the one pod consider calling the following
        #                 manually
        pod = self.get_pod_by_app_label(label, namespace)
        return self.execute_in_pod(command, pod, namespace)

    def destroy(self, skip=True):
        logger.info(f"kube destroy on hardware {self.hardware}")
        if skip:
            # We can skip in most cases since the nodes themselves will be
            # destroyed instead.
            return
        # TODO(jhesketh): Uninstall kubernetes
        pass

    def configure_kubernetes_client(self):
        kubernetes.config.load_kube_config(self.kubeconfig)
        self.v1 = kubernetes.client.CoreV1Api()
