.. _development_notes:

Development Notes
=================

NOTE: These are likely out of date.

It can be helpful to build the infrastructure in a Python shell for developing
and debugging. Here are the common steps that I take.

Install the requirements into a virtualenv or use tox:

.. code-block:: bash

    `tox -e venv python`

.. code-block:: python

    import tests.lib.hardware
    h = tests.lib.hardware.Hardware()

This creates an sshkey in ECP and sets up the environment with a working dir.
The working dir will be something like /tmp/josh-rookci-00b3bfd9_m0net09/
and contain the private key.

.. code-block:: python

    h.boot_nodes()

This will boot 1 master and 2 workers. You can ssh to them with something like
`ssh -i /tmp/josh-rookci-00b3bfd9_m0net09/private.key opensuse@10.86.0.0`
The IP's will be output in the shell or you can look them up in ECP/horizon.

.. code-block:: python

    h.prepare_nodes()

This will do the first ansible run to bootstrap the nodes. You might need to
wait 30seconds or so after boot_nodes to ensure they are all ready.

Now we can install kubernetes:

.. code-block:: python

    import tests.lib.kubernetes
    k = tests.lib.kubernetes.VanillaKubernetes(h)
    k.bootstrap()
    k.install_kubernetes()

You can then interact with the kubernetes cluster with (for example):
cd /tmp/josh-rookci-00b3bfd9_m0net09/
./kubectl --kubeconfig ./kubeconfig get nodes

Then we can build rook:

.. code-block:: python

    import tests.lib.rook
    r = tests.lib.rook.RookCluster(k)
    r.build_rook()

And lastly install rook:

.. code-block:: python

    r.install_rook()


Now the environment is set up and you can play around.


Using the playground test
-------------------------

As an alternative to doing the above steps manually, there is a "playground"
test that will bring up all of the fixtures for you and drop you into a
python interpreter.


.. code-block:: bash

    tox -e py38 -- tests/test_playground.py


Once the infrastructure is set up you can interact with the provided fixtures
`workspace`, `hardware`, `kubernetes`, `rook_cluster`.

When you are finished, exit the interpreter with `quit()` and rookcheck will
clean up the resources.



Finding orphaned resources
--------------------------

Sometimes a failed test run doesn't clean up resources correctly. This usually
occurs when there is a failure on the cloud provider or on the network
preventing rookcheck from doing its usual clean up.

Because rookcheck doesn't currently keep any state from a test run, there is
a helper tool for finding orphaned resources and removing them. currently
this is only available for the OpenStack provider. It can be ran like
so:


.. code-block:: bash

    tox -e venv -- python ./tools/clean_openstack_resources.py -s "rookcheck*"


The script will prompt you before deleting anything. It is also recommended
that you set the search pattern to your environment prefix.


Current issues
--------------

At the moment rook isn't being installed properly. Seeing the error:

.. code-block:: bash

    MountVolume.SetUp failed for volume "rook-ceph-crash-collector-keyring" :
    secret "rook-ceph-crash-collector-keyring" not found

This is likely due to networking between the nodes.
Flannel needs to have the public-ip's set for each of the nodes, otherwise it
does not use the correct network. This can be done with

.. code-block:: bash

    `kubectl annotate node josh-rookci-00b3bfd9_m0net09-master-0 flannel.alpha.coreos.com/public-ip-overwrite=10.86.0.0 --overwrite`

(Setting the correct node name and IP of course)

This should be done before Flannel is installed, so in my debugging I have done
some of the kubeadm installation steps by hand
(from tests.lib.kubernetes.DeploySUSE)


Install Kubernetes Dashboard
----------------------------

Run on master node

.. code-block:: bash

    zypper install -y jq

    KUBERNETES_DASHBOARD_NAMESPACE="kubernetes-dashboard"
    KUBERNETES_DASHBOARD_LOCAL_PORT=20443
    KUBERNETES_DASHBOARD_YAML="https://raw.githubusercontent.com/kubernetes/dashboard/v2.0.0-beta3/aio/deploy/recommended.yaml"

    curl ${KUBERNETES_DASHBOARD_YAML} | kubectl apply -f -

    name="kubernetes-dashboard-cluster-admin"
    cluster_role="cluster-admin"
    service_account="kubernetes-dashboard:kubernetes-dashboard "

    kubectl get clusterrolebinding ${name} || kubectl create clusterrolebinding ${name} --clusterrole=${cluster_role} --serviceaccount=${service_account}

    kubectl get pods -n ${KUBERNETES_DASHBOARD_NAMESPACE} -o yaml | kubectl replace --force -f -


    namespace="${KUBERNETES_DASHBOARD_NAMESPACE}"
    service_account="${namespace}"
    service_name="service/${namespace}"

    secret_name="$( \
        kubectl -n ${namespace} get serviceaccounts -o json ${service_account} | \
            jq -r '.secrets[].name')"

    token="$( \
        kubectl -n ${namespace} get -o json secret $secret_name | \
            jq -r '.data.token' | base64 -d -)"

    local="${KUBERNETES_DASHBOARD_LOCAL_PORT}"

    echo ""
    echo "  Dashboard addr: https://127.0.0.1:${local}"
    echo "  Dashboard token: ${token}"
    echo "  Use Ctrl-C to stop port forwarding when you are done."
    echo ""

    kubectl --namespace "${namespace}" port-forward "${service_name}" "${local}:443" --address 0.0.0.0


Install Ceph Dashboard
----------------------

Run on master node

.. code-block:: bash

    zypper install -y jq

    ROOK_NAMESPACE=rook-ceph

    pass="$(kubectl --namespace "${ROOK_NAMESPACE}" get -o json secret rook-ceph-dashboard-password | \
                jq -r '.data.password' | base64 -d -)"
    echo ""
    echo "  Dashboard addr: https://127.0.0.1:8443"
    echo "  Dashboard user: admin"
    echo "  Dashboard pass: ${pass}"
    echo "  Use Ctrl-C to stop port forwarding when you are done."
    echo ""

    kubectl --namespace "${ROOK_NAMESPACE}" port-forward service/rook-ceph-mgr-dashboard 8443 --address 0.0.0.0
