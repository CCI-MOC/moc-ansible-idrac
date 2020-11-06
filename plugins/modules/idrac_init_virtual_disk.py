import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac as idrac
import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac_module as idrac_module


def main():
    module_args = dict(
        disk=dict(type='dict'),
        disk_id=dict(type='str'),
        fast=dict(type='bool', default=True),
    )

    module = idrac_module.IDRACModule(
        argument_spec=module_args,
        supports_check_mode=False,
    )

    result = dict(
        changed=False,
    )

    if not module.params['disk'] or module.params['disk_id']:
        module.fail_json(msg='Must provide one of disk or disk_id')

    if module.params['disk']:
        disk = module.params['disk']
        disk_id = disk['@odata.id']
    else:
        disk_id = module.params['disk_id']

    try:
        jid = module.api.initialize_virtual_disk(disk_id, fast=module.params['fast'])
    except idrac.OperationFailed as err:
        module.fail_json(msg='failed to initialize disk',
                         errors=err.errors)
    result['changed'] = True
    result['idrac'] = {
        'job': {
            'id': jid,
        }
    }

    module.exit_json(**result)


if __name__ == '__main__':
    main()
