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


import logging
from typing import List, Optional
import threading
import string
import random

import openstack

from tests.config import settings
from tests.lib.hardware.hardware_base import HardwareBase
from tests.lib.hardware.node_base import NodeBase, NodeRole
from tests.lib.workspace import Workspace


logger = logging.getLogger(__name__)


class Node(NodeBase):
    def __init__(self, name: str, role: NodeRole, tags: List[str],
                 conn: openstack.connection.Connection,
                 flavor, image, network_private,
                 network_public, security_group, keypair: str):
        super().__init__(name, role, tags)
        self._name = name
        self._role = role
        self._tags = tags
        self._conn = conn
        self._flavor = flavor
        self._image = image
        self._network_private = network_private
        self._network_public = network_public
        self._security_group = security_group
        self._keypair = keypair
        self._instance = None

    def boot(self):
        instance = self._conn.get_server(self._name)
        if instance:
            raise Exception(f"Node {self._name} ({instance['id']}) already"
                            "available")

        logger.info(f"Node creating with name '{self._name}' ...")
        self._instance = self._conn.create_server(
            self._name, image=self._image, flavor=self._flavor,
            key_name=self._keypair, network=self._network_private,
            security_groups=[self._security_group.id], wait=True, auto_ip=True)
        logger.info(f"Node instance {self._instance['name']} "
                    f"({self._instance['id']}) created")
        # add floating IP
        try:
            # this might fail (eg. on OVH)
            self._conn.add_auto_ip(self._instance)
            # update instance data (to be able to get the floating ip)
            self._instance = self._conn.get_server(self._instance)
        except Exception:
            pass
        self._floating_ip = self._get_floating_ip()
        logger.info(f"Node {self._name} has IP {self._floating_ip}")
        if self._role == NodeRole.WORKER:
            for i in range(0, settings.WORKER_INITIAL_DATA_DISKS):
                disk_name = self.disk_create(10)
                self.disk_attach(name=disk_name)

    def get_ssh_ip(self) -> str:
        return self._floating_ip

    def _get_vol_name_by_vol(self, volume):
        for k, v in self._disks.items():
            if v['volume'].id == volume.id:
                return k

    def disk_create(self, capacity):
        super().disk_create(capacity)
        suffix = ''.join(random.choice(string.ascii_lowercase)
                         for i in range(5))
        name = f"{self._name}-volume-{suffix}"
        volume = self._conn.create_volume(capacity, name=name,
                                          delete_on_termination=True)
        self._disks[name] = {'volume': volume, 'attached': False}
        logger.info(f"disk {name} ({volume.id}) created")
        return name

    def disk_attach(self, name=None, volume=None):
        if name is None and volume is None:
            raise Exception("Please specify either name or volume parameter")
        if name is not None:
            volume = self._disks[name]['volume']
        else:
            name = self._get_vol_name_by_vol(volume)
        self._conn.attach_volume(self._instance, volume)
        self._disks[name]['attached'] = True
        logger.info(f"Volume {name} attached")
        # update instance data (so _instance.volumes is up-to-date)
        self._instance = self._conn.get_server(self._instance)

    def disk_detach(self, name):
        volume = self._disks[name]['volume']
        self._conn.detach_volume(self._instance, volume)
        self._disks[name]['attached'] = False
        logger.info(f"Volume {name} detached")
        # update instance data (so _instance.volumes is up-to-date)
        self._instance = self._conn.get_server(self._instance)

    def get_device_name(self, disk_name):
        volume_name = self._conn.get_volume(
            disk_name)['attachments'][0]['device']
        logger.info(f"Device {disk_name} got attached as {volume_name}")
        return volume_name

    def destroy(self):
        super().destroy()
        if self._instance:
            self._conn.delete_server(self._instance, wait=True,
                                     delete_ips=True)
            logger.info(f"Node {self._name} ({self._instance.id}) deleted")
            for k, v in self._disks.items():
                _id = v['volume'].id
                self._conn.delete_volume(v['volume'])
                logger.info(f"Deleted volume {k} ({_id})")

    def _get_floating_ip(self) -> Optional[str]:
        """
        try to find a public available IP for the instance
        """
        if self._instance:
            for addr in self._instance['addresses'].get(
                    self._network_private.name, []):
                if addr['version'] != 4:
                    continue
                if addr['OS-EXT-IPS:type'] == self._network_public.name:
                    return addr['addr']
            for addr in self._instance['addresses'].get(
                    self._network_public.name, []):
                if addr['version'] != 4:
                    continue
                return addr['addr']
        return None


