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
import subprocess
import threading
import time

import libcloud.security
from libcloud.compute.types import Provider, NodeState, StorageVolumeState
from libcloud.compute.providers import get_driver
from paramiko.client import AutoAddPolicy, SSHClient
from urllib.parse import urlparse

from tests.lib.hardware.hardware_base import HardwareBase
from tests.lib.hardware.node_base import NodeBase
from tests import config

logger = logging.getLogger(__name__)
libcloud.security.VERIFY_SSL_CERT = config.VERIFY_SSL_CERT

if config.DISTRO == 'openSUSE_k8s':
    from tests.lib.distro.opensuse import openSUSE_k8s as Distro
elif config.DISTRO == 'SLES_CaaSP':
    from tests.lib.distro.sles import SLES_CaaSP as Distro  # type: ignore
else:
    raise Exception('Unknown distro {}'.format(config.DISTRO))


class Node(NodeBase):
    def __init__(self, conn, name, pubkey=None, private_key=None,
                 tags=[]):
        super().__init__(name, private_key)
        self.conn = conn
        self.libcloud_node = None

        self.floating_ips = []
        self.volumes = []
        self.tags = tags
        self.pubkey = pubkey

        self._ssh_client = None

    def boot(self, size, image, sshkey_name=None, additional_networks=[],
             security_groups=[]):
        if self.libcloud_node:
            raise Exception("A node has already been booted")

        # TODO(jhesketh): Move cloud-specific configuration elsewhere
        kwargs = {}
        if additional_networks:
            kwargs['networks'] = additional_networks
        if sshkey_name:
            kwargs['ex_keyname'] = sshkey_name
        if security_groups:
            kwargs['ex_security_groups'] = security_groups

        # Can't use deploy_node because there is no public ip yet
        self.libcloud_node = self.conn.create_node(
            name=self.name,
            size=size,
            image=image,
            **kwargs
        )

        logger.info(f"Created node: {self.libcloud_node}")

    def create_and_attach_floating_ip(self):
        # TODO(jhesketh): Move cloud-specific configuration elsewhere
        floating_ip = self.conn.ex_create_floating_ip(
            config.OS_EXTERNAL_NETWORK)

        logger.info(f"Created floating IP: {floating_ip}")
        self.floating_ips.append(floating_ip)

        # Wait until the node is running before assigning IP
        self.wait_until_state()
        self.conn.ex_attach_floating_ip_to_node(
            self.libcloud_node, floating_ip)

    def create_and_attach_volume(self, size=10):
        vol_name = "%s-vol-%d" % (self.name, len(self.volumes))
        volume = self.conn.create_volume(size=size, name=vol_name)
        logger.info(f"Created volume: {volume}")

        # Wait for volume to be ready before attaching
        self.wait_until_volume_state(volume.uuid)

        self.conn.attach_volume(
            self.libcloud_node, volume, device=None)
        self.volumes.append(volume)

    def wait_until_volume_state(self, volume_uuid,
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

    def wait_until_state(self, state=NodeState.RUNNING, timeout=120,
                         interval=3, uuid=None):
        # `state` can be NodeState, "any", or None (for not existant)
        # `state` can also be a list of NodeState's, any matching will pass
        if not uuid:
            uuid = self.libcloud_node.uuid
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
        for floating_ip in self.floating_ips:
            floating_ip.delete()
        if self.libcloud_node:
            uuid = self.libcloud_node.uuid
            self.libcloud_node.destroy()
            self.libcloud_node = None
            self.wait_until_state(None, uuid=uuid)
        for volume in self.volumes:
            volume.destroy()

    def get_ssh_ip(self):
        """
        Figure out which IP to use to SSH over
        """
        # NOTE(jhesketh): For now, just use the last floating IP
        return self.floating_ips[-1].ip_address

    def execute_command(self, command):
        """
        Executes a command over SSH
        return_value: (stdin, stdout, stderr)

        (Warning, this method is untested)
        """
        if not self._ssh_client:
            self._ssh_client = SSHClient()
            self._ssh_client.set_missing_host_key_policy(
                AutoAddPolicy()
            )
            self._ssh_client.connect(
                hostname=self.get_ssh_ip,
                username=config.NODE_IMAGE_USER,
                pkey=self.private_key,
                allow_agent=False,
                look_for_keys=False,
            )
        return self._ssh_client.exec_command(command)


class Hardware(HardwareBase):
    def __init__(self):
        super().__init__()
        self._ex_os_key = self.generate_keys()
        self._ex_security_group = self._create_security_group()
        self._ex_network_cache = {}

        self._image_cache = {}
        self._size_cache = {}

        logger.info(f"public key {self.pubkey}")
        logger.info(f"private key {self.private_key}")

    def generate_keys(self):
        super().generate_keys()
        os_key = self.conn.import_key_pair_from_string(
            self.sshkey_name, self.pubkey)

        return os_key

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
            raise Exception("Cloud provider not yet supported by smoke_rook")
        return security_group

    def _create_node(self, node_name, tags=[]):
        node = Node(
            conn=self.conn,
            name=node_name, pubkey=self.pubkey, private_key=self.private_key,
            tags=tags)
        # TODO(jhesketh): Create fixed network as part of build and security
        #                 group
        additional_networks = []
        if config.OS_INTERNAL_NETWORK:
            additional_networks.append(
                self._get_ex_network_by_name(config.OS_INTERNAL_NETWORK)
            )
        node.boot(
            size=self._get_size_by_name(config.NODE_SIZE),
            image=self._get_image_by_id(config.NODE_IMAGE_ID),
            sshkey_name=self.sshkey_name,
            additional_networks=additional_networks,
            security_groups=[
                self._ex_security_group,
            ]
        )
        node.create_and_attach_floating_ip()
        # Wait for node to be ready
        node.wait_until_state(NodeState.RUNNING)
        # Attach a 10GB disk
        node.create_and_attach_volume(10)
        self.nodes[node_name] = node

    def boot_nodes(self, masters=1, workers=2, offset=0):
        """
        Boot n nodes
        Start them at a number offset
        """
        # Warm the caches
        self._get_ex_network_by_name()
        self._get_size_by_name()
        if masters:
            self._boot_nodes(['master', 'first_master'], 1, offset=offset,
                             suffix='master_')
            masters -= 1
            self._boot_nodes(['master'], masters, offset=offset+1,
                             suffix='master_')
        self._boot_nodes(['worker'], workers, offset=offset, suffix='worker_')

    def _boot_nodes(self, tags, n, offset=0, suffix=""):
        threads = []
        for i in range(n):
            node_name = "%s%s_%s%d" % (
                config.CLUSTER_PREFIX, self.hardware_uuid, suffix, i+offset)
            thread = threading.Thread(
                target=self._create_node, args=(node_name, tags))
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
        # Remove nodes
        logger.info("destroy nodes")

        threads = []
        for node in self.nodes.values():
            thread = threading.Thread(target=node.destroy,)
            threads.append(thread)
            thread.start()
            # FIXME(jhesketh): See above re thread-safety.
            thread.join()

        # for thread in threads:
        #     thread.join()

        self.conn.ex_delete_security_group(self._ex_security_group)
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
        subprocess.run(
            "ssh-keygen -R %s" % ip,
            shell=True
        )

    def prepare_nodes(self):
        """
        Install any dependencies, set firewall etc.
        """
        d = Distro()

        self.remove_host_keys()
        r = self.execute_ansible_play(d.wait_for_connection_play())

        if r.host_failed or r.host_unreachable:
            # TODO(jhesketh): Provide some more useful feedback and/or checking
            raise Exception("One or more hosts failed")

        r = self.execute_ansible_play(d.bootstrap_play())

        if r.host_failed or r.host_unreachable:
            # TODO(jhesketh): Provide some more useful feedback and/or checking
            raise Exception("One or more hosts failed")

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy()
