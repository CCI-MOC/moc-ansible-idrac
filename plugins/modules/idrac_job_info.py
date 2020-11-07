import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac as idrac
import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac_module as idrac_module


def main():
    module_args = dict(
        job=dict(type='dict'),
        job_id=dict(type='str'),
    )

    module = idrac_module.IDRACModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )

    result = dict(
        changed=False,
    )

    if module.params['job']:
        jid = module.params['job']['@odata.id']
    else:
        jid = module.params['job_id']

    job = module.api.get_job(jid)
    job['state'] = module.api.get_job_state(job)

    result['idrac'] = {
        'job': job,
    }

    module.exit_json(**result)


if __name__ == '__main__':
    main()
