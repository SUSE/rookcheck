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
import yaml

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


# check if rbd service gets started automatically
def test_service_mons(rook_cluster):
    cluster_yaml = os.path.join(rook_cluster.ceph_dir, 'cluster.yaml')
    with open(cluster_yaml, 'r') as f:
        cluster_object = yaml.load(f, Loader=yaml.BaseLoader)
    # get configured number of monitors
    count = cluster_object['spec']['mon']['count']
    count = int(count)
    logger.info("Expecting %d monitors", count)

    # get number of mon-services
    services = rook_cluster.kubernetes.get_services_by_app_label(
        "rook-ceph-mon")

    if count != len(services):
        pytest.fail("Expected %d mon-services but got %d",
                    count, len(services))

    # get number of mon-pods
    pods = rook_cluster.kubernetes.get_pods_by_app_label("rook-ceph-mon")
    if count != len(pods):
        pytest.fail("Expected %d mon-pods but got %d",
                    count, len(pods))


# check if all default services are available
def test_services(rook_cluster):
    services = ["csi-cephfsplugin-metrics",
                "csi-rbdplugin-metrics",
                "rook-ceph-mgr",
                "rook-ceph-mgr-dashboard",
                "rook-ceph-mon-a",
                "rook-ceph-mon-b",
                "rook-ceph-mon-c"]

    for service in services:
        found = rook_cluster.kubernetes.wait_for_service(service)
        if found is False:
            pytest.fail("Could not find service %s", service)


# check if rbd service gets started automatically
def test_service_rbd(rook_cluster):
    # create an ObjectStore
    output = rook_cluster.kubernetes.kubectl_apply(
                os.path.join(rook_cluster.ceph_dir, 'object-test.yaml'))

    if output[0] != 0:
        pytest.fail("Could not create an ObjectStore")

    found = rook_cluster.kubernetes.wait_for_service("rook-ceph-rgw-my-store",
                                                     iteration=20)

    if found is False:
        pytest.fail("rgw service has not been started automatically")

    # NOTE(jhesketh): This test leaves the rgw running in the cluster.


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
    node_name = "%s-worker-%s" % (rook_cluster.workspace.name, "test-node")
    node = rook_cluster.kubernetes.hardware.node_create(node_name,
                                                        NodeRole.WORKER,
                                                        ["worker"])
    # NodeRole.WORKER adds the disk for us
    rook_cluster.kubernetes.hardware.node_add(node)
    rook_cluster.kubernetes.hardware.prepare_nodes(limit_to_nodes=[node])
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
        if i == 90:
            pytest.fail("rook did not add an additional osd-node")
            break
        time.sleep(10)
        osds = rook_cluster.get_number_of_osds()
        i += 1


def test_add_storage(rook_cluster):
    # get number of currently configured osds
    osds = rook_cluster.get_number_of_osds()
    # get a worker node
    nodes = rook_cluster.kubernetes.hardware.workers

    # add a disk of 10 G the node
    disk_name = nodes[0].disk_create(10)
    nodes[0].disk_attach(name=disk_name)

    i = 0
    # expecting an additional osd
    osds_expected = osds + 1
    osds_new = rook_cluster.get_number_of_osds()

    # wait for the additional osd
    # this may take a while
    while osds_expected != osds_new:
        if i == 60:
            pytest.fail("rook did not add an additional osd-node")
            break
        time.sleep(10)
        osds_new = rook_cluster.get_number_of_osds()
        i += 1
