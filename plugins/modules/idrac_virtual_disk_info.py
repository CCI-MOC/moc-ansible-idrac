import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac as idrac
import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac_module as idrac_module


def main():
    module_args = dict(
        disk=dict(type='dict'),
        disk_id=dict(type='str'),
    )

    module = idrac_module.IDRACModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )

    result = dict(
        changed=False,
    )

    if module.params['disk']:
        did = module.params['disk']['@odata.id']
    elif module.params['disk_id']:
        did = module.params['disk_id']
    else:
        module.fail_json(
            msg='you must provide one of disk or disk_id')

    disk = module.api.get_virtual_disk(did)

    result['idrac'] = {
        'disk': disk,
    }
    module.exit_json(**result)


if __name__ == '__main__':
    main()
