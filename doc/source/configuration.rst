Configuration
=============

You will need to configure the platform that the tests are ran against::

    cp configuration.env my.env
    vim my.env # Make any changes needed
    source my.env

If you are using OpenStack you can use your openrc for most of the
configuration. You may wish to include this in my.env or source your openrc
separately.

OpenStack provider specifics
----------------------------

A OpenStack network needs to be available for usage. The network name needs to
be exported as::

  export OS_INTERNAL_NETWORK=my-test-net

If the network is not available, one can be created via::

  _OS_SUBNET=`echo $OS_INTERNAL_NETWORK|sed -e 's/-net/-subnet/'`
  _OS_ROUTER=`echo $OS_INTERNAL_NETWORK|sed -e 's/-net/-router/'`
  openstack network create ${OS_INTERNAL_NETWORK}
  openstack subnet create --network ${OS_INTERNAL_NETWORK} --subnet-range 192.168.100.0/24 ${_OS_SUBNET}
  openstack router create ${_OS_ROUTER}
  openstack router set --external-gateway floating ${_OS_ROUTER}

where `floating` is the name of the external network.
