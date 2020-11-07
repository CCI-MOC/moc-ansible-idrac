import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac as idrac
import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac_module as idrac_module


def main():
    module_args = dict(
        disk=dict(type='list', required=True),
    )

    module = idrac_module.IDRACModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    result = dict(
        changed=False,
    )

    for disk in module.api.list_all_virtual_disks():
        detail = module.api.get(disk)
        if any(
            'id' in spec and detail['Id'] == spec.get('id') or
            'name' in spec and detail['Name'] == spec.get('name')
            for spec in module.params['disk']
        ):
            break
    else:
        module.fail_json(msg='Failed to find any matching disks')

    result['idrac'] = {
        'disk': detail,
    }

    module.exit_json(**result)


if __name__ == '__main__':
    main()
