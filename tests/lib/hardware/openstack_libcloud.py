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

import libcloud.security
from libcloud.compute.types import Provider, NodeState, StorageVolumeState
from libcloud.compute.providers import get_driver
from urllib.parse import urlparse

from tests.lib.hardware.hardware_base import HardwareBase
from tests.lib.hardware.node_base import NodeBase, NodeRole
from tests import config

logger = logging.getLogger(__name__)
libcloud.security.VERIFY_SSL_CERT = config.VERIFY_SSL_CERT


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
        logging.debug(f"node {self.name} booted")

        self._create_and_attach_floating_ip()
        # Wait for node to be ready
        self._wait_until_state(NodeState.RUNNING)
        # Attach a 10GB disk
        self._create_and_attach_volume(10)

    def _create_and_attach_floating_ip(self):
        # TODO(jhesketh): Move cloud-specific configuration elsewhere
        floating_ip = self.conn.ex_create_floating_ip(
            config.OS_EXTERNAL_NETWORK)

        logger.info(f"Created floating IP: {floating_ip}")
        self._floating_ips.append(floating_ip)

        # Wait until the node is running before assigning IP
        self._wait_until_state()
        self.conn.ex_attach_floating_ip_to_node(
            self._libcloud_node, floating_ip)
        logger.debug(f"node {self.name} floating ip {floating_ip} attached")

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
        if self._ssh_client:
            self._ssh_client.close()
        for floating_ip in self._floating_ips:
            floating_ip.delete()
        if self._libcloud_node:
            uuid = self._libcloud_node.uuid
            self._libcloud_node.destroy()
            self._libcloud_node = None
            self._wait_until_state(None, uuid=uuid)
        for volume in self._volumes:
            volume.destroy()

    def get_ssh_ip(self):
        """
        Figure out which IP to use to SSH over
        """
        # NOTE(jhesketh): For now, just use the last floating IP
        return self._floating_ips[-1].ip_address


class Hardware(HardwareBase):
    def __init__(self):
        super().__init__()
        self._ex_os_key = self.conn.import_key_pair_from_string(
            self.sshkey_name, self.public_key)
        self._ex_security_group = self._create_security_group()
        self._ex_network_cache = {}

        self._image_cache = {}
        self._size_cache = {}

        logger.info(f"public key {self.public_key}")
        logger.info(f"private key {self.private_key}")

    def get_connection(self):
        """ Get a libcloud connection object for the configured driver """
        connection = None
        # TODO(jhesketh): Provide a sensible way to allow configuration
        #                 of extended options on a per-provider level.
        #                 For example, the setting of OpenStack networks.
        OpenStackDriver = get_driver(Provider.OPENSTACK)

        # Strip any path from OS_AUTH_URL to be compatable with libcloud's
        # auth_verion.
        auth_url_parts = urlparse(config.OS_AUTH_URL)
        auth_url = \
            "%s://%s" % (auth_url_parts.scheme, auth_url_parts.netloc)
        connection = OpenStackDriver(
            config.OS_USERNAME,
            config.OS_PASSWORD,
            ex_force_auth_url=auth_url,
            ex_force_auth_version=config.OS_AUTH_VERSION,
            ex_domain_name=config.OS_USER_DOMAIN_NAME,
            ex_tenant_name=config.OS_PROJECT_NAME,
            ex_tenant_domain_id=config.OS_PROJECT_DOMAIN_ID,
            ex_force_service_region=config.OS_REGION_NAME,
            secure=config.VERIFY_SSL_CERT,
        )
        return connection

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
        if config.CLOUD_PROVIDER == 'OPENSTACK':
            security_group = self.conn.ex_create_security_group(
                name=("%s%s_security_group"
                      % (config.CLUSTER_PREFIX, self.hardware_uuid)),
                description="Permissive firewall for rookci testing"
            )
            for protocol in ["TCP", "UDP"]:
                self.conn.ex_create_security_group_rule(
                    security_group,
                    ip_protocol=protocol,
                    from_port=1,
                    to_port=65535,
                )
        else:
            raise Exception("Cloud provider not yet supported by rookcheck")
        return security_group

    def _create_node(self, node_name, role, tags=[]):
        # are there any additional networks for the node wanted?
        additional_networks = []
        if config.OS_INTERNAL_NETWORK:
            additional_networks.append(
                self._get_ex_network_by_name(config.OS_INTERNAL_NETWORK)
            )

        node = Node(node_name, role, tags, self.conn,
                    self._get_size_by_name(config.NODE_SIZE),
                    self._get_image_by_id(config.NODE_IMAGE_ID),
                    additional_networks, [self._ex_security_group],
                    self.sshkey_name)

        node.boot()
        self.node_add(node)

    def boot_nodes(self, masters=1, workers=2, offset=0):
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
            node_name = "%s%s_%s%d" % (
                config.CLUSTER_PREFIX, self.hardware_uuid, suffix, i+offset)
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
        super().destroy()
        self.conn.ex_delete_security_group(self._ex_security_group)
        self.conn.delete_key_pair(self._ex_os_key)
