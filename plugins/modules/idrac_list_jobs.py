import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac as idrac
import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac_module as idrac_module


def main():
    module_args = dict(
        states=dict(type='list'),
        detail=dict(type='bool', default=False),
    )

    module = idrac_module.IDRACModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )

    result = dict(
        changed=False,
    )

    if module.params['states'] and not module.params['detail']:
        module.fail_json(
            msg='filtering by state requires detail=true')

    jobs = module.api.list_jobs(detail=module.params['detail'])

    if module.params['states']:
        states = [getattr(idrac.JOB_STATE, state) for state in module.params['states']]
    else:
        states = None

    result['idrac'] = {
        'jobs': [job for job in jobs
                 if states is None or
                 module.api.get_job_state(job) in states]
    }

    module.exit_json(**result)


if __name__ == '__main__':
    main()
