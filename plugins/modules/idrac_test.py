import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac as idrac
import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac_module as idrac_module


def main():
    module = idrac_module.IDRACModule(
        supports_check_mode=False,
    )

    mgr = idrac.IDRAC.from_module(module)

    result = dict(
        changed=False,
    )

    module.exit_json(**result)


if __name__ == '__main__':
    main()

