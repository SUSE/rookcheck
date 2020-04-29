rookcheck's documentation
=========================

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

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   installation
   configuration
   usage
   structure
   writing_tests
   theory


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
