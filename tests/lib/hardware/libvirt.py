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

# The Hardware module should take care of the operating system abstraction
# through images.
# There will be a challenge where those arbitrary commands differ between OS's;
# this is an abstraction that is not yet well figured out, but will likely
# take the form of cloud-init or similar bringing the target node to an
# expected state.

import netaddr
import os
import shutil
import time
import tempfile
import textwrap
import threading
import wget
import datetime
import logging
import libvirt
import uuid
import paramiko
import socket
from typing import List
from xml.dom import minidom
import string
import random

from tests.config import settings
from tests.lib.common import execute
from tests.lib.hardware.hardware_base import HardwareBase
from tests.lib.hardware.node_base import NodeBase, NodeRole
from tests.lib.workspace import Workspace

logger = logging.getLogger(__name__)

# this lock needs to resolve race condition issue while defining a node
libvirt_define_node_lock = threading.Lock()


class Node(NodeBase):
    def __init__(self, name, role, tags, conn, image_path,
                 network, memory, workspace):
        super().__init__(name, role, tags)
        self._conn = conn
        self._image_path = image_path
        self._network = network
        self._memory = memory * 1024 * 1024
        self._workspace = workspace
        self._ssh_public_key = workspace.public_key
        self._ssh_private_key = workspace.private_key
        self._snap_img_path = os.path.join(
            workspace.working_dir, f"{self.name}-snapshot.qcow2")
        self._cloud_init_seed_path = os.path.join(
            workspace.working_dir, f"{self.name}-cloud-init-seed.img")

    def boot(self):
        self._backing_file_create()
        self._cloud_init_seed_create()
        xml = self._get_domain(self.name, self._snap_img_path,
                               self._cloud_init_seed_path,
                               self._network.name(), self._memory)
        logger.info(f"node {self.name}: booting with "
                    f"image {self._snap_img_path}")
        logger.debug(f"node {self.name}: libvirt xml: {xml}")
        try:
            libvirt_define_node_lock.acquire()
            self._dom = self._conn.defineXML(xml)
        except libvirt.libvirtError as e:
            logger.error(
                f"unable to define node '{self.name}' using xml: {xml}")
            raise e
        finally:
            libvirt_define_node_lock.release()

        self._dom.create()
        if self._role == NodeRole.WORKER:
            for i in range(0, settings.WORKER_INITIAL_DATA_DISKS):
                disk_name = self.disk_create(10)
                self.disk_attach(name=disk_name)
        self._ips = self._get_ips()
        self._wait_for_ssh()

    def destroy(self):
        self._dom.destroy()
        self._dom.undefine()
        if os.path.exists(self._cloud_init_seed_path):
            os.remove(self._cloud_init_seed_path)
        if os.path.exists(self._snap_img_path):
            os.remove(self._snap_img_path)
        for k, v in self._disks.items():
            os.remove(v['path'])
            logger.info(f"Deleted disk {k} at path {v['path']}")

    def get_ssh_ip(self):
        return self._ips[0]

    def _wait_for_ssh(self, timeout=180):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ip = self.get_ssh_ip()
        stop = datetime.datetime.now() + datetime.timedelta(seconds=timeout)
        logger.info(f"node {self.name}: waiting {timeout} s for ssh to "
                    f"{settings.NODE_IMAGE_USER}@{ip}")
        while datetime.datetime.now() < stop:
            try:
                ssh.connect(ip, username=settings.NODE_IMAGE_USER,
                            key_filename=self._ssh_private_key)
                logger.info(f"node {self.name}: ssh ready for user "
                            f"{settings.NODE_IMAGE_USER}")
                return
            except (paramiko.BadHostKeyException,
                    paramiko.AuthenticationException,
                    paramiko.ssh_exception.SSHException,
                    socket.error):
                time.sleep(3)
        raise Exception(f"node {self.name}: Timeout while waiting for "
                        f"ssh on {ip}")

    def _get_ips(self, timeout=120):
        """get the ip addresses of the guest domain from the DHCP leases"""
        ips_found = []
        xmldoc = minidom.parseString(self._dom.XMLDesc())
        mac_list = xmldoc.getElementsByTagName('mac')
        stop = datetime.datetime.now() + datetime.timedelta(seconds=timeout)
        logger.info(f"node {self.name}: wait {timeout}s to get IP address")
        while len(mac_list) and datetime.datetime.now() < stop:
            for mac in mac_list:
                mac_addr = mac.attributes["address"].value
                for d in self._network.DHCPLeases():
                    if d['mac'].lower() == mac_addr.lower():
                        ips_found.append(d['ipaddr'])
            if len(ips_found):
                logger.info(f"node {self.name}: found IPs {ips_found}")
                return ips_found
            time.sleep(3)
        raise Exception(f"node {self.name}: no IP address found")

    def _backing_file_create(self):
        if os.path.exists(self._snap_img_path):
            logger.info(f"node {self.name}: Delete available backing image "
                        f"{self._snap_img_path}")
            os.remove(self._snap_img_path)
        execute(f"qemu-img create -f qcow2 -F qcow2 -o "
                f"backing_file={self._image_path} {self._snap_img_path} 10G")
        logger.info(f"node {self.name}: created qcow2 backing file under"
                    f"{self._snap_img_path}")

    def disk_create(self, capacity):
        """
        Create a disk volume
        """
        super().disk_create(capacity)
        capacity_gb = f"{capacity}G"
        suffix = ''.join(random.choice(string.ascii_lowercase)
                         for i in range(5))
        name = f"{self._name}-volume-{suffix}"
        disk_path = os.path.join(self._workspace.working_dir,
                                 f"{name}.qcow2")
        execute(f"qemu-img create -f qcow2 {disk_path} {capacity_gb}")
        self._disks[name] = {
            'path': disk_path,
            'attached': False,
            'xml': None
        }
        logger.info(f"disk {name} created")
        return name

    def _get_next_disk_letter(self):
        """
        Return the next available device name for disks
        """
        alphabet = list(string.ascii_lowercase)
        xmldoc = minidom.parseString(self._dom.XMLDesc())
        disks = xmldoc.getElementsByTagName('disk')
        for element in disks:
            # get X in vdX and remove it from usable ones
            # only consider 'virtio' bus
            if element.getElementsByTagName(
                    'target')[0].getAttribute('bus') == 'virtio':
                alphabet.remove(element.getElementsByTagName(
                    'target')[0].getAttribute('dev')[-1])
        return 'vd' + alphabet[0]

    def disk_attach(self, name):
        """
        Attach a disk volume
        """
        block_device = self._get_next_disk_letter()
        disk = textwrap.dedent("""
            <disk type='file' device='disk'>
                <driver name='qemu' type='qcow2' cache='writeback'/>
                <source file='%(disk_path)s'/>
                <target dev='%(block_device)s' bus='virtio'/>
            </disk>
        """ % {"disk_path": self._disks[name]['path'],
               "block_device": block_device
               })
        self._disks[name]['xml'] = disk
        self._dom.attachDevice(disk)
        logger.info(f"Attached volume {name} as device {block_device}")

    def disk_detach(self, name):
        """
        Detach a disk volume
        """
        self._dom.detachDevice(self._disks[name]['xml'])
        logger.info(f"Detached volume {name}")

    def _cloud_init_seed_create(self):
        user_data = textwrap.dedent("""
            #cloud-config
            debug: True
            ssh_authorized_keys:
                - {}
        """)
        meta_data = textwrap.dedent("""
            ---
            instance-id: {}
            local-hostname: {}
        """)

        iso_cmd = shutil.which('mkisofs')
        if not iso_cmd:
            raise Exception('mkisofs command not found')

        if os.path.exists(self._cloud_init_seed_path):
            os.remove(self._cloud_init_seed_path)
        with tempfile.TemporaryDirectory() as tempdir:
            with open(os.path.join(tempdir, 'user-data'), 'w') as ud:
                ud.write(user_data.format(self._ssh_public_key))
            with open(os.path.join(tempdir, 'meta-data'), 'w') as md:
                md.write(meta_data.format(uuid.uuid4(), self.name))
            # create the seed file
            args = [iso_cmd,
                    '-output', self._cloud_init_seed_path,
                    '-volid', 'cidata',
                    '-joliet', '-rock',
                    tempdir]
            execute(" ".join(args), log_stdout=False, log_stderr=False)

    def _get_domain(self, domain_name, image, cloud_init_seed, network_name,
                    memory):
        return textwrap.dedent("""
            <domain type='kvm'>
                <name>%(domain_name)s</name>
                <memory unit='KiB'>%(memory)s</memory>
                <currentMemory unit='KiB'>%(memory)s</currentMemory>
                <vcpu placement='static'>2</vcpu>
                <cpu mode='host-passthrough'></cpu>
                <!--<cpu mode='host-model'>
                    <feature policy='require' name='vmx'/>
                </cpu>-->
                <os>
                    <type arch='x86_64' machine='pc-i440fx-2.1'>hvm</type>
                    <boot dev='hd'/>
                </os>
                <features>
                    <acpi/>
                </features>
                <on_poweroff>destroy</on_poweroff>
                <on_reboot>restart</on_reboot>
                <on_crash>restart</on_crash>
                <devices>
                    <emulator>/usr/bin/qemu-system-x86_64</emulator>
                    <disk type='file' device='disk'>
                        <driver name='qemu' type='qcow2' cache='writeback'/>
                        <source file='%(image)s'/>
                        <target dev='vda' bus='virtio'/>
                    </disk>
                    <disk type='file' device='cdrom'>
                        <driver name='qemu' type='raw' />
                        <source file='%(cloud_init_seed)s'/>
                        <target dev='sda' bus='sata'/>
                        <readonly/>
                    </disk>
                    <controller type='virtio-serial' index='0'>
                        <address type='pci' domain='0x0000' bus='0x00'
                                 slot='0x05' function='0x0'/>
                    </controller>
                    <interface type='network'>
                        <source network='%(network_name)s'/>
                        <model type='virtio'/>
                        <address type='pci' domain='0x0000' bus='0x00'
                                 slot='0x03' function='0x0'/>
                    </interface>
                    <serial type='pty'>
                        <target port='0'/>
                    </serial>
                    <console type='pty'>
                        <target type='serial' port='0'/>
                    </console>
                    <channel type='spicevmc'>
                        <target type='virtio' name='com.redhat.spice.0'/>
                        <address type='virtio-serial' controller='0' bus='0'
                                 port='1'/>
                    </channel>
                    <input type='mouse' bus='ps2'/>
                    <input type='keyboard' bus='ps2'/>
                    <graphics type='spice' autoport='yes'/>
                    <video>
                        <model type='vga'/>
                    </video>
                    <redirdev bus='usb' type='spicevmc'></redirdev>
                    <memballoon model='virtio'>
                        <address type='pci' domain='0x0000' bus='0x00'
                                 slot='0x06' function='0x0'/>
                    </memballoon>
                </devices>
            </domain>
        """ % {
            "domain_name": domain_name, "image": image,
            "cloud_init_seed": cloud_init_seed,
            "network_name": network_name,
            "memory": memory
        })


