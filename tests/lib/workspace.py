# Copyright (c) 2020 SUSE LLC
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

import contextlib
import logging
import os
import shutil
import stat
import subprocess
from typing import Any, Dict, Optional, Tuple
import uuid

import paramiko.rsakey

from tests.config import settings
from tests.lib.common import execute, handle_cleanup_input


logger = logging.getLogger(__name__)


class Workspace():
    def __init__(self):
        # Set up a common workspace that most modules will expect
        self._workspace_uuid: str = str(uuid.uuid4())[:4]
        self._working_dir: str = self._get_working_dir()

        self._sshkey_name: Optional[str] = None
        self._public_key: Optional[str] = None
        self._private_key: Optional[str] = None

        self._generate_keys()

        self._ssh_agent_auth_sock: str = os.path.join(
            self.working_dir, 'ssh-agent.sock')
        self._ssh_agent()

        logger.info(f"Workspace {self.name} set up at {self.working_dir}")
        logger.info(f"public key {self.public_key}")
        logger.info(f"private key {self.private_key}")

    # TODO fix self rep

    @property
    def name(self) -> str:
        return "%s%s" % (settings.CLUSTER_PREFIX, self._workspace_uuid)

    @property
    def working_dir(self) -> str:
        return self._working_dir

    @property
    def sshkey_name(self):
        return self._sshkey_name

    @property
    def public_key(self):
        return self._public_key

    @property
    def private_key(self):
        return self._private_key

    def _generate_keys(self):
        """
        Generatees a public and private key
        """
        key = paramiko.rsakey.RSAKey.generate(2048)
        self._private_key = os.path.join(
            self.working_dir, 'private.key')
        with open(self._private_key, 'w') as key_file:
            key.write_private_key(key_file)
        os.chmod(self._private_key, 0o400)

        self._sshkey_name = "%s_key" % (self.name)
        self._public_key = "%s %s" % (key.get_name(), key.get_base64())

    @property
    def ssh_agent_auth_sock(self) -> str:
        return self._ssh_agent_auth_sock

    @property
    def ssh_agent_pid(self) -> str:
        return self._ssh_agent_pid

    def _ssh_agent(self):
        try:
            # NOTE(jhesketh): We can't use self.execute yet because
            #                 self.ssh_agent_pid is not ready yet.
            rc, stdout, stderr = execute(
                f'ssh-agent -a {self.ssh_agent_auth_sock}',
                capture=True
            )
        except subprocess.CalledProcessError:
            logger.exception('Failed to start ssh agent')
            raise

        self._ssh_agent_pid = stdout.split(';')[2].split('=')[1]
        try:
            logging.info("Adding ssh-key to agent")
            # NOTE(jhesketh): For some reason, ssh-add outputs to stderr which
            #                 will be logged as a warning. It's not really
            #                 dangerous because we're creating and destroying
            #                 our own agent, so we'll suppress the messages.
            self.execute(f'ssh-add {self.private_key}', log_stderr=False)
        except subprocess.CalledProcessError:
            logger.exception('Failed to add keys to agent')
            raise

    def execute(self, command: str, capture: bool = False, check: bool = True,
                log_stdout: bool = True, log_stderr: bool = True,
                env: Optional[Dict[str, str]] = None,
                logger_name: Optional[str] = None,
                chdir: Optional[str] = None) -> Tuple[
                    int, Optional[str], Optional[str]]:
        """Executes a command inside the workspace

        This is a wrapper around the execute util that will automatically
        chdir into the workspace and set some common env vars (such as the
        ssh agent).
        """
        if not env:
            env = {
                'PATH': os.environ.get(
                    'PATH', '/usr/local/bin:/usr/bin:/bin')
            }
        env['PATH'] = f"{os.path.join(self.working_dir, 'bin')}:{env['PATH']}"
        with self.chdir(chdir):
            env['SSH_AUTH_SOCK'] = self.ssh_agent_auth_sock
            env['SSH_AGENT_PID'] = self.ssh_agent_pid
            return execute(command, capture=capture, check=check,
                           log_stdout=log_stdout, log_stderr=log_stderr,
                           env=env, logger_name=logger_name)

    def ansible_inventory_vars(self) -> Dict[str, Any]:
        """
        Some basic ansible inventory variables that are common for this
        workspace
        """
        vars = {
            'ansible_ssh_private_key_file': self.private_key,
            'ansible_host_key_checking': False,
            'ansible_ssh_host_key_checking': False,
            'ansible_scp_extra_args': '-o StrictHostKeyChecking=no',
            'ansible_ssh_extra_args': '-o StrictHostKeyChecking=no',
            'ansible_python_interpreter': '/usr/bin/python3',
            'rookcheck_workspace_dir': self.working_dir,
        }
        return vars

    @contextlib.contextmanager
    def chdir(self, path=None):
        """A context manager which changes the working directory to the given
        path, and then changes it back to its previous value on exit.

        """
        if not path:
            path = self.working_dir
        prev_cwd = os.getcwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(prev_cwd)

    def _get_working_dir(self):
        working_dir_path = os.path.join(
            settings.WORKSPACE_DIR, self.name
        )
        os.makedirs(working_dir_path)
        os.makedirs(os.path.join(working_dir_path, 'bin'))
        return working_dir_path

    def destroy(self, skip=False):
        if settings.as_bool('_TEAR_DOWN_CLUSTER_CONFIRM'):
            handle_cleanup_input("pause before cleanup workspace")

        # This kills the SSH_AGENT_PID agent
        try:
            self.execute('ssh-agent -k', check=True)
        except subprocess.CalledProcessError:
            logger.warning(f'Killing ssh-agent with PID'
                           f' {self._ssh_agent_pid} failed')

        if skip:
            logger.warning("The workspace directory will not be removed!")
            logger.warning(f"Workspace left behind at {self.working_dir}")
            return

        if settings.as_bool('_REMOVE_WORKSPACE'):
            logger.info(f"Removing workspace {self.working_dir} from disk")
            # NOTE(jhesketh): go clones repos as read-only. We need to chmod
            #                 all the files back to writable (in particular,
            #                 the directories) so that we can remove them
            #                 without failures or warnings.
            for root, dirs, files in os.walk(self.working_dir):
                for folder in dirs:
                    path = os.path.join(root, folder)
                    try:
                        os.chmod(path, os.stat(path).st_mode | stat.S_IWUSR)
                    except (FileNotFoundError, PermissionError):
                        # Some path's might be broken symlinks.
                        # Some files may be owned by somebody else (eg qemu)
                        # but are still safe to remove so ignore the
                        # permissions issue.
                        pass
                for f in files:
                    path = os.path.join(root, f)
                    try:
                        os.chmod(path, os.stat(path).st_mode | stat.S_IWUSR)
                    except (FileNotFoundError, PermissionError):
                        # Some path's might be broken symlinks.
                        # Some files may be owned by somebody else (eg qemu)
                        # but are still safe to remove so ignore the
                        # permissions issue.
                        pass
            shutil.rmtree(self.working_dir)
        else:
            logger.info(f"Keeping workspace on disk at {self.working_dir}")

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy(skip=not settings.as_bool('_TEAR_DOWN_CLUSTER'))
