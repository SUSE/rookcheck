Installation
============

Quickstart
----------

Install requirements:

.. code-block:: bash

    sudo zypper in python-pip
    sudo pip install tox
    sudo zypper in $(tox -qq -e bindep -- -b)
    sudo systemctl start docker
    sudo usermod -aG docker $USER

Requiremnets
------------

Requirements are tracked with
`bindep <https://docs.openstack.org/infra/bindep/readme.html>`_ and
`pip <https://pip.pypa.io/en/stable/reference/pip_install>`_'s requiements.txt.

First we need python-tox to be able to manage our virtual environments. This is
best installed from pip, but can be installed from your system packages as
well.

.. code-block:: bash

    sudo zypper in python-pip
    sudo pip install tox

Next we run bindep from inside a tox environment to get the list of missing
system packages:

.. code-block:: bash

    PROFILE=libvirt
    tox -e bindep ${PROFILE}

Then we can take the list and install them.

.. code-block:: bash

    sudo zypper in <output from bindep command>

Or as one command the above can be:

.. code-block:: bash

    sudo zypper in $(tox -qq -e bindep -- -b)

One of the system requirements to build rook is docker. Make sure the docker
daemon is running:

.. code-block:: bash

    sudo systemctl start docker

You may also need to make sure your user is in the docker group:

.. code-block:: bash

    sudo usermod -aG docker $USER

Verify that you can run docker::

    docker run hello-world

If that fails then see your systems instructions for setting up docker.

