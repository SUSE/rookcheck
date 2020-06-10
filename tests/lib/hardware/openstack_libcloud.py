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

# The Hardware module should take care of the operating system abstraction
# through images.
# libcloud will provide a common set of cloud-agnostic objects such as Node[s]
# We might extend the Node object to have an easy way to run arbitrary commands
# on the node such as Node.execute().
# There will be a challenge where those arbitrary commands differ between OS's;
# this is an abstraction that is not yet well figured out, but will likely
# take the form of cloud-init or similar bringing the target node to an
# expected state.

import logging
import threading
import time
from typing import Dict, List

from dynaconf import settings
import libcloud.security
from libcloud.compute.base import NodeImage
from libcloud.compute.drivers.openstack import (
    OpenStackNetwork, OpenStackNodeSize, OpenStackSecurityGroup
)
from libcloud.compute.types import Provider, NodeState, StorageVolumeState
from libcloud.compute.providers import get_driver
from urllib.parse import urlparse

from tests.lib.hardware.hardware_base import HardwareBase
from tests.lib.hardware.node_base import NodeBase, NodeRole
from tests.lib.workspace import Workspace

logger = logging.getLogger(__name__)
libcloud.security.VERIFY_SSL_CERT = settings.as_bool('OS_VERIFY_SSL_CERT')


class Node(NodeBase):
    def __init__(self, name, role, tags, conn, size, image, networks,
                 security_groups, sshkey_name):
        super().__init__(name, role, tags)
        self.conn = conn
        self._size = size
        self._image = image
        self._networks = networks
        self._security_groups = security_groups
        self._sshkey_name = sshkey_name
        self._libcloud_node = None

        self._floating_ips = []
        self._floating_ips_created = []
        self._volumes = []

        self._ssh_client = None

    def boot(self):
        if self._libcloud_node:
            raise Exception(f"node {self.name} has already been booted")

        kwargs = {}
        if self._networks:
            kwargs['networks'] = self._networks
        if self._sshkey_name:
            kwargs['ex_keyname'] = self._sshkey_name
        kwargs['ex_security_groups'] = self._security_groups

        logging.debug(f"node {self.name} booting")
        self._libcloud_node = self.conn.create_node(
            name=self.name,
            size=self._size,
            image=self._image,
            **kwargs
        )
        logging.info(f"node {self.name} booted")

        self._get_floating_ip()
        # Wait for node to be ready
        self._wait_until_state(NodeState.RUNNING)
        # Attach a 10GB disk
        self._create_and_attach_volume(10)

    def _get_floating_ip(self):
        try:
            floating_ip = self.conn.ex_create_floating_ip(
                settings.OS_EXTERNAL_NETWORK)
            logger.info(f"Created floating IP: {floating_ip}")
            self._floating_ips.append(floating_ip)
            self._floating_ips_created.append(floating_ip)
        except libcloud.common.exceptions.BaseHTTPError:
            logger.error("Unable to create floating IP")
            logger.warning("Falling back to existing IP \
association if any is free...")
            for floating_ip in self.libcloud_conn.ex_list_floating_ips():
                if floating_ip.node_id is None:
                    self._floating_ips.append(floating_ip)
                break
            if floating_ip.node_is is not None:
                raise Exception("Unable to find an available IP to associate")

        # Wait until the node is running before assigning IP
        self._wait_until_state()
        self.conn.ex_attach_floating_ip_to_node(
            self._libcloud_node, floating_ip)
        logger.info(f"node {self.name}: floating ip {floating_ip} attached")

    def _create_and_attach_volume(self, size=10):
        vol_name = "%s-vol-%d" % (self.name, len(self._volumes))
        volume = self.conn.create_volume(size=size, name=vol_name)
        logger.info(f"Created volume: {volume}")

        # Wait for volume to be ready before attaching
        self._wait_until_volume_state(volume.uuid)

        self.conn.attach_volume(
            self._libcloud_node, volume, device=None)
        logger.debug(f"node {self.name} volume attached")
        self._volumes.append(volume)

    def _wait_until_volume_state(self, volume_uuid,
                                 state=StorageVolumeState.AVAILABLE,
                                 timeout=120, interval=3):
        # `state` can be StorageVolumeState, "any", or None (for not existant)
        # `state` can also be a list of NodeState's, any matching will pass
        for _ in range(int(timeout / interval)):
            volumes = self.conn.list_volumes()
            for volume in volumes:
                if volume.uuid == volume_uuid:
                    if state == "any":
                        # Special case where we just want to see the volume in
                        # volume_list in any state.
                        return True
                    elif type(state) is list:
                        if volume.state in state:
                            return True
                    elif state == volume.state:
                        return True
                    break
            if state is None:
                return True
            time.sleep(interval)

        raise Exception("Timeout waiting for volume to be state `%s`" % state)

    def _wait_until_state(self, state=NodeState.RUNNING, timeout=120,
                          interval=3, uuid=None):
        # `state` can be NodeState, "any", or None (for not existant)
        # `state` can also be a list of NodeState's, any matching will pass
        if not uuid:
            uuid = self._libcloud_node.uuid
        for _ in range(int(timeout / interval)):
            nodes = self.conn.list_nodes()
            for node in nodes:
                if node.uuid == uuid:
                    if state == "any":
                        # Special case where we just want to see the node in
                        # node_list in any state.
                        return True
                    elif type(state) is list:
                        if node.state in state:
                            return True
                    elif state == node.state:
                        return True
                    break
            if state is None:
                return True
            time.sleep(interval)

        raise Exception("Timeout waiting for node to be state `%s`" % state)

    def destroy(self):
        logger.info(f"Destroy node {self.name}")
        if self._ssh_client:
            self._ssh_client.close()
        for floating_ip in self._floating_ips_created:
            logger.info(f"Delete floating ip {floating_ip}")
            floating_ip.delete()
        if self._libcloud_node:
            uuid = self._libcloud_node.uuid
            logger.info(f"Delete node {self._libcloud_node}")
            self._libcloud_node.destroy()
            self._libcloud_node = None
            self._wait_until_state(None, uuid=uuid)
        for volume in self._volumes:
            logger.info(f"Delete volume {volume}")
            volume.destroy()

    def get_ssh_ip(self):
        """
        Figure out which IP to use to SSH over
        """
        # NOTE(jhesketh): For now, just use the last floating IP
        return self._floating_ips[-1].ip_address

    def add_data_disk(self, capacity):
        # TODO: We need to add three methods actually
        # disk_create
        # disk_attach
        # disk_detach
        # _create_and_attach_volume() above is already doign part of it
        logger.warn('add_data_disk() not implemented for'
                    'openstack backend yet')


