import os
import logging
from virttest import utils_v2v
from virttest import utils_misc
from virttest import utils_sasl
from virttest import ovirt
from autotest.client import utils
from autotest.client.shared import ssh_key, error

LINUX_VM_TIMEOUT = 500
WINDOWS_VM_TIMEOUT = 800


def get_args_dict(params):
    args_dict = {}
    keys_list = ['target', 'main_vm', 'ovirt_engine_url', 'ovirt_engine_user',
                 'ovirt_engine_password', 'hypervisor', 'storage',
                 'remote_node_user', 'v2v_opts', 'export_name', 'storage_name',
                 'cluster_name']

    if params.get('network'):
        keys_list.append('network')

    if params.get('bridge'):
        keys_list.append('bridge')

    hypervisor = params.get('hypervisor')
    if hypervisor == 'esx':
        esx_args_list = ['vpx_ip', 'vpx_pwd', 'vpx_pwd_file',
                         'vpx_dc', 'esx_ip', 'hostname']
        keys_list += esx_args_list

    if hypervisor == 'xen':
        xen_args_list = ['xen_ip', 'xen_pwd', 'hostname']
        keys_list += xen_args_list

    for key in keys_list:
        val = params.get(key)
        if val is None:
            raise KeyError("%s doesn't exist" % key)
        elif val.count("EXAMPLE"):
            raise error.TestNAError("Please provide specific value for %s: %s",
                                    key, val)
        else:
            args_dict[key] = val

    logging.debug(args_dict)
    return args_dict

def run(test, params, env):
    """
    Test convert vm to ovirt
    """

    def import_to_ovirt():
        """
        Import VM from export domain to oVirt Data Center
        """
        os_type = params.get('os_type')
        export_name = params.get('export_name')
        storage_name = params.get('storage_name')
        cluster_name = params.get('cluster_name')
        address_cache = env.get('address_cache')
        # Check ovirt status
        dc = ovirt.DataCenterManager(params)
        logging.info("Current data centers list: %s" % dc.list())
        cls = ovirt.ClusterManager(params)
        logging.info("Current cluster list: %s" % cls.list())
        ht = ovirt.HostManager(params)
        logging.info("Current host list: %s" % ht.list())
        sd = ovirt.StorageDomainManager(params)
        logging.info("Current storage domain list: %s" % sd.list())
        vm = ovirt.VMManager(params, address_cache)
        logging.info("Current vm list: %s" % vm.list())
        timeout = LINUX_VM_TIMEOUT
        wait_for_up = True
        if os_type == 'windows':
            timeout = WINDOWS_VM_TIMEOUT
            wait_for_up = False
        try:
            # Import VM
            vm.import_from_export_domain(export_name,
                                         storage_name,
                                         cluster_name,
                                         timeout=timeout)
            logging.info("The latest list: %s" % vm.list())
        except Exception, e:
            # Try to delete the vm from export domain
            vm.delete_from_export_domain(export_name)
            raise error.TestFail("Import %s failed: %s" % (vm.name, e))
        # Start VM after import successfully
        vm.start(wait_for_up=wait_for_up, timeout=timeout)

    args_dict = get_args_dict(params)
    hypervisor = args_dict.get('hypervisor')
    xen_ip = args_dict.get('xen_ip')
    xen_pwd = args_dict.get('xen_pwd')
    remote_node_user = args_dict.get('remote_node_user', 'root')
    vpx_pwd = args_dict.get('vpx_pwd')
    vpx_pwd_file = args_dict.get('vpx_pwd_file')

    # Set libguestfs environment
    os.environ['LIBGUESTFS_BACKEND'] = 'direct'

    if hypervisor == 'xen':
        ssh_key.setup_ssh_key(xen_ip, user=remote_node_user,
                              port=22, password=xen_pwd)
        # Note that password-interactive and Kerberos access are not supported.
        # You have to set up ssh access using ssh-agent and authorized_keys.
        try:
            utils_misc.add_identities_into_ssh_agent()
        except:
            utils.run("ssh-agent -k")
            raise error.TestFail("Failed to start 'ssh-agent'")

    if hypervisor == 'esx':
        logging.info("Building ESX no password interactive verification.")
        fp = open(vpx_pwd_file, 'w')
        fp.write(vpx_pwd)
        fp.close()

    # Create sasl user on the ovirt host
    user_pwd = "[[%s, %s]]" % (params.get("sasl_user"), params.get("sasl_pwd"))
    sasl_args = {'sasl_user_pwd': user_pwd}
    v2v_sasl = utils_sasl.SASL(*sasl_args)
    v2v_sasl.server_ip = params.get("remote_ip")
    v2v_sasl.server_user = params.get('remote_user')
    v2v_sasl.server_pwd = params.get('remote_pwd')
    v2v_sasl.setup()

    try:
        # Run test case
        ret = utils_v2v.v2v_cmd(args_dict)
        logging.debug("virt-v2 verbose messages:\n%s", ret)
        if ret.exit_status != 0:
            raise error.TestFail("Convert VM failed")
        import_to_ovirt()
    finally:
        v2v_sasl.cleanup()
        if hypervisor == "xen":
            utils.run("ssh-agent -k")
        if hypervisor == "esx":
            utils.run("rm -rf %s" % vpx_pwd_file)
