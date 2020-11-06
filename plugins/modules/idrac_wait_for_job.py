import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac as idrac
import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac_module as idrac_module


def main():
    module_args = dict(
        job=dict(type='dict'),
        job_id=dict(type='str'),
        state=dict(type='str', required=True),
        timeout=dict(type='int'),
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
    elif module.params['job_id']:
        jid = module.params['job_id']
    else:
        module.fail_json(
            msg='you must provide one of job or job_id')

    try:
        module.api.wait_for_job_state(
            jid,
            getattr(idrac.JOB_STATE, module.params['state']),
            timeout=module.params['timeout'],
        )
    except TimeoutError:
        module.fail_json(msg='Timeout waiting for job')

    job = module.api.get_job(jid)
    result['idrac'] = {
        'job': job,
    }
    module.exit_json(**result)


if __name__ == '__main__':
    main()
