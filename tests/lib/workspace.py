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
import os
import shutil
import uuid

from tests import config


class Workspace():
    def __init__(self):
        # Set up a common workspace that most modules will expect

        self._workspace_uuid: str = str(uuid.uuid4())[:8]
        self._working_dir: str = self._get_working_dir()

    # TODO fix self rep

    @property
    def name(self) -> str:
        return "%s%s" % (config.CLUSTER_PREFIX, self._workspace_uuid)

    @property
    def working_dir(self) -> str:
        return self._working_dir

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
            config.WORKSPACE_DIR, self.name
        )
        os.makedirs(working_dir_path)
        return working_dir_path

    def destroy(self):
        if config._REMOVE_WORKSPACE:
            logger.info(f"Removing workspace {self.name} from disk")
            shutil.rmtree(self.working_dir)
        else:
            logger.info(f"Keeping workspace on disk at {self.working_dir}")

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy()
