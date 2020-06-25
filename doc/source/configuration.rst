.. _configuration:

Configuration
=============

Configuration is managed with `dynaconf <https://dynaconf.readthedocs.io/>`_.
The defaults and annotations for the available settings can be observed in
`config/settings.toml`.

The easiest way to configure rookcheck is to provide overrides via environment
variables.

The environment variables are capitalised and prefixed with `ROOKCHECK_`. For
example, to change where rookcheck creates files (known as `workspace_dir` in
settings.toml), you can set `ROOKCHECK_WOKRSPACE_DIR=...`.

Start by copying the example configuration.env:

.. code-block:: bash

    cp configuration.env .env
    vim .env # Make any changes needed

OpenStack provider specifics
----------------------------

If you are using OpenStack you can use your
`clouds.yaml <https://docs.openstack.org/openstacksdk/latest/user/guides/connect_from_config.html>`_
configuration file and reference a cloud defined in that file with OS_CLOUD

.. code-block:: bash

    export OS_CLOUD=my-cloud

libvirt provider specifics
--------------------------

For using `libvirt` as a hardware backend, a qcow2 image which includes
`cloud-init` is needed.

Then some environment variables are needed:

.. code-block:: bash

   export HARDWARE_PROVIDER='LIBVIRT'

.. automodule:: tests.config
   :members:
   :private-members:
   :special-members:
   :undoc-members:

