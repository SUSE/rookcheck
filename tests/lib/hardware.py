# Copyright (c) 2019 SUSE LINUX GmbH
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

from io import StringIO
import uuid

import libcloud.security
from libcloud.compute.base import NodeAuthSSHKey
from libcloud.compute.deployment import MultiStepDeployment, ScriptDeployment
from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver
import paramiko

from tests import config

libcloud.security.VERIFY_SSL_CERT = config.VERIFY_SSL_CERT


# The Hardware module should take care of the operating system abstraction
# through images.
# libcloud will provide a common set of cloud-agnostic objects such as Node[s]
# We might extend the Node object to have an easy way to run arbitrary commands
# on the node such as Node.execute().
# There will be a challenge where those arbitrary commands differ between OS's;
# this is an abstraction that is not yet well figured out, but will likely
# take the form of cloud-init or similar bringing the target node to an
# expected state.


class Hardware():
    def __init__(self):
        # Boot nodes
        print("boot nodes")
        print(self)
        self.nodes = {}
        self.hardware_uuid = str(uuid.uuid4())[:8]
        self.libcloud_conn = self.get_driver_connection()

        self._image_cache = {}
        self._size_cache = {}
        self._ex_network_cache = {}

        self.pubkey, self.private_key = self.generate_keys()

    def get_driver_connection(self):
        """ Get a libcloud connection object for the configured driver """
        connection = None
        if config.CLOUD_PROVIDER == 'OPENSTACK':
            # TODO(jhesketh): Provide a sensible way to allow configuration
            #                 of extended options on a per-provider level.
            #                 For example, the setting of OpenStack networks.
            OpenStackDriver = get_driver(Provider.OPENSTACK)

            connection = OpenStackDriver(
                config.OS_USERNAME,
                config.OS_PASSWORD,
                ex_force_auth_url=config.OS_AUTH_URL,
                ex_force_auth_version=config.OS_AUTH_VERSION,
                ex_domain_name=config.OS_USER_DOMAIN,
                ex_tenant_name=config.OS_PROJECT,
                ex_tenant_domain_id=config.OS_PROJECT_DOMAIN,
                ex_force_service_region=config.OS_REGION,
                secure=config.VERIFY_SSL_CERT,
            )
        else:
            raise Exception("Cloud provider not yet supported by smoke_rook")
        return connection

    def deployment_steps(self):
        """ The base deployment steps to perform on each node """
        yield ScriptDeployment('echo "hi" && touch ~/i_was_here')

    def get_image_by_name(self, name):
        if name in self._image_cache:
            return self._image_cache[name]
        self._image_cache[name] = self.libcloud_conn.get_image(name)
        return self._image_cache[name]

    def get_size_by_name(self, name):
        if self._size_cache:
            sizes = self._size_cache
        else:
            sizes = self.libcloud_conn.list_sizes()
            self._size_cache = sizes

        for node_size in sizes:
            if node_size.name == name:
                return node_size

        return None

    def get_ex_network_by_name(self, name):
        if self._ex_network_cache:
            networks = self._ex_network_cache
        else:
            networks = self.libcloud_conn.ex_list_networks()
            self._ex_network_cache = networks

        for network in networks:
            if network.name == name:
                return network

        return None

    def generate_keys(self):
        """
        Generatees a public and private key
        """
        key = paramiko.RSAKey.generate(2048)
        private_string = StringIO()
        key.write_private_key(private_string)
        return ("%s %s" % (key.get_name(), key.get_base64()),
                private_string.getvalue())

    def boot_nodes(self, n=1):
        """
        Boot n nodes
        """

        print(self.pubkey)
        print(self.private_key)

        # TODO(jhesketh): Move this out of boot_nodes
        sshkey_name = "%s%s_key" % (config.CLUSTER_PREFIX, self.hardware_uuid)
        self._ex_os_key = self.libcloud_conn.ex_import_keypair_from_string(
            sshkey_name, self.pubkey)

        # Create n nodes for the cluster
        for _ in range(n):
            node_name = "%s%s_%d" % (
                config.CLUSTER_PREFIX, self.hardware_uuid, n)

            # TODO(jhesketh): Move cloud-specific configuration elsewhere
            kwargs = {}
            kwargs['networks'] = [self.get_ex_network_by_name('user')]
            kwargs['ex_keyname'] = sshkey_name

            # Can't use deploy_node because there is no public ip yet
            self.nodes[node_name] = self.libcloud_conn.create_node(
                name=node_name,
                size=self.get_size_by_name(config.NODE_SIZE),
                image=self.get_image_by_name("e9de104d-f03a-4d9f-8681-e5dd4e9cede7"),
                auth=NodeAuthSSHKey(self.pubkey),
                **kwargs,
            )

            print("Created node: ")
            print(self.nodes[node_name])

            # TODO(jhesketh): Move cloud-specific configuration elsewhere
            floating_ip = self.libcloud_conn.ex_create_floating_ip('floating')

            print("Created floating IP: ")
            print(floating_ip)

            # TODO(jhesketh): Find a better way to wait for the node before
            #                 assigning floating ip's
            import time
            time.sleep(30)
            self.libcloud_conn.ex_attach_floating_ip_to_node(
                self.nodes[node_name], floating_ip)
            self._floating_ip = floating_ip

    def destroy(self):
        # Remove nodes
        print("destroy nodes")
        print(self)

        import time
        time.sleep(60)

        for node in self.nodes.values():
            node.destroy()
        self._floating_ip.delete()
        self.libcloud_conn.delete_key_pair(self._ex_os_key)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy()
