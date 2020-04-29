rookcheck
=========

`rookcheck` is a testing platform for rook.io. The intention is to provide
developers with a way to simulate various environments and scenarios that may
occur within them.

For example, rookcheck can perform tests such as adding new nodes to your
kubernetes cluster and ensuring that they are correctly enrolled and handled by
rook.io/ceph.

Additionally rookcheck can handle disaster testing such as kernel panics,
physically removed nodes, and so forth.

Because a test may need to interact with the underlying hardware the unit tests
will set up and configure the nodes, distros, kubernetes, and rook itself.
These are then exposed to the test writer to interact with further or to verify
the environment.

rookcheck requires VM's from `libcloud` to set up and perform the tests
against.

`Read the full documentation <https://rookcheck.readthedocs.io/>`_.

Quickstart
----------

Install requirements:

.. code-block:: bash

    sudo zypper in python-pip
    sudo pip install tox
    sudo zypper in $(tox -qq -e bindep -- -b)
    sudo systemctl start docker
    sudo usermod -aG docker $USER

Run tests:

.. code-block:: bash

    tox -e py38


.. image:: https://readthedocs.org/projects/rookcheck/badge/?version=latest
   :target: https://rookcheck.readthedocs.io/en/latest/?badge=latest
   :alt: Documentation Status
