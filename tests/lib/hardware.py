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

import uuid

import libcloud.security
from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver

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
        self.libcloud_driver = self.get_driver()
        # Quick test to prove driver is working
        print("*"*120)
        print(self.libcloud_driver.list_sizes())

    def get_driver(self):
        driver = None
        if config.CLOUD_PROVIDER == 'OPENSTACK':
            OpenStack = get_driver(Provider.OPENSTACK)

            driver = OpenStack(
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
        return driver

    def boot_nodes(self, n=3):
        # Create n nodes for the cluster
        for _ in range(n):
            node_name = "%s%s_%d" % (
                config.CLUSTER_PREFIX, self.hardware_uuid, n)
            self.nodes[node_name] = {}

    def destroy(self):
        # Remove nodes
        print("destroy nodes")
        print(self)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy()
