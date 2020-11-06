import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac as idrac
import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac_module as idrac_module


def main():
    module_args = dict(
        timeout=dict(type='int'),
    )

    module = idrac_module.IDRACModule(
        argument_spec=module_args,
        supports_check_mode=False,
    )

    result = dict(
        changed=False,
    )

    try:
        module.api.power_cycle_system(timeout=module.params['timeout'])
    except TimeoutError:
        module.fail_json('Timeout waiting for reboot')

    result['changed'] = True
    module.exit_json(**result)


if __name__ == '__main__':
    main()
