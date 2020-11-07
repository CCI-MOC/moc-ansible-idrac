from ansible.module_utils.basic import AnsibleModule
import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac as idrac

CONNECTION_REQUIRED_KEYS = (
    'host', 'username', 'password'
)


class IDRACModule(AnsibleModule):
    def __init__(self, argument_spec=None, **kwargs):
        if argument_spec is None:
            argument_spec = {}

        argument_spec.update({
            'connection': {
                'type': 'dict',
                'required': True,
            }
        })

        super().__init__(argument_spec=argument_spec, **kwargs)

        for k in CONNECTION_REQUIRED_KEYS:
            if k not in self.params.get('connection', {}):
                self.fail_json(
                    msg='missing required connection option {}'.format(k))

        self.api = idrac.IDRAC(
            self.params['connection']['host'],
            self.params['connection']['username'],
            self.params['connection']['password'],
            verify=self.params['connection'].get('verify'),
            timeout=self.params['connection'].get('timeout'),
        )
