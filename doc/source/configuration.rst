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

Amazon Web Services (AWS) EC2 specifics
---------------------------------------

The AWS driver is implemented using the `boto3 library <https://boto3.amazonaws.com/v1/documentation/api/latest/index.html>`_.

Tox will install the library for you, but you'll need to configure the
credentials in `~/.aws/credentials`. The easiest way to do that is by running
`aws configure` if you already have the `AWS CLI <http://aws.amazon.com/cli/>`_
installed.

See the `boto3 configuration <https://boto3.amazonaws.com/v1/documentation/api/latest/guide/quickstart.html#configuration>`_
documentation for full details.

The driver will set up a VPC and create all of the necessary resources inside
of that.

Please note that the image id for the nodes differs depending on the AWS
region that you are using. You may also need to accept any licenses for the
images that you are using (as the same user as the configured credentials).
For example, you can subscribe to the `openSUSE Leap image here <https://aws.amazon.com/marketplace/pp/B01N4R3GJI>`_.
After you have subscribed to the image, you can follow the links to
"continue to configuration", then after selecting your expected region, you
should be able to see the AMI ID.

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

   export ROOKCHECK_HARDWARE_PROVIDER='LIBVIRT'

.. automodule:: tests.config
   :members:
   :private-members:
   :special-members:
   :undoc-members:

