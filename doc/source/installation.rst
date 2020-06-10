Installation
============

Quickstart
----------

Install requirements:

.. code-block:: bash

    sudo zypper in python-pip
    sudo pip install -U tox
    sudo zypper in $(tox -qq -e bindep -- -b)
    sudo systemctl start docker
    sudo usermod -aG docker $USER

Requiremnets
------------

Requirements are tracked with
`bindep <https://docs.openstack.org/infra/bindep/readme.html>`_ and
`pip <https://pip.pypa.io/en/stable/reference/pip_install>`_'s requiements.txt.

First we need python-tox to be able to manage our virtual environments. Version
3.15.2 or greater is recommended as it fixes an issue with cleaning up
resources when being manually terminated. This is best installed from pip, but
could alternatively be installed from your system packages.

.. code-block:: bash

    sudo zypper in python-pip
    sudo pip install -U tox

Next we run bindep from inside a tox environment to get the list of missing
system packages. By specifying the HARDWARE_PROVIDER and DISTRO we are going
to use we can ensure the requirements for our infrastructure are met (see
:ref:`configuration` for more information):

.. code-block:: bash

    ROOKCHECK_HARDWARE_PROVIDER=libvirt
    ROOKCHECK_DISTRO=openSUSE_k8s
    # Alternatively, source these from .env if you have already set up your
    # configuration.
    tox -e bindep ${ROOKCHECK_HARDWARE_PROVIDER} ${ROOKCHECK_DISTRO}

Then we can take the list and install them.

.. code-block:: bash

    sudo zypper in <output from bindep command>

Or as one command the above can be:

.. code-block:: bash

    sudo zypper in $(tox -qq -e bindep -- -b ${HARDWARE_PROVIDER} ${DISTRO})

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
