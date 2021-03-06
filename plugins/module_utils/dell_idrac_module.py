from ansible.module_utils.basic import AnsibleModule
import ansible_collections.moc.idrac.plugins.module_utils.dell_idrac as idrac

AUTH_REQUIRED_KEYS = (
    'username', 'password'
)


class IDRACModule(AnsibleModule):
    def __init__(self, argument_spec=None, **kwargs):
        if argument_spec is None:
            argument_spec = {}

        argument_spec.update({
            'host': {
                'type': 'str',
                'required': True,
            },
            'timeout': {
                'type': 'int',
                'required': False,
            },
            'auth': {
                'type': 'dict',
                'required': True,
            }
        })

        super().__init__(argument_spec=argument_spec, **kwargs)

        for k in AUTH_REQUIRED_KEYS:
            if k not in self.params.get('auth', {}):
                self.fail_json(
                    msg='missing required auth option {}'.format(k))

        self.api = idrac.IDRAC(
            self.params['host'],
            self.params['auth']['username'],
            self.params['auth']['password'],
            verify=self.params['auth'].get('verify'),
            timeout=self.params.get('timeout'),
        )
