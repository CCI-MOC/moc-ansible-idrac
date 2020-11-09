import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac as idrac
import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac_module as idrac_module


def main():
    module_args = dict(
        reset_type=dict(type='str', required=True),
    )

    module = idrac_module.IDRACModule(
        argument_spec=module_args,
        supports_check_mode=False,
    )

    result = dict(
        changed=False,
    )

    try:
        module.api.reset_system(module.params['reset_type'])
    except idrac.OperationFailed as err:
        module.fail_json(msg=str(err))
    except ValueError as err:
        module.fail_json(msg='{}: invalid reset_type'.format(err))

    result['changed'] = True
    module.exit_json(**result)


if __name__ == '__main__':
    main()