class Hardware(HardwareBase):
    def __init__(self, workspace: Workspace):
        super().__init__(workspace)
        self._ex_os_key = self.conn.import_key_pair_from_string(
            self.workspace.sshkey_name, self.workspace.public_key)
        self._ex_security_group: OpenStackSecurityGroup = \
            self._create_security_group()
        self._ex_network_cache: List[OpenStackNetwork] = []

        self._image_cache: Dict[str, NodeImage] = {}
        self._full_image_cache: List[NodeImage] = []
        self._size_cache: List[OpenStackNodeSize] = []

    def get_connection(self):
        """ Get a libcloud connection object for the configured driver """
        connection = None
        # TODO(jhesketh): Provide a sensible way to allow configuration
        #                 of extended options on a per-provider level.
        #                 For example, the setting of OpenStack networks.
        OpenStackDriver = get_driver(Provider.OPENSTACK)

        # Strip any path from OS_AUTH_URL to be compatable with libcloud's
        # auth_verion.
        auth_url_parts = urlparse(settings.OS_AUTH_URL)
        auth_url = \
            "%s://%s" % (auth_url_parts.scheme, auth_url_parts.netloc)
        connection = OpenStackDriver(
            settings.OS_USERNAME,
            settings.OS_PASSWORD,
            ex_force_auth_url=auth_url,
            ex_force_auth_version=settings.OS_AUTH_VERSION,
            ex_domain_name=settings.OS_USER_DOMAIN_NAME,
            ex_tenant_name=settings.OS_PROJECT_NAME,
            ex_tenant_domain_id=settings.OS_PROJECT_DOMAIN_ID,
            ex_force_service_region=(
                settings.OS_REGION_NAME if settings.OS_REGION_NAME else None),
            secure=settings.as_bool('OS_VERIFY_SSL_CERT'),
        )
        return connection

    def _get_image(self, identifier=None):
        try:
            return self._get_image_by_id(identifier)
        except libcloud.common.exceptions.BaseHTTPError:
            logger.debug('No image found by id. '
                         'Falling back to search by name')
            return self._get_image_by_name(identifier)

    def _get_image_by_name(self, name):
        # NOTE(jhesketh): In general we wouldn't expect the provider list of
        #                 images to change mid-test. Thus caching this once
        #                 should be sufficient.
        if not self._full_image_cache:
            self._full_image_cache = self.conn.list_images()
        for image in self._full_image_cache:
            if name == image.name:
                return image
        raise Exception(f'No image found matching NAME {name}')

    def _get_image_by_id(self, id):
        if id in self._image_cache:
            return self._image_cache[id]
        self._image_cache[id] = self.conn.get_image(id)
        return self._image_cache[id]

    def _get_size_by_name(self, name=None):
        if self._size_cache:
            sizes = self._size_cache
        else:
            sizes = self.conn.list_sizes()
            self._size_cache = sizes

        if name:
            for node_size in sizes:
                if node_size.name == name:
                    return node_size

        return None

    def _get_ex_network_by_name(self, name=None):
        # TODO(jhesketh): Create a network instead
        if self._ex_network_cache:
            networks = self._ex_network_cache
        else:
            networks = self.conn.ex_list_networks()
            self._ex_network_cache = networks

        if name:
            for network in networks:
                if network.name == name:
                    return network

        return None

    def _create_security_group(self):
        """
        Creates a security group used for this set of hardware. For now,
        all ports are open.
        """
        security_group = self.conn.ex_create_security_group(
            name=("%s_security_group" % self.workspace.name),
            description="Permissive firewall for rookci testing"
        )
        for protocol in ["TCP", "UDP"]:
            self.conn.ex_create_security_group_rule(
                security_group,
                ip_protocol=protocol,
                from_port=1,
                to_port=65535,
            )
        return security_group

    def node_create(self, name: str, role: NodeRole,
                    tags: List[str]) -> NodeBase:
        super().node_create(name, role, tags)
        # are there any additional networks for the node wanted?
        additional_networks = []
        if settings.OS_INTERNAL_NETWORK:
            additional_networks.append(
                self._get_ex_network_by_name(settings.OS_INTERNAL_NETWORK)
            )

        node = Node(name, role, tags, self.conn,
                    self._get_size_by_name(settings.OS_NODE_SIZE),
                    self._get_image(settings.OS_NODE_IMAGE),
                    additional_networks, [self._ex_security_group],
                    self.workspace.sshkey_name)
        node.boot()
        return node

    def _create_node(self, node_name, role, tags=[]):
        node = self.node_create(node_name, role, tags)
        self.node_add(node)

    def boot_nodes(self, masters: int, workers: int, offset: int = 0):
        """
        Boot n nodes
        Start them at a number offset
        """
        # Warm the caches
        self._get_ex_network_by_name()
        self._get_size_by_name()
        if masters:
            self._boot_nodes(NodeRole.MASTER, ['master', 'first_master'], 1,
                             offset=offset, suffix='master_')
            masters -= 1
            self._boot_nodes(NodeRole.MASTER, ['master'], masters,
                             offset=offset+1, suffix='master_')
        self._boot_nodes(NodeRole.WORKER, ['worker'], workers, offset=offset,
                         suffix='worker_')

    def _boot_nodes(self, role, tags, n, offset=0, suffix=""):
        threads = []
        for i in range(n):
            node_name = "%s_%s%d" % (self.workspace.name, suffix, i+offset)
            thread = threading.Thread(
                target=self._create_node, args=(node_name, role, tags))
            threads.append(thread)
            thread.start()

            # FIXME(jhesketh): libcloud apparently is not thread-safe. libcloud
            # expects to be able to look up a response in the Connection
            # object but if multiple requests were sent the wrong one may be
            # set. Instead of removing the threading code, we'll just rejoin
            # the thread in case we can use this in the future.
            # We could create a new libcloud instance for each thread..
            thread.join()

        # for thread in threads:
        #     thread.join()

    def destroy(self):
        logger.info("Destroy Hardware")
        super().destroy()
        logger.info("Remove OpenStack security group")
        self.conn.ex_delete_security_group(self._ex_security_group)
        logger.info("Remove OpenStack keypair")
        self.conn.delete_key_pair(self._ex_os_key)

    def remove_host_keys(self):
        # The mitogen plugin does not correctly ignore host key checking, so we
        # should remove any host keys for our nodes before starting.
        # The 'ssh' connection imports ssh-keys for us, so as a first step we
        # run a standard ssh connection to do the imports. We could import the
        # sshkeys manually first, but we also want to wait on the connection to
        # be available (in order to even be able to get them).
        # Therefore simply remove any entries from your known_hosts. It's also
        # helpful to do this after a build to clean up anything locally.
        for node in self.nodes.values():
            self.remove_ssh_key(node.get_ssh_ip())

    def remove_ssh_key(self, ip):
        logger.info(
            f"Removing {ip} from known-hosts if exists.")
        self.workspace.execute(
            f"ssh-keygen -R {ip}", check=False, log_stderr=False)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy()
