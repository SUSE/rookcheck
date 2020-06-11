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

If you are using OpenStack you can use your openrc for most of the
configuration. To do this, you just need to source the file into your bash
session:

.. code-block:: bash

    source ~/openrc


Alternatively you can set the OpenStack credentials in your .env file, but you
will have to use the `ROOKCHECK_` prefix.

TODO(jhesketh): Autodoc the config options once configuration is reworked into
something more useful.

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

