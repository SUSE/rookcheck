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
import kubernetes
import logging
import re
import time
from typing import List

from tests.config import settings
from tests.lib import common
from tests.lib.hardware.hardware_base import HardwareBase
from tests.lib.hardware.node_base import NodeBase
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
            self.workspace.working_dir, 'bin/kubectl')
        self.v1 = None
        logger.info(f"kube init on hardware {self.hardware}")

    @abstractmethod
    def bootstrap(self):
        """
        bootstrap a k8s cluster.
        After calling this method, at least a single master node
        should be available in the k8s cluster so other master or worker
        nodes can join
        """
        logging.info("bootstrapping the kubernetes cluster")

    @abstractmethod
    def join(self, nodes: List[NodeBase]):
        logging.info(f"{len(nodes)} node(s) joining kubernetes cluster")

    @abstractmethod
    def install_kubernetes(self):
        self._configure_kubernetes_client()

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
        self.destroy(skip=not settings.as_bool('_TEAR_DOWN_CLUSTER'))

    def _configure_kubernetes_client(self):
        kubernetes.config.load_kube_config(self.kubeconfig)
        self.v1 = kubernetes.client.CoreV1Api()

    def kubectl(self, command, check=True, log_stdout=True, log_stderr=True):
        """
        Run a kubectl command
        """
        return common.execute(
            f"{self.kubectl_exec} --kubeconfig {self.kubeconfig}"
            f" {command}",
            check=check,
            capture=True,
            log_stdout=log_stdout,
            log_stderr=log_stderr,
            logger_name=f"kubectl {command}",
        )

    def kubectl_apply(self, yaml_file, log_stdout=True, log_stderr=True):
        return self.kubectl(
            "apply -f %s" % yaml_file, log_stdout=log_stdout,
            log_stderr=log_stderr
        )

    def untaint_master(self):
        # Untainting returns exit status 1 since not all nodes are tainted.
        self.kubectl(
            "taint nodes --all node-role.kubernetes.io/master-",
            check=False
        )

    def execute_in_pod(self, command, pod, namespace="rook-ceph",
                       log_stdout=True, log_stderr=True):
        return self.kubectl(
            '--namespace %s exec -t "%s" -- bash -c "$(cat <<\'EOF\'\n'
            '%s'
            '\nEOF\n)"'
            % (namespace, pod, command),
            log_stdout=log_stdout,
            log_stderr=log_stderr
        )

    def get_pods_by_app_label(self, label, namespace="rook-ceph"):
        pods_string = self.kubectl(
            '--namespace %s get pod -l app="%s"'
            ' --output custom-columns=name:metadata.name --no-headers'
            % (namespace, label)
        )[1].strip()
        return pods_string.split('\n')

    def get_services_by_app_label(self, label, namespace="rook-ceph"):
        services_string = self.kubectl(
            '--namespace %s get svc -l app="%s"'
            ' --output custom-columns=name:metadata.name --no-headers'
            % (namespace, label)
        )[1].strip()
        return services_string.split('\n')

    def execute_in_pod_by_label(self, command, label, namespace="rook-ceph",
                                log_stdout=True, log_stderr=True):
        # Note(jhesketh): The pod isn't cached, so if running multiple commands
        #                 in the one pod consider calling the following
        #                 manually
        pods = self.get_pods_by_app_label(label, namespace)
        return self.execute_in_pod(
            command, pods[0], namespace, log_stdout=log_stdout,
            log_stderr=log_stderr
        )

    def destroy(self, skip=True):
        if skip:
            # We can skip in most cases since the nodes themselves will be
            # destroyed instead.
            return

        if settings.as_bool('_TEAR_DOWN_CLUSTER_CONFIRM'):
            common.handle_cleanup_input("pause before cleanup kubernetes")

        # TODO(jhesketh): Uninstall kubernetes
        logger.info(f"kube destroy on hardware {self.hardware}")
        pass

    def configure_kubernetes_client(self):
        kubernetes.config.load_kube_config(self.kubeconfig)
        self.v1 = kubernetes.client.CoreV1Api()

    def wait_for_service(self, service, sleep=10, iteration=60,
                         namespace="rook-ceph"):
        found = False
        for i in range(iteration):
            output = self.kubectl(
                            '-n ' + namespace + ' get service ' + service,
                            check=False)
            if output[0] == 0:
                found = True
                break
            time.sleep(10)

        return found

    def wait_for_pods_by_app_label(self, label, count=1, sleep=5, attempts=120,
                                   namespace="rook-ceph"):
        pattern = re.compile(r'.*Running')
        common.wait_for_result(
            self.kubectl,
            f'--namespace {namespace} get pod -l app="{label}" --no-headers',
            matcher=common.regex_count_matcher(pattern, count),
            attempts=attempts, interval=sleep)
