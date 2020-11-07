import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac as idrac
import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac_module as idrac_module


def main():
    module_args = dict(
    )

    module = idrac_module.IDRACModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )

    result = dict(
        changed=False,
    )

    system = module.api.get_system()

    result['idrac'] = {
        'system': system,
    }

    module.exit_json(**result)


if __name__ == '__main__':
    main()
