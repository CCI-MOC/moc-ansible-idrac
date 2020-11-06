import logging
import requests
import time
import types
import urllib3
import warnings

from enum import Enum
from urllib.parse import urljoin

# It is common from management controllers to have vendor-provided
# self-signed certificates. We don't need a warning every time we
# connect.
warnings.filterwarnings(
    'ignore',
    category=urllib3.exceptions.InsecureRequestWarning)

LOG = logging.getLogger(__name__)

MODULE_COMMON_ARGS = dict(
    host=dict(type='str', required=True),
    username=dict(type='str', required=True),
    password=dict(type='str', required=True, no_log=True),
    verify=dict(type='bool', default=True),
)


class JOB_STATE(Enum):
    unknown = 0
    scheduled = 1
    running = 2
    finished = 3
    failed = 10


class RESOURCES(types.SimpleNamespace):
    system = '/redfish/v1/Systems/System.Embedded.1'
    manager = '/redfish/v1/Managers/iDRAC.Embedded.1'
    storage = '/redfish/v1/Systems/System.Embedded.1/Storage'
    jobs = '/redfish/v1/Managers/iDRAC.Embedded.1/Jobs'


def extract_members(data):
    members = []
    for member in data['Members']:
        members.append({
            'uri': member['@odata.id'],
            'id': member['@odata.id'].split('/')[-1],
        })

    return members


class IDRACError(Exception):
    pass


class OperationInProgress(IDRACError):
    pass


class OperationFailed(IDRACError):
    def __init__(self, exc):
        self.request = exc.request
        self.response = exc.response

        if exc.response.text:
            data = exc.response.json()
        else:
            data = {}

        msg = str(exc)
        self.errors = []
        if 'error' in data:
            for error in data['error'].get('@Message.ExtendedInfo', []):
                self.errors.append((
                    error['MessageId'],
                    error['Message'],
                ))

        super().__init__(msg)


class JobSchedulingFailed(IDRACError):
    pass


