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
import shutil
import tempfile
import threading
import time
import uuid
import yaml

from ansible.module_utils.common.collections import ImmutableDict
from ansible.parsing.dataloader import DataLoader
from ansible.vars.manager import VariableManager
from ansible.inventory.manager import InventoryManager
from ansible.playbook.play import Play
from ansible.executor.task_queue_manager import TaskQueueManager
from ansible.plugins.callback import CallbackBase
from ansible import context as ansible_context
import ansible.constants as C
import libcloud.security
from libcloud.compute.deployment import ScriptDeployment
from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver
from paramiko.client import AutoAddPolicy, SSHClient
import paramiko.rsakey

from tests import config

libcloud.security.VERIFY_SSL_CERT = config.VERIFY_SSL_CERT


class Distro(ABC):
    @abstractmethod
    def bootstrap_play(self):
        pass


class SUSE(Distro):
    def bootstrap_play(self):
        tasks = []
        print("Installing dependencies")
        tasks.append(
            dict(
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

        print("Updating kernel")
        tasks.append(
            dict(
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

        print("Removing anti-dependencies ")
        tasks.append(
            dict(
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

        print("Enabling docker")
        tasks.append(
            dict(
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
        print("Raising max open files")
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        cmd="sysctl -w fs.file-max=1200000",
                    )
                )
            )
        )

        print("Minimize swappiness")
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        cmd="sysctl -w vm.swappiness=0",
                    )
                )
            )
        )

        print("Reboot nodes")
        tasks.append(
            dict(
                action=dict(
                    module='reboot',
                )
            )
        )

        print("Setting iptables on nodes to be permissive")
        tasks.append(
            dict(
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
                tasks=tasks
            )
        return play_source


class ResultCallback(CallbackBase):
    """This callback stores the latest results for a run in an instance
    variable (host_ok, host_unreachable, host_failed).
    It is intended to be instanciated for each individual run.
    """
    def __init__(self, *args, **kwargs):
        super(ResultCallback, self).__init__(*args, **kwargs)
        self.host_ok = {}
        self.host_unreachable = {}
        self.host_failed = {}

    def v2_runner_on_unreachable(self, result):
        if result._host.get_name() not in self.host_unreachable:
            self.host_unreachable[result._host.get_name()] = []
        self.host_unreachable[result._host.get_name()].append(result)

    def v2_runner_on_ok(self, result, *args, **kwargs):
        if result._host.get_name() not in self.host_ok:
            self.host_ok[result._host.get_name()] = []
        self.host_ok[result._host.get_name()].append(result)

    def v2_runner_on_failed(self, result, *args, **kwargs):
        if result._host.get_name() not in self.host_failed:
            self.host_failed[result._host.get_name()] = []
        self.host_failed[result._host.get_name()].append(result)


class AnsibleRunner(object):
    def __init__(self, nodes):
        # since the API is constructed for CLI it expects certain options to
        # always be set in the context object
        ansible_context.CLIARGS = ImmutableDict(
            connection='paramiko_ssh', module_path=[''], forks=10,
            gather_facts='no',
        )

        # Takes care of finding and reading yaml, json and ini files
        self.loader = DataLoader()
        self.passwords = dict(vault_pass='secret')

        # create inventory, use path to host config file as source or hosts in
        # a comma separated string
        self.inventory_file = self.create_inventory(nodes)
        self.inventory = InventoryManager(
            loader=self.loader, sources=self.inventory_file)

        # variable manager takes care of merging all the different sources to
        # give you a unified view of variables available in each context
        self.variable_manager = VariableManager(
            loader=self.loader, inventory=self.inventory)

    def create_inventory(self, nodes):
        fd = tempfile.NamedTemporaryFile(
            mode='a',
            prefix="%s" % config.CLUSTER_PREFIX,
            suffix=".yaml",
            delete=False
        )
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

        yaml.dump(inv, fd)

        # NOTE(jhesketh): The inventory file is never cleaned up. This is
        # somewhat deliberate to keep the private key if it is needed for
        # debugging.
        fd.close()

        return fd.name

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
            tqm = TaskQueueManager(
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


class Node():
    def __init__(self, name, pubkey=None, private_key=None, tags=[]):
        self.name = name
        self.libcloud_node = None
        self.floating_ips = []
        self.tags = tags
        self.pubkey = pubkey
        self.private_key = private_key

        self._ssh_client = None

    def boot(self, libcloud_conn, size, image, sshkey_name=None,
             external_networks=[]):
        if self.libcloud_node:
            raise Exception("A node has already been booted")

        # TODO(jhesketh): Move cloud-specific configuration elsewhere
        kwargs = {}
        if external_networks:
            kwargs['networks'] = external_networks
        if sshkey_name:
            kwargs['ex_keyname'] = sshkey_name

        # Can't use deploy_node because there is no public ip yet
        self.libcloud_node = libcloud_conn.create_node(
            name=self.name,
            size=size,
            image=image,
            **kwargs
        )

        print("Created node: ")
        print(self)
        print(self.libcloud_node)

    def create_and_attach_floating_ip(self, libcloud_conn):
        # TODO(jhesketh): Move cloud-specific configuration elsewhere
        floating_ip = libcloud_conn.ex_create_floating_ip('floating')

        print("Created floating IP: ")
        print(floating_ip)
        self.floating_ips.append(floating_ip)

        # TODO(jhesketh): Find a better way to wait for the node before
        #                 assigning floating ip's
        time.sleep(10)
        libcloud_conn.ex_attach_floating_ip_to_node(
            self.libcloud_node, floating_ip)

    def destroy(self):
        if self._ssh_client:
            self._ssh_client.close()
        for floating_ip in self.floating_ips:
            floating_ip.delete()
        if self.libcloud_node:
            self.libcloud_node.destroy()
            self.libcloud_node = None

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
                username="opensuse", #FIXME
                pkey=self.private_key,
                allow_agent=False,
                look_for_keys=False,
            )
        return self._ssh_client.exec_command(command)

    def ansible_inventory_vars(self):
        return {
            'ansible_host': self._get_ssh_ip(),
            'ansible_user': 'opensuse', #FIXME
            'ansible_ssh_private_key_file': self.private_key,
            'ansible_become': True,
            'ansible_become_method': 'sudo',
            'ansible_become_user': 'root',
            'ansible_host_key_checking': False,
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

        self.sshkey_name = None
        self.pubkey = None
        self.private_key = None
        self._ex_os_key = None
        self.generate_keys()

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
        key_file = tempfile.NamedTemporaryFile(
            mode='a',
            prefix="%s%s" % (config.CLUSTER_PREFIX, self.hardware_uuid),
            suffix=".key",
            delete=False
        )
        key.write_private_key(key_file)
        key_file.close()
        # NOTE(jhesketh): The key_file is never cleaned up. This is somewhat
        # deliberate to keep the private key if it is needed for debugging.

        self.sshkey_name = \
            "%s%s_key" % (config.CLUSTER_PREFIX, self.hardware_uuid)
        self.pubkey = "%s %s" % (key.get_name(), key.get_base64())
        self.private_key = key_file.name

        self._ex_os_key = self.libcloud_conn.import_key_pair_from_string(
            self.sshkey_name, self.pubkey)

    def execute_ansible_play(self, play_source):
        if not self.ansible_runner or self._ansible_runner_nodes != self.nodes:
            # Create a new AnsibleRunner if the nodes dict has changed (to
            # generate a new inventory).
            self.ansible_runner = AnsibleRunner(self.nodes)
            self._ansible_runner_nodes = self.nodes.copy()

        return self.ansible_runner.run_play(play_source)

    def create_node(self, node_name):
        node = Node(
            name=node_name, pubkey=self.pubkey, private_key=self.private_key)
        node.boot(
            libcloud_conn=self.libcloud_conn,
            size=self.get_size_by_name(config.NODE_SIZE),
            # TODO(jhesketh): FIXME
            image=self.get_image_by_name(
                "e9de104d-f03a-4d9f-8681-e5dd4e9cede7"),
            sshkey_name=self.sshkey_name,
            external_networks=[self.get_ex_network_by_name('user')],
        )
        node.create_and_attach_floating_ip(self.libcloud_conn)
        self.nodes[node_name] = node

    def boot_nodes(self, controllers=1, workers=2, offset=0):
        """
        Boot n nodes
        Start them at a number offset
        """
        # Warm the caches
        self.get_ex_network_by_name()
        self.get_size_by_name()
        self._boot_nodes(['controller'], controllers, offset=offset,
                         suffix='controller_')
        self._boot_nodes(['worker'], workers, offset=offset, suffix='worker_')

    def _boot_nodes(self, tags, n, offset=0, suffix=""):
        threads = []
        for i in range(n):
            node_name = "%s%s_%s%d" % (
                config.CLUSTER_PREFIX, self.hardware_uuid, suffix, i+offset)
            thread = threading.Thread(
                target=self.create_node, args=(node_name,))
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

        # FIXME(jhesketh): Remove timeout. Just here to make sure all the
        #                  resources are up before attempting to delete.
        time.sleep(20)

        threads = []
        for node in self.nodes.values():
            thread = threading.Thread(target=node.destroy,)
            threads.append(thread)
            thread.start()
            # FIXME(jhesketh): See above re thread-safety.
            thread.join()

        # for thread in threads:
        #     thread.join()

        self.libcloud_conn.delete_key_pair(self._ex_os_key)

    def prepare_nodes(self):
        """
        Install any dependencies, set firewall etc.
        """
        if config.DISTRO == 'SUSE':
            d = SUSE()
        else:
            raise Exception("OS yet to be implemented/unsupport.")

        r = self.execute_ansible_play(d.bootstrap_play())

        if r.host_failed or r.host_unreachable:
            # TODO(jhesketh): Provide some more useful feedback and/or checking
            raise Exception("One or more hosts failed")

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy()
