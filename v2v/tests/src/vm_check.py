import os
import re
import time
import logging
import commands
from autotest.client.shared import error
from virttest import utils_v2v
from virttest import data_dir
from virttest import virsh


def run(test, params, env):
    """
    Check VM after conversion
    """
    target = params.get('target')
    vm_name = params.get('main_vm')
    os_type = params.get('os_type', 'linux')
    target = params.get('target', 'libvirt')

    def check_linux_vm(check_obj):
        """
        Check linux guest after v2v convert.
        """
        # Create ssh session for linux guest
        check_obj.create_session()
        logging.info("Check guest os info")
        os_info = check_obj.get_vm_os_info()
        os_vendor = check_obj.get_vm_os_vendor()
        if os_vendor == 'Red Hat':
            os_version = os_info.split()[6]
        else:
            raise error.TestFail("Only RHEL is supported now.")

        logging.info("Check guest kernel after conversion")
        kernel_version = check_obj.get_vm_kernel()
        if re.search('xen', kernel_version):
            raise error.TestFail("FAIL")
        else:
            logging.info("SUCCESS")

        logging.info("Check parted info after conversion")
        parted_info = check_obj.get_vm_parted()
        if os_version != '3':
            if re.findall('/dev/vd\S+', parted_info):
                logging.info("SUCCESS")
            else:
                raise error.TestFail("FAIL")

        logging.info("Check virtio_net module in modprobe conf")
        modprobe_conf = check_obj.get_vm_modprobe_conf()
        if not re.search('No such file', modprobe_conf):
            virtio_mod = re.findall(r'(?m)^alias.*virtio', modprobe_conf)
            net_blk_mod = re.findall(r'(?m)^alias\s+scsi|(?m)^alias\s+eth',
                                     modprobe_conf)
            if len(virtio_mod) == len(net_blk_mod):
                logging.info("SUCCESS")
            else:
                raise error.TestFail("FAIL")

        logging.info("Check virtio module")
        modules = check_obj.get_vm_modules()
        if os_version == '3':
            if re.search("e1000|^ide", modules):
                logging.info("SUCCESS")
            else:
                raise error.TestFail("FAIL")
        elif re.search("virtio", modules):
            logging.info("SUCCESS")
        else:
            raise error.TestFail("FAIL")

        logging.info("Check virtio pci devices")
        pci = check_obj.get_vm_pci_list()
        if os_version != '3':
            if (re.search('[Vv]irtio network', pci) and
                    re.search('[Vv]irtio block', pci)):
                if target == "ovirt":
                    logging.info("SUCCESS")
                elif (target != "ovirt" and
                      re.search('[Vv]irtio memory', pci)):
                    logging.info("SUCCESS")
                else:
                    raise error.TestFail("FAIL")
            else:
                raise error.TestFail("FAIL")

        logging.info("Check in /etc/rc.local")
        rc_output = check_obj.get_vm_rc_local()
        if re.search('^[modprobe|insmod].*xen-vbd.*', rc_output):
            raise error.TestFail("FAIL")
        else:
            logging.info("SUCCESS")

        logging.info("Check vmware tools")
        if check_obj.has_vmware_tools() is False:
            logging.info("SUCCESS")
        else:
            raise error.TestFail("FAIL")

        logging.info("Check tty")
        tty = check_obj.get_vm_tty()
        if re.search('[xh]vc0', tty):
            raise error.TestFail("FAIL")
        else:
            logging.info("SUCCESS")

        logging.info("Check video")
        video = check_obj.get_vm_video()
        if target == 'ovirt':
            if re.search('qxl', video):
                logging.info("SUCCESS")
            else:
                raise error.TestFail("FAIL")
        else:
            # dump VM XML
            cmd = "virsh dumpxml %s |grep -A 3 '<video>'" % vm_name
            status, output = commands.getstatusoutput(cmd)
            # get remote session
            if status:
                raise error.TestError(vm_name, output)

            video_model = ""
            video_type = re.search("type='[a-z]*'", output)
            if video_type:
                video_model = eval(video_type.group(0).split('=')[1])

            if re.search('el7', kernel_version):
                if 'cirrus' in output:
                    if re.search('kms', video):
                        logging.info("SUCCESS")
                    else:
                        raise error.TestFail("FAIL")
                else:
                    if re.search(video_model, video):
                        logging.info("SUCCESS")
                    else:
                        raise error.TestFail("FAIL")
            else:
                if re.search(video_model, video):
                    logging.info("SUCCESS")
                else:
                    raise error.TestFail("FAIL")

        logging.info("Check device mapping")
        dev_map = ""
        if re.search('el7', kernel_version):
            dev_map = '/boot/grub2/device.map'
        else:
            dev_map = '/boot/grub/device.map'

        if check_obj.get_grub_device(dev_map):
            logging.info("SUCCESS")
        else:
            raise error.TestFail("FAIL")

    def check_windows_vm(check_obj):
        """
        Check windows guest after v2v convert.
        """
        match_image_timeout = 300
        logging.info("Initialize windows in %s seconds", match_image_timeout)
        compare_screenshot_vms = ["win2003", "win2008", "win2008r2", "win7"]
        timeout_msg = "Not match expected images in %s" % match_image_timeout
        timeout_msg += " seconds, try to login VM directly"
        match_image_list = []
        if check_obj.os_version in compare_screenshot_vms:
            image_name_list = params.get("images_for_match", '').split(',')
            for image_name in image_name_list:
                match_image = os.path.join(data_dir.get_data_dir(), image_name)
                if not os.path.exists(match_image):
                    raise error.TestError("%s not exist" % match_image)
                match_image_list.append(match_image)
            img_match_ret = check_obj.wait_for_match(match_image_list,
                                                     timeout=match_image_timeout)
            if img_match_ret < 0:
                logging.error(timeout_msg)
            else:
                if check_obj.os_version == "win2003":
                    if img_match_ret == 0:
                        check_obj.click_left_button()
                        time.sleep(20)
                        check_obj.click_tab_enter()
                    elif img_match_ret == 1:
                        check_obj.click_left_button()
                        time.sleep(20)
                        check_obj.click_tab_enter()
                        check_obj.click_left_button()
                        check_obj.send_win32_key('VK_RETURN')
                    else:
                        pass
                elif check_obj.os_version in ["win7", "win2008r2"]:
                    if img_match_ret in [0, 1]:
                        check_obj.click_left_button()
                        check_obj.click_left_button()
                        check_obj.send_win32_key('VK_TAB')
                        check_obj.click_tab_enter()
                elif check_obj.os_version == "win2008":
                    if img_match_ret in [0, 1]:
                        check_obj.click_tab_enter()
                        check_obj.click_install_driver()
                        check_obj.move_mouse((0, -50))
                        check_obj.click_left_button()
                        check_obj.click_tab_enter()
                    else:
                        check_obj.click_install_driver()
        else:
            # No need sendkey/click button for Win8, Win8.1, Win2012, Win2012r2
            # So give a long timeout(10 min)for these VMs
            check_obj.timeout = 600
            logging.info("%s is booting up ...", check_obj.os_version)
        # Try to create nc/telnet session for windows guest
        check_obj.create_session()

        # 1. Check viostor file
        logging.info("Check windows viostor info")
        viostor_check = True
        output = check_obj.get_viostor_info()
        if not output:
            viostor_check = False
            logging.error("Windows viostor info check failed")

        # 2. Check Red Hat drivers
        logging.info("Check Red Hat drivers")
        driver_check = True
        win_dirves = check_obj.get_driver_info()
        virtio_drivers = ["Red Hat VirtIO SCSI",
                          "Red Hat VirtIO Ethernet Adapte"]
        for driver in virtio_drivers:
            if driver in win_dirves:
                logging.info("Find driver: %s", driver)
            else:
                driver_check = False
                logging.error("Not find driver: %s", driver)
        video_driver = "vga"
        if target == "ovirt":
            video_driver = "qxl"
        win_dirves = check_obj.get_driver_info(signed=False)
        if video_driver in win_dirves:
            logging.info("Find driver: %s", video_driver)
        else:
            #driver_check = False
            logging.error("Not find driver: %s", video_driver)

        # 3. Renew network
        logging.info("Renew network for windows guest")
        network_check = True
        if not check_obj.get_network_restart():
            logging.error("Renew network failed")
            network_check = False
        if not all([viostor_check, driver_check, network_check]):
            raise error.TestFail("Windows check failed as above errors")

    check_obj = utils_v2v.VMCheck(test, params, env)
    try:
        virsh_session_id = None
        if target == "ovirt":
            virsh_session = utils_v2v.VirshSessionSASL(params)
            virsh_session_id = virsh_session.get_id()
        check_obj.virsh_session_id = virsh_session_id
        if os_type == "linux":
            check_linux_vm(check_obj)
        else:
            check_windows_vm(check_obj)
    finally:
        if check_obj:
            if check_obj.session:
                check_obj.session.close()
            check_obj.cleanup()
