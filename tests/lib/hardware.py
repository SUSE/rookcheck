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

# The Hardware module should take care of the operating system abstraction
# through images.
# libcloud will provide a common set of cloud-agnostic objects such as Node[s]
# We might extend the Node object to have an easy way to run arbitrary commands
# on the node such as Node.execute().
# There will be a challenge where those arbitrary commands differ between OS's;
# this is an abstraction that is not yet well figured out, but will likely
# take the form of cloud-init or similar bringing the target node to an
# expected state.

from abc import ABC, abstractmethod
import os
import subprocess
import shutil
import tarfile
import tempfile
import threading
import time
import urllib.request
import uuid
import yaml

from ansible.module_utils.common.collections import ImmutableDict
from ansible.parsing.dataloader import DataLoader
from ansible.vars.manager import VariableManager
from ansible.inventory.manager import InventoryManager
from ansible.playbook.play import Play
from ansible import context as ansible_context
import ansible.plugins.loader
import ansible.executor.task_queue_manager
from ansible.plugins.callback.default import CallbackModule
import ansible.constants as C
import libcloud.security
from libcloud.compute.deployment import ScriptDeployment
from libcloud.compute.types import Provider, NodeState, StorageVolumeState
from libcloud.compute.providers import get_driver
from paramiko.client import AutoAddPolicy, SSHClient
import paramiko.rsakey
from urllib.parse import urlparse


from tests import config

libcloud.security.VERIFY_SSL_CERT = config.VERIFY_SSL_CERT


class Distro(ABC):
    @abstractmethod
    def bootstrap_play(self):
        pass


class SUSE(Distro):
    def wait_for_connection_play(self):
        # In order to be able to use mitogen we need to install python on the
        # nodes
        tasks = []

        tasks.append(
            dict(
                name="Wait for connection to hosts",
                action=dict(
                    module='wait_for_connection',
                    args=dict(
                        timeout=300
                    )
                )
            )
        )

        play_source = dict(
            name="Wait for nodes",
            hosts="all",
            tasks=tasks,
            gather_facts="no",
            strategy="free",
        )

        return play_source

    def bootstrap_play(self):
        tasks = []

        tasks.append(
            dict(
                name="Installing dependencies",
                action=dict(
                    module='zypper',
                    args=dict(
                        name=['bash-completion',
                              'ca-certificates',
                              'conntrack-tools',
                              'curl',
                              'docker',
                              'ebtables',
                              'ethtool',
                              'lvm2',
                              'lsof',
                              'ntp',
                              'socat',
                              'tree',
                              'vim',
                              'wget',
                              'xfsprogs'],
                        state='present',
                        extra_args_precommand='--non-interactive '
                                              '--gpg-auto-import-keys',
                        update_cache='yes',
                    )
                )
            )
        )

        tasks.append(
            dict(
                name="Updating kernel",
                action=dict(
                    module='zypper',
                    args=dict(
                        name='kernel-default',
                        state='latest',
                        extra_args_precommand='--non-interactive '
                                              '--gpg-auto-import-keys',
                    )
                )
            )
        )

        tasks.append(
            dict(
                name="Removing anti-dependencies",
                action=dict(
                    module='zypper',
                    args=dict(
                        name='firewalld',
                        state='absent',
                        extra_args_precommand='--non-interactive '
                                              '--gpg-auto-import-keys',
                    )
                )
            )
        )

        tasks.append(
            dict(
                name="Enabling docker",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd="systemctl enable --now docker",
                    )
                )
            )
        )

        # TODO(jhesketh): These commands are lifted from dev-rook-ceph. However
        # it appears that the sysctl settings are reset after reboot so they
        # may not be useful here.
        tasks.append(
            dict(
                name="Raising max open files",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd="sysctl -w fs.file-max=1200000",
                    )
                )
            )
        )

        tasks.append(
            dict(
                name="Minimize swappiness",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd="sysctl -w vm.swappiness=0",
                    )
                )
            )
        )

        # TODO(jhesketh): Figure out if this is appropriate for all OpenStack
        #                 clouds.
        config = "\nIPADDR_0={{ ansible_host }}/32"
        config += "\nLABEL_0=Floating\n"
        tasks.append(
            dict(
                name="Add floating IP to eth0",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd='printf "%s" >> /etc/sysconfig/network/ifcfg-eth0'
                            % config,
                    )
                )
            )
        )

        # Alternate approach that likely doesn't require setting --node-ip with
        # kubelet (as it'll default to the floating ip).
        # Set static IP to be the floating,
        # add second IP for the internal network,
        # Create default route,
        # Set up DNS again

        tasks.append(
            dict(
                name="Reboot nodes",
                action=dict(
                    module='reboot',
                )
            )
        )

        tasks.append(
            dict(
                name="Setting iptables on nodes to be permissive",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd="iptables -I INPUT -j ACCEPT && "
                            "iptables -P INPUT ACCEPT",
                    )
                )
            )
        )

        play_source = dict(
            name="Prepare nodes",
            hosts="all",
            tasks=tasks,
            gather_facts="no",
            strategy="mitogen_free",
        )
        return play_source