class Hardware(HardwareBase):
    def __init__(self, workspace: Workspace):
        super().__init__(workspace)
        self._workspace = workspace
        self._conn = self.get_connection()

        # check if the external network is there
        self._network_public = self._conn.get_network(
            settings.OPENSTACK.EXTERNAL_NETWORK)
        if not self._network_public:
            raise Exception(f"External network "
                            f"{settings.OPENSTACK.EXTERNAL_NETWORK} not found."
                            " Check OPENSTACK.EXTERNAL_NETWORK setting")

        # check if image is available
        self._image = self._conn.get_image(settings.OPENSTACK.NODE_IMAGE)
        if not self._image:
            raise Exception(f"Node image {settings.OPENSTACK.NODE_IMAGE} not "
                            "found. Check OPENSTACK.NODE_IMAGE setting")

        # check if flavor is available
        self._flavor = self._conn.get_flavor(settings.OPENSTACK.NODE_SIZE)
        if not self._flavor:
            raise Exception(f"Node flavor {settings.OPENSTACK.NODE_SIZE} not "
                            "found. Check OPENSTACK.NODE_SIZE setting")

        # basic setup needed for all nodes
        self._keypair = self._create_keypair()
        self._security_group = self._create_security_group()
        # the private network
        self._network_private, self._subnet_private, self._router_private = \
            self._create_network_private()

    def get_connection(self):
        return openstack.connect()

    def node_create(self, name: str, role: NodeRole,
                    tags: List[str]) -> NodeBase:
        super().node_create(name, role, tags)
        node = Node(name, role, tags, self.get_connection(),
                    self._flavor, self._image,
                    self._network_private, self._network_public,
                    self._security_group, self._keypair.name)
        node.boot()
        return node

    def _node_create_add(self, name: str, role: NodeRole,
                         tags: List[str]):
        node = self.node_create(name, role, tags)
        self.node_add(node)

    def boot_nodes(self, masters: int, workers: int, offset: int = 0):
        super().boot_nodes(masters, workers, offset)
        threads = []
        for m in range(0, masters):
            if m == 0:
                tags = ['master', 'first_master']
            else:
                tags = ['master']
            node_name = "%s-master-%d" % (self.workspace.name, m+offset)

            thread = threading.Thread(
                target=self._node_create_add, args=(node_name, NodeRole.MASTER,
                                                    tags))
            threads.append(thread)
            thread.start()

        for m in range(0, workers):
            tags = ['worker']
            node_name = "%s-worker-%d" % (self.workspace.name, m+offset)
            thread = threading.Thread(
                target=self._node_create_add, args=(node_name, NodeRole.WORKER,
                                                    tags))
            threads.append(thread)
            thread.start()

        # wait for all threads to finish
        for t in threads:
            t.join()

    def destroy(self, skip=False):
        super().destroy(skip=skip)

        if skip:
            if self._router_private:
                logger.warning(f"Leaving router {self._router_private.name}")
            if self._subnet_private:
                logger.warning(f"Leaving subnet {self._subnet_private.name}")
            if self._network_private:
                logger.warning(f"Leaving network {self._network_private.name}")
            if self._security_group:
                logger.warning(
                    f"Leaving security group {self._security_group.name}")
            if self._keypair:
                logger.warning(f"Leaving keypair {self._keypair.name}")
            return

        self._delete_network_private()
        self._delete_security_group()
        self._delete_keypair()

    def _create_network_private(self):
        net_name = f"{self.workspace.name}-net"
        subnet_name = f"{self.workspace.name}-subnet"
        router_name = f"{self.workspace.name}-router"

        net = self._conn.network.create_network(name=net_name)
        logger.info(f"network {net.name} ({net.id}) created")
        subnet = self._conn.network.create_subnet(
            name=subnet_name, network_id=net.id, ip_version='4',
            cidr='192.168.100.0/24')
        logger.info(f"subnet {subnet.name} ({subnet.id}) created")
        router = self._conn.network.create_router(
            name=router_name, external_gateway_info={
                "network_id": self._network_public.id
            })
        logger.info(f"router {router.name} ({router.id}) created")
        self._conn.network.add_interface_to_router(router, subnet_id=subnet.id)
        return net, subnet, router

    def _delete_network_private(self):
        if self._router_private:
            self._conn.network.remove_interface_from_router(
                self._router_private.id, self._subnet_private.id)
            self._conn.network.delete_router(self._router_private.id)
            logger.info(f"router {self._router_private.name} "
                        f"({self._router_private.id}) deleted")
            self._router_private = None
        if self._subnet_private:
            self._conn.network.delete_subnet(self._subnet_private.id)
            logger.info(f"subnet {self._subnet_private.name} "
                        f"({self._subnet_private.id}) deleted")
            self._subnet_private = None
        if self._network_private:
            self._conn.network.delete_network(self._network_private.id)
            logger.info(f"network {self._network_private.name} "
                        f"({self._network_private.id}) deleted")
            self._network_private = None

    def _create_security_group(self):
        sg_name = f"{self.workspace.name}-sg"
        sg = self._conn.network.create_security_group(
            name=sg_name, description='Permissive firewall for rookcheck')
        logger.info(f"security group {sg_name} ({sg.id}) created")
        for proto in ['tcp', 'udp']:
            self._conn.network.create_security_group_rule(
                direction='ingress', ethertype='IPv4', port_range_min=1,
                port_range_max=65535, protocol=proto,
                security_group_id=sg.id)
        return sg

    def _delete_security_group(self):
        if self._security_group:
            self._conn.network.delete_security_group(self._security_group.id)
            logger.info(f"security group {self._security_group.name} "
                        f"({self._security_group.id}) deleted")
            self._security_group = None

    def _create_keypair(self):
        name = f"{self.workspace.name}-keypair"
        keypair = self._conn.create_keypair(
            name, self.workspace.public_key)
        logger.info(f"keypair {name} created")
        return keypair

    def _delete_keypair(self):
        if self._keypair:
            self._conn.delete_keypair(self._keypair.name)
            logger.info(f"keypair {self._keypair.name} deleted")

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy()