class Hardware(HardwareBase):
    def __init__(self, workspace: Workspace):
        super().__init__(workspace)
        self._network = self._create_network()
        if not self._network:
            raise Exception('Can not get libvirt network %s' %
                            settings.LIBVIRT.NETWORK_RANGE)
        logger.info(f"Got libvirt network {self._network.name()}")
        self._image_path = self._get_image_path()

    def _get_image_path(self):
        if (settings.LIBVIRT.IMAGE.startswith("http://") or
                settings.LIBVIRT.IMAGE.startswith("https://")):
            logging.info(
                f"Downloading image from {settings.LIBVIRT.IMAGE}")
            download_location = os.path.join(
                self.workspace.working_dir,
                os.path.basename(settings.LIBVIRT.IMAGE)
            )
            wget.download(
                settings.LIBVIRT.IMAGE,
                download_location,
                bar=None
            )
            return download_location
        return settings.LIBVIRT.IMAGE

    def _create_network(self):
        network_range = netaddr.IPNetwork(settings.LIBVIRT.NETWORK_RANGE)
        subnets = network_range.subnet(
            int(settings.LIBVIRT.NETWORK_SUBNET))
        for network in subnets:
            host_ip = str(netaddr.IPAddress(network.first+1))
            netmask = str(network.netmask)
            dhcp_start = str(netaddr.IPAddress(network.first+2))
            dhcp_end = str(netaddr.IPAddress(network.last-1))
            xml = textwrap.dedent("""
                <network>
                <name>%(network_name)s</name>
                <forward mode="nat"/>
                <ip address="%(host_ip)s" netmask="%(netmask)s">
                    <dhcp>
                        <range start="%(dhcp_start)s" end="%(dhcp_end)s" />
                    </dhcp>
                </ip>
                </network>
            """ % {
                "network_name": self.workspace.name,
                "host_ip": host_ip,
                "netmask": netmask,
                "dhcp_start": dhcp_start,
                "dhcp_end": dhcp_end,
            })
            try:
                net = self._conn.networkCreateXML(xml)
            except libvirt.libvirtError as e:
                if "Network is already in use" in e.get_error_message():
                    logger.debug(f"Network {network} is already in use."
                                 f" Trying next subnet..")
                    continue
                raise
            logger.info(f"created network {network} as {net.name()}")
            return net

    def get_connection(self):
        conn = libvirt.open(settings.LIBVIRT.CONNECTION)
        if not conn:
            raise Exception('Can not open libvirt connection %s' %
                            settings.LIBVIRT.CONNECTION)
        logger.debug(f"Got connection to libvirt: {conn}")
        return conn

    def node_create(self, name: str, role: NodeRole,
                    tags: List[str]) -> NodeBase:
        super().node_create(name, role, tags)
        # get a fresh connection to avoid threading problems
        conn = self.get_connection()
        node = Node(name, role, tags, conn, self._image_path, self._network,
                    settings.LIBVIRT.VM_MEMORY, self.workspace)
        node.boot()
        return node

    def _boot_node(self, name: str, role: NodeRole, tags: List[str]):
        node = self.node_create(name, role, tags)
        self.node_add(node)

    def boot_nodes(self, masters: int, workers: int, offset: int = 0):
        super().boot_nodes(masters, workers, offset)
        threads = []
        for c in range(0, masters):
            if c == 0:
                tags = ['master', 'first_master']
            else:
                tags = ['master']
            t = threading.Thread(
                target=self._boot_node, args=(
                    f"{self.workspace.name}-master-{c}",
                    NodeRole.MASTER, tags))
            threads.append(t)
            t.start()

        for c in range(0, workers):
            t = threading.Thread(
                target=self._boot_node, args=(
                    f"{self.workspace.name}-worker-{c}",
                    NodeRole.WORKER, ['worker']))
            threads.append(t)
            t.start()

        # wait for all threads to finish
        for t in threads:
            t.join()

    def destroy(self, skip=False):
        super().destroy(skip=skip)

        if skip:
            logger.warning(f"Leaving network {self._network.name()}")
            return

        self._network.destroy()
        logger.info(f"network {self._network.name()} destroyed")