class ResultCallback(CallbackModule):
    """This callback stores the latest results for a run in an instance
    variable (host_ok, host_unreachable, host_failed).
    It is intended to be instanciated for each individual run.
    """
    def __init__(self):
        super(ResultCallback, self).__init__()
        self._load_name = "CustomResultCallback"
        self.set_options()
        self.host_ok = {}
        self.host_unreachable = {}
        self.host_failed = {}

    def v2_runner_on_unreachable(self, result):
        if result._host.get_name() not in self.host_unreachable:
            self.host_unreachable[result._host.get_name()] = []
        self.host_unreachable[result._host.get_name()].append(result)
        super(ResultCallback, self).v2_runner_on_unreachable(result)

    def v2_runner_on_ok(self, result):
        if result._host.get_name() not in self.host_ok:
            self.host_ok[result._host.get_name()] = []
        self.host_ok[result._host.get_name()].append(result)
        super(ResultCallback, self).v2_runner_on_ok(result)

    def v2_runner_on_failed(self, result, ignore_errors=False):
        if result._host.get_name() not in self.host_failed:
            self.host_failed[result._host.get_name()] = []
        self.host_failed[result._host.get_name()].append(result)
        super(ResultCallback, self).v2_runner_on_failed(result, ignore_errors)


class AnsibleRunner(object):
    def __init__(self, nodes, working_dir=None):
        # since the API is constructed for CLI it expects certain options to
        # always be set in the context object
        ansible_context.CLIARGS = ImmutableDict(
            connection='ssh', module_path=[''], forks=10,
            gather_facts='no', host_key_checking=False,
            verbosity=4
        )

        # Takes care of finding and reading yaml, json and ini files
        self.loader = DataLoader()
        self.passwords = dict(vault_pass='secret')

        # create inventory, use path to host config file as source or hosts in
        # a comma separated string
        self.inventory_file = self.create_inventory(nodes, working_dir)
        self.inventory = InventoryManager(
            loader=self.loader, sources=self.inventory_file)

        # variable manager takes care of merging all the different sources to
        # give you a unified view of variables available in each context
        self.variable_manager = VariableManager(
            loader=self.loader, inventory=self.inventory)

        mitogen_plugin = self.download_mitogen(working_dir)

        # Hack around loading strategy modules:
        ansible.executor.task_queue_manager.strategy_loader = \
            ansible.plugins.loader.PluginLoader(
                'StrategyModule',
                'ansible.plugins.strategy',
                [mitogen_plugin] + C.DEFAULT_STRATEGY_PLUGIN_PATH,
                'strategy_plugins',
                required_base_class='StrategyBase',
            )

    def create_inventory(self, nodes, working_dir=None):
        if not working_dir:
            # NOTE(jhesketh): The working dir is never cleaned up. This is
            # somewhat deliberate to keep the private key if it is needed for
            # debugging.
            working_dir = tempfile.mkdtemp()

        inv = {
            'all': {
                'hosts': {},
                'children': {}
            }
        }

        for node in nodes.values():
            if not node.tags:
                inv['all']['hosts'][node.name] = node.ansible_inventory_vars()
            else:
                for tag in node.tags:
                    if tag not in inv['all']['children']:
                        inv['all']['children'][tag] = {'hosts': {}}
                    inv['all']['children'][tag]['hosts'][node.name] = \
                        node.ansible_inventory_vars()

        inv_path = os.path.join(working_dir, "inventory")
        with open(inv_path, 'w') as inv_file:
            yaml.dump(inv, inv_file)

        return inv_path

    def run_play(self, play_source):
        # Create a new results instance for each run
        # Instantiate our ResultCallback for handling results as they come in.
        # Ansible expects this to be one of its main display outlets
        results_callback = ResultCallback()

        # Create play object, playbook objects use .load instead of init or new
        # methods,
        # this will also automatically create the task objects from the info
        # provided in play_source
        play = Play().load(play_source, variable_manager=self.variable_manager,
                           loader=self.loader)

        # Run it - instantiate task queue manager, which takes care of forking
        # and setting up all objects to iterate over host list and tasks

        # TODO(jhesketh): the results callback could be a new instance each
        # time storing the run's specific feedback to return as a dict in this
        # method.
        tqm = None
        result = -1
        try:
            tqm = ansible.executor.task_queue_manager.TaskQueueManager(
                inventory=self.inventory,
                variable_manager=self.variable_manager,
                loader=self.loader,
                passwords=self.passwords,
                stdout_callback=results_callback,
            )
            result = tqm.run(play)
        finally:
            # we always need to cleanup child procs and the structures we use
            # to communicate with them
            if tqm is not None:
                tqm.cleanup()

            # Remove ansible tmpdir
            shutil.rmtree(C.DEFAULT_LOCAL_TMP, True)

        # TODO(jhesketh): Return the results of this run individually
        if result != 0:
            # TODO(jhesketh): Provide more useful information
            # *0* -- OK or no hosts matched
            # *1* -- Error
            # *2* -- One or more hosts failed
            # *3* -- One or more hosts were unreachable
            # *4* -- Parser error
            # *5* -- Bad or incomplete options
            # *99* -- User interrupted execution
            # *250* -- Unexpected error
            Exception("An error occurred running playbook")

        return results_callback

    def download_mitogen(self, working_dir):
        print("Downloading and unpacking mitogen")
        tar_url = "https://networkgenomics.com/try/mitogen-0.2.9.tar.gz"
        stream = urllib.request.urlopen(tar_url)
        tar_file = tarfile.open(fileobj=stream, mode="r|gz")
        tar_file.extractall(path=working_dir)
        return os.path.join(
            working_dir, 'mitogen-0.2.9/ansible_mitogen/plugins/strategy')