class IDRAC(requests.Session):
    def __init__(self, host, username, password,
                 verify=True,
                 timeout=None):
        super().__init__()
        self.baseurl = 'https://{}'.format(host)
        self.auth = (username, password)
        self.headers['Content-type'] = 'application/json'
        self.verify = verify
        self.timeout = timeout

        self._cache = {}

    @classmethod
    def from_module(cls, module):
        '''Handy constructor for use by Ansible modules'''

        return cls(
            module.params['connection']['host'],
            module.params['connection']['username'],
            module.params['connection']['password'],
            verify=module.params['connection'].get('verify'),
            timeout=module.params['connection'].get('timeout'),
        )

    def request(self, method, url, **kwargs):
        if '://' in url:
            raise ValueError(
                'this class cannot fetch fully qualifed urls')

        url = urljoin(self.baseurl, url)

        LOG.info('fetch %s', url)

        res = super().request(method, url, **kwargs)
        try:
            res.raise_for_status()
        except requests.exceptions.HTTPError as err:
            raise OperationFailed(err)
        else:
            if res.headers['Content-type'].split(';')[0] != 'application/json':
                raise ValueError('unexpected content type {}'.format(
                    res.headers['Content-type']))

            if not res.text:
                data = {}
            else:
                data = res.json()

            data.update({
                '_location': res.headers.get('Location', ''),
            })

            return data

    def get(self, uri, **kwargs):
        '''Fetch a resource from the iDRAC using it's URI

        This will update the cached value of the resource (but this
        method does not return values from the cache; for that see
        the get_cached method)
        '''
        LOG.debug('get %s', uri)
        res = super().get(uri, **kwargs)
        self._cache[uri] = res
        return res

    def get_cached(self, uri, **kwargs):
        '''Like self.get, but return a cached value if one exists.

        Use this when fetching resources that won't change during the
        course of a session.
        '''
        LOG.debug('get %s, possibly from cache', uri)
        return self._cache[uri] if uri in self._cache else self.get(uri)

    def _execute_action(self, uri, action, **params):
        '''Execute a named action on a Redfish resource.

        Validates parameters against the allowed values provided
        by the resources.
        '''

        LOG.debug('trying to execute action %s on %s', action, uri)
        obj = self.get_cached(uri)

        # raises KeyError if the named action doesn't exist
        action = obj['Actions'][action]

        for pname, pval in params.items():
            # raises KeyError if the named parameter doesn't exist
            allowable_values = action['{}@Redfish.AllowableValues'.format(pname)]

            if pval not in allowable_values:
                raise ValueError(pval)

        return self.post(action['target'],
                         json=params)

    def list_storage_controllers(self):
        data = self.get_cached(RESOURCES.storage)
        return extract_members(data)

    def list_virtual_disks(self, uri):
        data = self.get_cached('{}/Volumes'.format(uri))
        return extract_members(data)

    def list_all_virtual_disks(self):
        disks = []
        for controller in self.list_storage_controllers():
            for member in self.list_virtual_disks(controller['uri']):
                disks.append(member)

        return disks

    def get_virtual_disk_by_name(self, want_name):
        for disk in self.list_all_virtual_disks():
            detail = self.get(disk['uri'])
            if detail['Name'] == want_name:
                return detail

    def get_virtual_disk_by_id(self, want_id):
        for disk in self.list_all_virtual_disks():
            detail = self.get(disk['uri'])
            if detail['Id'] == want_id:
                return detail

    def initialize_virtual_disk(self, uri, fast=True):
        LOG.debug('initialize disk %s (fast=%s)', uri, fast)
        init_type = 'Fast' if fast else 'Slow'
        disk = self.get(uri)
        if disk['Operations']:
            raise OperationInProgress()

        res = self._execute_action(
            uri,
            '#Volume.Initialize',
            InitializeType=init_type,
        )

        if 'JID' not in res['_location']:
            raise JobSchedulingFailed('failed to allocate job id')

        jid = res['_location'].split('/')[-1]
        return jid

    def list_jobs(self, detail=False):
        data = self.get_cached(RESOURCES.jobs)
        members = extract_members(data)

        if detail:
            return [self.get_job(member['uri']) for member in members]
        else:
            return members

    def get_job(self, jid):
        if not jid.startswith('/'):
            jid = '{}/{}'.format(RESOURCES.jobs, jid)

        return self.get(jid)

    def get_job_type(self, job):
        if job['JobType'] == 'RAIDConfiguration':
            job_type = 'staged'
        elif job['JobType'] == 'RealTimeNoRebootConfiguration':
            job_type = 'realtime'
        else:
            raise ValueError(job['JobType'])

        return job_type

    def get_job_state(self, job):
        if 'failed' in job['Message'].lower():
            return JOB_STATE.failed
        elif job['Message'] == 'Task successfully scheduled.':
            return JOB_STATE.scheduled
        elif job['Message'] == 'Job in progress.':
            return JOB_STATE.running
        elif job['Message'] == 'Job completed successfully.':
            return JOB_STATE.finished
        else:
            return JOB_STATE.unknown

    def get_system(self):
        return self.get(RESOURCES.system)

    def wait_for_job_state(self, jid, want_state, timeout=None):
        LOG.info('waiting for job state %s', want_state)
        time_start = time.time()

        while True:
            job = self.get_job(jid)
            have_state = self.get_job_state(job)
            LOG.debug('want %s, have %s', want_state, have_state)

            if have_state == want_state:
                break

            if timeout and (time.time() - time_start) > timeout:
                raise TimeoutError()

            time.sleep(5)

    def wait_for_power_state(self, want_state, timeout=None):
        LOG.info('waiting for power state %s', want_state)
        time_start = time.time()

        while True:
            system = self.get_system()
            have_state = system['PowerState']
            LOG.debug('want %s, have %s', want_state, have_state)

            if want_state == have_state:
                break

            if timeout and (time.time() - time_start) > timeout:
                raise TimeoutError()

            time.sleep(5)

    def get_manager(self):
        return self.get(RESOURCES.manager)

    def reset_manager(self):
        return self._execute_action(
            RESOURCES.manager,
            '#Manager.Reset',
            ResetType='GracefulRestart',
        )

    def reset_system(self, reset_type):
        return self._execute_action(
            RESOURCES.system,
            '#ComputerSystem.Reset',
            ResetType=reset_type,
        )

    def power_cycle_system(self, timeout=300):
        LOG.info('power cycling system')
        system = self.get_system()

        if system['PowerState'] == 'On':
            self.reset_system('GracefulShutdown')
            try:
                self.wait_for_power_state('Off', timeout=timeout)
            except TimeoutError:
                LOG.error('system failed to shut down gracefully; forcing off')
                self.reset_system('ForceOff')
                self.wait_for_power_state('Off', timeout=timeout)

        self.reset_system('On')
        self.wait_for_power_state('On', timeout=timeout)
