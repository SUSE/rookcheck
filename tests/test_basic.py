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
import re

from tests.lib.hardware.node_base import NodeRole
from tests.lib import common


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

    rook_cluster.kubernetes.wait_for_pods_by_app_label("rook-direct-mount")

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

    rook_cluster.kubernetes.wait_for_pods_by_app_label("rook-direct-mount")

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
    services = ["rook-ceph-mgr",
                "rook-ceph-mgr-dashboard",
                "rook-ceph-mon-a",
                "rook-ceph-mon-b",
                "rook-ceph-mon-c"]

    # TODO(jhesketh): Check if csi-cephfsplugin-metrics or
    #                 csi-rbdplugin-metrics should be here.

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


def test_add_storage(rook_cluster):
    # get number of currently configured osds
    osds = rook_cluster.get_number_of_osds()
    # get a worker node
    nodes = rook_cluster.kubernetes.hardware.workers

    new_osds = 0
    # add a disk of 10 G the node
    disk_name = nodes[0].disk_create(10)
    nodes[0].disk_attach(name=disk_name)
    new_osds += 1

    # expecting an additional osd
    osds_expected = osds + new_osds

    # wait for the additional osd
    # this may take a while
    i = 0
    while osds < osds_expected:
        if i == 60:
            pytest.fail("rook was not able to add {new_osds} of required osds")
            break
        time.sleep(10)
        osds = rook_cluster.get_number_of_osds()
        i += 1
    # here we also detect if there are added more osds than required
    if osds != osds_expected:
        pytest.fail(f"we expect {osds_expected} osds, but have got {osds}")


def test_mons_up_down(rook_cluster):
    cluster_yaml = os.path.join(rook_cluster.ceph_dir, 'cluster.yaml')

    with open(cluster_yaml, 'r') as f:
        content = yaml.full_load(f)
        mons = int(content['spec']['mon']['count'])

    mon_pods = rook_cluster.get_number_of_mons()

    logger.info("Monitors to deploy by default: %d", mons)
    logger.info("Monitor pods actually running now: %d", mon_pods)

    assert mon_pods == mons

    deltamon = 2

    content['spec']['mon']['count'] = mons + deltamon
    content['spec']['mon']['allowMultiplePerNode'] = True

    cluster_yaml_modded = os.path.join(
        rook_cluster.ceph_dir, 'cluster_modded.yaml')

    with open(cluster_yaml_modded, 'w') as f:
        yaml.dump(content, f)

    logger.info("About to increase the number of monitors by %d", deltamon)

    rook_cluster.kubernetes.kubectl_apply(cluster_yaml_modded)
    rook_cluster.kubernetes.wait_for_pods_by_app_label(
        "rook-ceph-mon", count=mons+deltamon)

    mon_pods = rook_cluster.get_number_of_mons()

    logger.info("Monitor pods actually running now: %d", mon_pods)

    assert mon_pods == mons + deltamon

    logger.info("Attempting to restore the number of monitors to %d", mons)

    rook_cluster.kubernetes.kubectl_apply(cluster_yaml)

    check = 1
    mon_pods = rook_cluster.get_number_of_mons()

    while (check <= 180) and (mon_pods != mons):
        time.sleep(10)
        mon_pods = rook_cluster.get_number_of_mons()
        check += 1

    assert mon_pods == mons


def test_rbd_pvc(rook_cluster):
    # create a CephBlockPool
    output = rook_cluster.kubernetes.kubectl_apply(
                os.path.join(
                    rook_cluster.ceph_dir, 'csi/rbd/storageclass.yaml'))

    if output[0] != 0:
        pytest.fail("Could not create a CephBlockPool StorageClass")

    # check if StorageClass is up and available
    pattern = re.compile(r'.*rook-ceph-block*')
    common.wait_for_result(rook_cluster.kubernetes.kubectl, "get sc",
                           matcher=common.regex_matcher(pattern),
                           attempts=10, interval=6)

    # create an rbd based PVC
    output = rook_cluster.kubernetes.kubectl_apply(
                os.path.join(rook_cluster.ceph_dir, 'csi/rbd/pvc.yaml'))

    if output[0] != 0:
        pytest.fail("Could not create a rbd-PVC")

    pattern = re.compile(r'.*Bound*')
    common.wait_for_result(rook_cluster.kubernetes.kubectl, "get pvc rbd-pvc",
                           matcher=common.regex_matcher(pattern),
                           attempts=10, interval=6)

    # create a pod using the PVC
    output = rook_cluster.kubernetes.kubectl_apply(
                os.path.join(rook_cluster.ceph_dir, 'csi/rbd/pod.yaml'))

    if output[0] != 0:
        pytest.fail("Could not create a rbd-pod")

    pattern = re.compile(r'.*Running*')
    common.wait_for_result(rook_cluster.kubernetes.kubectl,
                           "get pod csirbd-demo-pod",
                           matcher=common.regex_matcher(pattern),
                           attempts=10, interval=10)

    rook_cluster.kubernetes.kubectl('delete pod csirbd-demo-pod')
    rook_cluster.kubernetes.kubectl('delete pvc rbd-pvc')
    rook_cluster.kubernetes.kubectl('delete sc rook-ceph-block')


@pytest.mark.xfail(reason="This is currently failing due to "
                          "https://github.com/rook/rook/issues/6214")
def test_add_remove_node(rook_cluster):
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
            rook_cluster.kubernetes.hardware.node_remove(node)
            pytest.fail("Was not able to add an additional node")
        time.sleep(10)
        workers_new = len(rook_cluster.kubernetes.hardware.workers)
        i += 1

    # get number of new osds
    osds = rook_cluster.get_number_of_osds()

    i = 0
    while osds != workers_new:
        if i == 90:
            rook_cluster.kubernetes.hardware.node_remove(node)
            pytest.fail("rook did not add an additional osd-node."
                        f"Removed node {node} again")
        time.sleep(10)
        osds = rook_cluster.get_number_of_osds()
        i += 1

    # now remove the node again
    workers_current = len(rook_cluster.kubernetes.hardware.workers)
    workers_expected = workers_current - 1
    i = 0
    rook_cluster.kubernetes.hardware.node_remove(node)
    while workers_expected != workers_current:
        if i == 10:
            pytest.fail(f"Was not able to remove node {node}")
        time.sleep(10)
        workers_current = len(rook_cluster.kubernetes.hardware.workers)
        i += 1

    # wait for OSDs to be back at the number of nodes
    workers_current = len(rook_cluster.kubernetes.hardware.workers)
    osds_current = rook_cluster.get_number_of_osds()

    i = 0
    while osds_current != workers_current:
        if i == 10:
            pytest.fail("rook did not remove additional OSD "
                        "after node removal")
        time.sleep(10)
        osds_current = rook_cluster.get_number_of_osds()
        i += 1