class Node():
    def __init__(self, libcloud_conn, name, pubkey=None, private_key=None,
                 tags=[]):
        self.name = name
        self.libcloud_conn = libcloud_conn
        self.libcloud_node = None
        self.floating_ips = []
        self.volumes = []
        self.tags = tags
        self.pubkey = pubkey
        self.private_key = private_key

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
        self.libcloud_node = self.libcloud_conn.create_node(
            name=self.name,
            size=size,
            image=image,
            **kwargs
        )

        print("Created node: ")
        print(self)
        print(self.libcloud_node)

    def create_and_attach_floating_ip(self):
        # TODO(jhesketh): Move cloud-specific configuration elsewhere
        floating_ip = self.libcloud_conn.ex_create_floating_ip(
            config.OS_EXTERNAL_NETWORK)

        print("Created floating IP: ")
        print(floating_ip)
        self.floating_ips.append(floating_ip)

        # Wait until the node is running before assigning IP
        self.wait_until_state()
        self.libcloud_conn.ex_attach_floating_ip_to_node(
            self.libcloud_node, floating_ip)

    def create_and_attach_volume(self, size=10):
        vol_name = "%s-vol-%d" % (self.name, len(self.volumes))
        volume = self.libcloud_conn.create_volume(size=size, name=vol_name)
        print("Created volume: ")
        print(volume)

        # Wait for volume to be ready before attaching
        self.wait_until_volume_state(volume.uuid)

        self.libcloud_conn.attach_volume(
            self.libcloud_node, volume, device=None)
        self.volumes.append(volume)

    def wait_until_volume_state(self, volume_uuid,
                                state=StorageVolumeState.AVAILABLE,
                                timeout=120, interval=3):
        # `state` can be StorageVolumeState, "any", or None (for not existant)
        # `state` can also be a list of NodeState's, any matching will pass
        for _ in range(int(timeout / interval)):
            volumes = self.libcloud_conn.list_volumes()
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
            nodes = self.libcloud_conn.list_nodes()
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

    def _get_ssh_ip(self):
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
                hostname=self._get_ssh_ip,
                # FIXME(jhesketh): Set username depending on OS
                username="opensuse",
                pkey=self.private_key,
                allow_agent=False,
                look_for_keys=False,
            )
        return self._ssh_client.exec_command(command)

    def ansible_inventory_vars(self):
        return {
            'ansible_host': self._get_ssh_ip(),
            # FIXME(jhesketh): Set username depending on OS
            'ansible_user': 'opensuse',
            'ansible_ssh_private_key_file': self.private_key,
            'ansible_become': True,
            'ansible_become_method': 'sudo',
            'ansible_become_user': 'root',
            'ansible_host_key_checking': False,
            'ansible_ssh_host_key_checking': False,
            'ansible_scp_extra_args': '-o StrictHostKeyChecking=no',
            'ansible_ssh_extra_args': '-o StrictHostKeyChecking=no',
            'ansible_python_interpreter': '/usr/bin/python3',
        }


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

        # NOTE(jhesketh): The working_dir is never cleaned up. This is somewhat
        # deliberate to keep the private key if it is needed for debugging.
        self.working_dir = tempfile.mkdtemp(
            prefix="%s%s_" % (config.CLUSTER_PREFIX, self.hardware_uuid))

        self.sshkey_name = None
        self.pubkey = None
        self.private_key = None
        self._ex_os_key = self.generate_keys()
        self._ex_security_group = self.create_security_group()

        self.ansible_runner = None
        self._ansible_runner_nodes = None

        print(self.pubkey)
        print(self.private_key)

    def get_driver_connection(self):
        """ Get a libcloud connection object for the configured driver """
        connection = None
        if config.CLOUD_PROVIDER == 'OPENSTACK':
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
        else:
            raise Exception("Cloud provider '{}' not yet supported by "
                            "smoke_rook".format(config.CLOUD_PROVIDER))
        return connection

    def deployment_steps(self):
        """ The base deployment steps to perform on each node """
        yield ScriptDeployment('echo "hi" && touch ~/i_was_here')

    def get_image_by_name(self, name):
        if name in self._image_cache:
            return self._image_cache[name]
        self._image_cache[name] = self.libcloud_conn.get_image(name)
        return self._image_cache[name]

    def get_size_by_name(self, name=None):
        if self._size_cache:
            sizes = self._size_cache
        else:
            sizes = self.libcloud_conn.list_sizes()
            self._size_cache = sizes

        if name:
            for node_size in sizes:
                if node_size.name == name:
                    return node_size

        return None

    def get_ex_network_by_name(self, name=None):
        # TODO(jhesketh): Create a network instead
        if self._ex_network_cache:
            networks = self._ex_network_cache
        else:
            networks = self.libcloud_conn.ex_list_networks()
            self._ex_network_cache = networks

        if name:
            for network in networks:
                if network.name == name:
                    return network

        return None

    def generate_keys(self):
        """
        Generatees a public and private key
        """
        key = paramiko.rsakey.RSAKey.generate(2048)
        self.private_key = os.path.join(self.working_dir, 'private.key')
        with open(self.private_key, 'w') as key_file:
            key.write_private_key(key_file)
        os.chmod(self.private_key, 0o400)

        self.sshkey_name = \
            "%s%s_key" % (config.CLUSTER_PREFIX, self.hardware_uuid)
        self.pubkey = "%s %s" % (key.get_name(), key.get_base64())

        os_key = self.libcloud_conn.import_key_pair_from_string(
            self.sshkey_name, self.pubkey)

        return os_key

    def create_security_group(self):
        """
        Creates a security group used for this set of hardware. For now,
        all ports are open.
        """
        if config.CLOUD_PROVIDER == 'OPENSTACK':
            security_group = self.libcloud_conn.ex_create_security_group(
                name=("%s%s_security_group"
                      % (config.CLUSTER_PREFIX, self.hardware_uuid)),
                description="Permissive firewall for rookci testing"
            )
            for protocol in ["TCP", "UDP"]:
                self.libcloud_conn.ex_create_security_group_rule(
                    security_group,
                    ip_protocol=protocol,
                    from_port=1,
                    to_port=65535,
                )
        else:
            raise Exception("Cloud provider not yet supported by smoke_rook")
        return security_group

    def execute_ansible_play(self, play_source):
        if not self.ansible_runner or self._ansible_runner_nodes != self.nodes:
            # Create a new AnsibleRunner if the nodes dict has changed (to
            # generate a new inventory).
            self.ansible_runner = AnsibleRunner(self.nodes, self.working_dir)
            self._ansible_runner_nodes = self.nodes.copy()

        return self.ansible_runner.run_play(play_source)

    def create_node(self, node_name, tags=[]):
        node = Node(
            libcloud_conn=self.libcloud_conn,
            name=node_name, pubkey=self.pubkey, private_key=self.private_key,
            tags=tags)
        # TODO(jhesketh): Create fixed network as part of build and security
        #                 group
        additional_networks = []
        if config.OS_INTERNAL_NETWORK:
            additional_networks.append(
                self.get_ex_network_by_name(config.OS_INTERNAL_NETWORK)
            )
        node.boot(
            size=self.get_size_by_name(config.NODE_SIZE),
            # TODO(jhesketh): FIXME
            image=self.get_image_by_name(
                "e9de104d-f03a-4d9f-8681-e5dd4e9cede7"),
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
        self.get_ex_network_by_name()
        self.get_size_by_name()
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
                target=self.create_node, args=(node_name, tags))
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
        print("destroy nodes")
        print(self)

        threads = []
        for node in self.nodes.values():
            thread = threading.Thread(target=node.destroy,)
            threads.append(thread)
            thread.start()
            # FIXME(jhesketh): See above re thread-safety.
            thread.join()

        # for thread in threads:
        #     thread.join()

        self.libcloud_conn.ex_delete_security_group(self._ex_security_group)
        self.libcloud_conn.delete_key_pair(self._ex_os_key)

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
            self.remove_ssh_key(node._get_ssh_ip())

    def remove_ssh_key(self, ip):
        subprocess.run(
            "ssh-keygen -R %s" % ip,
            shell=True
        )

    def prepare_nodes(self):
        """
        Install any dependencies, set firewall etc.
        """
        if config.DISTRO == 'SUSE':
            d = SUSE()
        else:
            raise Exception("OS yet to be implemented/unsupport.")

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
