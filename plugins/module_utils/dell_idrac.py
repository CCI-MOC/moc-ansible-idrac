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


class IDRACError(Exception):
    '''Base class for other exceptions raised by this module'''
    pass


class OperationInProgress(IDRACError):
    '''Attempt to start a job when another one is already scheduled'''
    pass


class OperationFailed(IDRACError):
    '''Raised when an action returns an HTTP error.

    The 'error' key is a list [MessageId, Message] tuples
    returned by the Redfish API.

    The 'request' and 'response' keys contain, respectively,
    the request and response objects.
    '''

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
    '''Failed to get job ID when scheduling a job'''
    pass


class IDRAC(requests.Session):
    def __init__(self, host, username, password,
                 verify=True,
                 timeout=None):
        super().__init__()
        self.baseurl = 'https://{}'.format(host)

        # set up the requests.Session attributes
        self.auth = (username, password)
        self.headers['Content-type'] = 'application/json'
        self.verify = verify
        self.timeout = timeout

        self._cache = {}

    def request(self, method, uri, **kwargs):
        '''Fetch a Redfish resource and return the unserialized response

        Requests the named uri, decodes the JSON response, and
        returns the resulting dictionary to the caller.

        The uri argument must be an absolute but unqualified URI. It
        is expected (but not required) to start with '/redfish'.
        '''

        if '://' in uri:
            raise ValueError(
                'this class cannot fetch fully qualifed urls')

        if not uri.startswith('/redfish'):
            LOG.warning('%s does not look like a redfish uri', uri)

        url = urljoin(self.baseurl, uri)

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

            # Because the job id for e.g. initilization jobs is
            # delivered via the Location header
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

    def _extract_members(self, data,
                         member_attr='Members',
                         detail=False,
                         cache=False):
        '''Return the list of members from a Redfish container resource'''
        members = []
        for member in data[member_attr]:
            uri = member['@odata.id']

            if detail:
                if cache:
                    members.append(self.get_cached(uri))
                else:
                    members.append(self.get(uri))
            else:
                members.append(uri)

        return members

    def _execute_action(self, uri, action, **params):
        '''Execute a named action on a Redfish resource.

        Validates parameters against the allowed values provided by the
        '@Redfish.AllowableValues' key on the action descriptor.
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

    def list_storage_controllers(self, detail=False):
        data = self.get_cached(RESOURCES.storage)
        return self._extract_members(data, detail=detail, cache=True)

    def list_virtual_disks(self, uri, detail=False):
        '''Return a list of virtual disks on the given controller'''

        data = self.get_cached('{}/Volumes'.format(uri))
        return self._extract_members(data, detail=detail, cache=True)

    def list_all_virtual_disks(self, detail=False):
        '''Return a list of virtual disks on all controllers'''

        disks = []
        for controller in self.list_storage_controllers():
            for member in self.list_virtual_disks(
                    controller, detail=True):
                disks.append(member)

        return disks

    def get_virtual_disk_by_name(self, want_name):
        '''Find a virtual disk for which the Name key matches want_name'''

        for disk in self.list_all_virtual_disks():
            detail = self.get(disk)
            if detail['Name'] == want_name:
                return detail

    def get_virtual_disk_by_id(self, want_id):
        '''Find a virtual disk for which the Id key matches want_id'''

        for disk in self.list_all_virtual_disks():
            detail = self.get(disk)
            if detail['Id'] == want_id:
                return detail

    def initialize_virtual_disk(self, uri, fast=True):
        '''Initialize a virtual disk.

        Schedules an initialization job and returns the job id.
        '''

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
        members = self._extract_members(data)

        if detail:
            return [self.get_job(member) for member in members]
        else:
            return members

    def get_job(self, jid):
        '''Get a job by ID or URI.

        The 'jid' parameter may either by a raw job id (JID_123456) or
        the uri of a job (/redfish/v1/.../Jobs/JID_123456).
        '''

        if not jid.startswith('/'):
            jid = '{}/{}'.format(RESOURCES.jobs, jid)

        return self.get(jid)

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
        '''Wait until a job reaches want_state.

        This calls get_job, so jid may be either a raw job id or
        a job uri.

        If timeout is not None, raise a TimeoutError if the job
        does not reach the specified state in timeout seconds.
        '''

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
        '''Wait for the system to achieve the named power state.

        If timeout is not None, raise a TimeoutError if the system
        does not reach the specified state in timeout seconds.
        '''

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
        '''Reset the iDRAC'''

        return self._execute_action(
            RESOURCES.manager,
            '#Manager.Reset',
            ResetType='GracefulRestart',
        )

    def reset_system(self, reset_type):
        '''Reset the system.

        This calls the '#ComputerSystem.Reset' action on the system
        resource, which is used to control the system power state.
        '''

        return self._execute_action(
            RESOURCES.system,
            '#ComputerSystem.Reset',
            ResetType=reset_type,
        )

    def power_cycle_system(self, timeout=300):
        '''Power cycle the system.

        This will perform a graceful shutdown of the system followed by
        a power on.  If the system does not power off within timeout
        seconds, force the system off and then power it on.

        Raises a TimeoutError if the system fails to reach the required
        power states within timeout seconds (each).
        '''

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
