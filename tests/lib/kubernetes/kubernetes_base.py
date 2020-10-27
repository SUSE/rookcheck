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
import json
import kubernetes
import logging
import os
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

    def gather_logs(self, dest_dir):
        dest_dir = os.path.join(dest_dir, 'kubernetes')
        os.makedirs(dest_dir, exist_ok=True)
        logging.info(f"Gathering kubernetes logs to {dest_dir}")

        try:
            with open(os.path.join(dest_dir, 'get_all.txt'), 'w') as f:
                rc, stdout, stderr = self.kubectl("get all --all-namespaces",
                                                  log_stdout=False)
                f.write(stdout)
        except Exception:
            logger.warning("Unable to `kubectl get all`")

        methods = {
            'config_maps.json': 'list_config_map_for_all_namespaces',
            'endpoints.json': 'list_endpoints_for_all_namespaces',
            'events.json': 'list_event_for_all_namespaces',
            'limit_ranges.json': 'list_limit_range_for_all_namespaces',
            'namespaces.json': 'list_namespace',
            'nodes.json': 'list_node',
            'persistent_volumes.json': 'list_persistent_volume',
            'persistent_volume_claims.json':
                'list_persistent_volume_claim_for_all_namespaces',
            'pods.json': 'list_pod_for_all_namespaces',
            'pod_templates.json': 'list_pod_template_for_all_namespaces',
            'replication_controllers.json':
                'list_replication_controller_for_all_namespaces',
            'resource_quotas.json': 'list_resource_quota_for_all_namespaces',
            'secrets.json': 'list_secret_for_all_namespaces',
            'services.json': 'list_service_for_all_namespaces',
            'service_accounts.json': 'list_service_account_for_all_namespaces'

        }

        for file_name, method in methods.items():
            try:
                with open(os.path.join(dest_dir, file_name), 'w') as f:
                    json.dump(
                        getattr(self.v1, method)().to_dict(),
                        f, default=str, sort_keys=True, indent=2
                    )
            except Exception:
                logger.warning(f"Unable to log {method}")

        pod_logs_dest_dir = os.path.join(dest_dir, 'pod_logs')
        os.makedirs(pod_logs_dest_dir, exist_ok=True)
        pods = self.v1.list_pod_for_all_namespaces()
        for pod in pods.items:
            pod_name = pod.metadata.name
            namespace = pod.metadata.namespace
            try:
                with open(os.path.join(pod_logs_dest_dir, f'{pod_name}.txt'),
                          'w') as f:
                    f.write(
                        self.v1.read_namespaced_pod_log(pod_name, namespace)
                    )
            except Exception:
                logger.warning(f"Unable to get logs for pod {pod_name}")
            try:
                with open(os.path.join(pod_logs_dest_dir,
                                       f'describe_{pod_name}.txt'), 'w') as f:
                    rc, stdout, stderr = self.kubectl(
                        f"-n {namespace} describe pod {pod_name}",
                        log_stdout=False)
                    f.write(stdout)
            except Exception:
                logger.warning(f"Unable to describe pod {pod_name}")

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        if settings._GATHER_LOGS_DIR:
            self.gather_logs(settings._GATHER_LOGS_DIR)
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
            '-n %s exec -t "%s" -- bash -c "$(cat <<\'EOF\'\n'
            '%s'
            '\nEOF\n)"'
            % (namespace, pod, command),
            log_stdout=log_stdout,
            log_stderr=log_stderr
        )

    def get_pods_by_app_label(self, label, namespace="rook-ceph"):
        pods_string = self.kubectl(
            '-n %s get pod -l app="%s"'
            ' --output custom-columns=name:metadata.name --no-headers'
            % (namespace, label)
        )[1].strip()
        return pods_string.split('\n')

    def get_services_by_app_label(self, label, namespace="rook-ceph"):
        services_string = self.kubectl(
            '-n %s get svc -l app="%s"'
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
            f'-n {namespace} get pod -l app="{label}" --no-headers',
            matcher=common.regex_count_matcher(pattern, count),
            attempts=attempts, interval=sleep)
