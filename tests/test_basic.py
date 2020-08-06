# Copyright (c) 2020 SUSE LINUX GmbH
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
import pytest
import time

from tests.lib.hardware.node_base import NodeRole


logger = logging.getLogger(__name__)


def test_deploy_filesystem(rook_cluster):
    # rook_cluster checks the filesystem is deployed before continuing
    rook_cluster.deploy_rbd()
    time.sleep(10)
    rook_cluster.deploy_filesystem()
    # This test leaves the filesystem set up ready for the next tests in this
    # module.


def test_file_creation(rook_cluster):
    logger.debug("Create direct-mount deployment")
    rook_cluster.kubernetes.kubectl_apply(
        os.path.join(rook_cluster.ceph_dir, 'direct-mount.yaml'))

    # TODO(jhesketh): Create a helper function for checking if a container is
    #                 ready instead of waiting.
    time.sleep(10)

    logger.debug("Mount myfs in pod and put a test string into a file")
    rook_cluster.kubernetes.execute_in_pod_by_label("""
        # Create the directory
        mkdir /tmp/registry

        # Detect the mon endpoints and the user secret for the connection
        mon_endpoints=$(grep mon_host /etc/ceph/ceph.conf | awk '{print $3}')
        my_secret=$(grep key /etc/ceph/keyring | awk '{print $3}')

        # Mount the filesystem
        mount -t ceph -o mds_namespace=myfs,name=admin,secret=$my_secret \
            $mon_endpoints:/ /tmp/registry

        # See your mounted filesystem
        df -h /tmp/registry

        echo "Hello Rook" > /tmp/registry/hello
        umount /tmp/registry
        rmdir /tmp/registry
    """, label="rook-direct-mount")

    logger.debug("Recreate the direct-mount container and wait...")

    # Scale the direct mount deployment down and back up again to recreate the
    # pod (to ensure that we haven't left anything on the container volume
    # and therefore to be sure we are writing to the cephfs)
    rook_cluster.kubernetes.kubectl(
        "scale deployment rook-direct-mount --replicas=0 -n rook-ceph")

    time.sleep(10)

    rook_cluster.kubernetes.kubectl(
        "scale deployment rook-direct-mount --replicas=1 -n rook-ceph")

    time.sleep(10)

    logger.debug("Mount myfs again and output the contents")
    rc, stdout, stderr = rook_cluster.kubernetes.execute_in_pod_by_label("""
        # Create the directory
        mkdir /tmp/registry

        # Detect the mon endpoints and the user secret for the connection
        mon_endpoints=$(grep mon_host /etc/ceph/ceph.conf | awk '{print $3}')
        my_secret=$(grep key /etc/ceph/keyring | awk '{print $3}')

        # Mount the filesystem
        mount -t ceph -o mds_namespace=myfs,name=admin,secret=$my_secret \
            $mon_endpoints:/ /tmp/registry

        cat /tmp/registry/hello
        umount /tmp/registry
        rmdir /tmp/registry
    """, label="rook-direct-mount")

    logger.debug("Check result")
    # Assert that the contents is as expected, confirming that writing to the
    # cephfs is working as expected
    assert stdout.strip() == "Hello Rook"

    # Cleanup: Uninstall rook-direct-mount
    rook_cluster.kubernetes.kubectl(
        "delete deployment.apps/rook-direct-mount -n rook-ceph")

    logger.debug("Test successful/complete!")


def test_osd_number(rook_cluster):
    # get number of workers
    workers = len(rook_cluster.kubernetes.hardware.workers)
    logger.debug("cluster has %s worker nodes", workers)

    osds = rook_cluster.get_number_of_osds()
    i = 0
    while osds != workers:
        if i == 20:
            pytest.fail("rook did not add an additional osd-node")
            break
        time.sleep(10)
        osds = rook_cluster.get_number_of_osds()
        i += 1


def test_add_node(rook_cluster):
    workers_old = len(rook_cluster.kubernetes.hardware.workers)
    # add a node to the cluster
    node_name = "%s_worker_%s" % (rook_cluster.workspace.name, "test-node")
    node = rook_cluster.kubernetes.hardware.node_create(node_name,
                                                        NodeRole.WORKER,
                                                        ["worker"])
    # add a disk of 10 G the node
    node.disk_create(10)
    rook_cluster.kubernetes.hardware.node_add(node)
    rook_cluster.kubernetes.hardware.prepare_nodes()
    # add the node the k8s cluster
    rook_cluster.kubernetes.join([node])

    # get number of new workers
    workers_new = len(rook_cluster.kubernetes.hardware.workers)
    i = 0
    while workers_new == workers_old:
        if i == 10:
            pytest.fail("Was not able to add an additional node")
            break
        time.sleep(10)
        workers_new = len(rook_cluster.kubernetes.hardware.workers)
        i += 1

    # get number of new osds
    osds = rook_cluster.get_number_of_osds()

    i = 0
    while osds != workers_new:
        if i == 20:
            pytest.fail("rook did not add an additional osd-node")
            break
        time.sleep(10)
        osds = rook_cluster.get_number_of_osds()
        i += 1
