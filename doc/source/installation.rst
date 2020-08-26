Installation
============

Quickstart
----------

Install requirements:

.. code-block:: bash

    # For OpenSUSE:
    sudo zypper in python3-pip python3-tox
    sudo zypper in $(tox -qq -e bindep -- -b)
    sudo systemctl start docker
    sudo usermod -aG docker $USER

.. code-block:: bash

    # For Ubuntu:
    sudo apt install python3-pip tox
    sudo apt install $(tox -qq -e bindep -- -b)
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

    # For OpenSUSE:
    sudo zypper in python3-pip python3-tox

    # For Ubuntu:
    sudo apt install python3-pip tox

    # If your distro does not have tox >= 3.15.2, then you can alternatively
    # install or upgrade it from pypi:
    sudo zypper in python3-pip # / or sudo apt install python3-pip
    sudo pip install -U tox

Next we run bindep from inside a tox environment to get the list of missing
system packages.
By specifying the ROOKCHECK_HARDWARE_PROVIDER and ROOKCHECK_DISTRO we are
going to use we can ensure the requirements for our infrastructure are met
(see :ref:`configuration` for more information):

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

    sudo zypper in $(tox -qq -e bindep -- -b ${ROOKCHECK_HARDWARE_PROVIDER,,} ${ROOKCHECK_DISTRO,,})

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
