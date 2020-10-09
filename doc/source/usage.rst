Usage
=====

Make sure to have followed the :ref:`configuration` steps first, and to source
or ensure the correct environment variables are set.

.. _running_tests:

Running tests
-------------

`rookcheck` uses `tox <https://tox.readthedocs.io/>`_ to make managing the test
environment easier. If you just ran `tox`, it would execute all of the
available environments. You can see how these are configured in `tox.ini`.
Unless you are developing tests, then running the linting or other checks that
`tox` helps provide may not be necessary. Thus we can limit `tox` with the `-e`
env flag.

Running all tests:

.. code-block:: bash

    tox -e py37

Running an individual test or set of tests:

.. code-block:: bash

    tox -e py37 -- tests/test_basic.py
    # Or specific test
    tox -e py37 -- tests/test_basic.py::test_file_creation

Debugging
---------

You can leave the built environment available by `setting _tear_down_cluster`
to False.

.. code-block:: bash

    export ROOKCHECK__TEAR_DOWN_CLUSTER="FALSE"

In that case, you need to cleanup the resources (used hardware, eg. OpenStack
or EC2 nodes) manually.

Another option is to keep `setting _tear_down_cluster` to True and set instead
`setting tear_down_cluster_confirm` to True. In that case, the tear down steps
for the different layers (workspace, hardware, kubernetes, rook) must be
manually confirmed.

.. code-block:: bash

   export ROOKCHECK__TEAR_DOWN_CLUSTER="TRUE" # This is anyway the default
   export ROOKCHECK__TEAR_DOWN_CLUSTER_CONFIRM="TRUE"

You can then access the kubeconfig and ansible inventory files among other
resources in the workspace (defined by `workspace_dir`). This is usually
something like `/tmp/rookcheck*`.

If Kubernetes was set up, you can access the binaries used from there too.
For example:

.. code-block:: bash

    cd /tmp/rookcheck/rookcheck-josh-75f5 # (substitute with your build name)
    ./bin/kubectl --kubeconfig kubeconfig get all --all-namespaces

    # Or if you're building SES, use
    ./bin/kubectl --kubeconfig cluster/admin.conf get all --all-namespaces


Dropping to `PDB (Python Debugger) <http://docs.python.org/library/pdb.html>`_
on failure:

.. code-block:: bash

    tox -e py37 -- --pdb

Dropping to `PDB` at the start of a test:

.. code-block:: bash

    tox -e py37 -- --trace

If you want to use the prepared environment from `tox`, you can activate the
created virtual env:

.. code-block:: bash

    source .tox/py37/bin/activate

This will now let you run `pytest` directly and have all the dependencies
correctly set up. Similarly you can run `python` and start importing
`rookcheck`'s library. See :ref:`development_notes` for more.

Notes/Common Problems
---------------------

 * rookcheck will remove and manage known host keys on the test runner, which
   may include removing legitimate entries.
