#!/usr/bin/python

#
# Copyright (c) 2015 CenturyLink
#
# This file is part of Ansible.
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>
#

DOCUMENTATION = '''
module: clc_publicip
short_description: Add and Delete public ips on servers in CenturyLink Cloud.
description:
  - An Ansible module to add or delete public ip addresses on an existing server or servers in CenturyLink Cloud.
version_added: "2.0"
options:
  protocol:
    description:
      - The protocol that the public IP will listen for.
    default: TCP
    choices: ['TCP', 'UDP', 'ICMP']
    required: False
  ports:
    description:
      - A list of ports to expose. This is required when state is 'present'
    required: False
    default: None
  server_ids:
    description:
      - A list of servers to create public ips on.
    required: True
  source_restrictions:
    description:
      - The source IP address range allowed to access the new public IP address.
        Used to restrict access to only the specified range of source IPs.
        The IP range allowed to access the public IP should be specified using CIDR notation.
    required: False
    default: None
  state:
    description:
      - Determine whether to create or delete public IPs. If present module will not create a second public ip if one
        already exists.
    default: present
    choices: ['present', 'absent']
    required: False
  wait:
    description:
      - Whether to wait for the tasks to finish before returning.
    choices: [ True, False ]
    default: True
    required: False
requirements:
    - python = 2.7
    - requests >= 2.5.0
    - clc-sdk
author: "CLC Runner (@clc-runner)"
notes:
    - To use this module, it is required to set the below environment variables which enables access to the
      Centurylink Cloud
          - CLC_V2_API_USERNAME, the account login id for the centurylink cloud
          - CLC_V2_API_PASSWORD, the account password for the centurylink cloud
    - Alternatively, the module accepts the API token and account alias. The API token can be generated using the
      CLC account login and password via the HTTP api call @ https://api.ctl.io/v2/authentication/login
          - CLC_V2_API_TOKEN, the API token generated from https://api.ctl.io/v2/authentication/login
          - CLC_ACCT_ALIAS, the account alias associated with the centurylink cloud
    - Users can set CLC_V2_API_URL to specify an endpoint for pointing to a different CLC environment.
'''

EXAMPLES = '''
# Note - You must set the CLC_V2_API_USERNAME And CLC_V2_API_PASSWD Environment variables before running these examples

- name: Add Public IP to Server
  hosts: localhost
  gather_facts: False
  connection: local
  tasks:
    - name: Create Public IP For Servers
      clc_publicip:
        protocol: 'TCP'
        ports:
            - 80
        server_ids:
            - UC1TEST-SVR01
            - UC1TEST-SVR02
        state: present
      register: clc

    - name: debug
      debug: var=clc

- name: Delete Public IP from Server
  hosts: localhost
  gather_facts: False
  connection: local
  tasks:
    - name: Create Public IP For Servers
      clc_publicip:
        server_ids:
            - UC1TEST-SVR01
            - UC1TEST-SVR02
        state: absent
      register: clc

    - name: debug
      debug: var=clc
'''

RETURN = '''
changed:
    description: A flag indicating if any change was made or not
    returned: success
    type: boolean
    sample: True
server_ids:
    description: The list of server ids that are changed
    returned: success
    type: list
    sample:
        [
            "UC1TEST-SVR01",
            "UC1TEST-SVR02"
        ]
'''

__version__ = '${version}'

from distutils.version import LooseVersion

try:
    import requests
except ImportError:
    REQUESTS_FOUND = False
else:
    REQUESTS_FOUND = True

#
#  Requires the clc-python-sdk.
#  sudo pip install clc-sdk
#
try:
    import clc as clc_sdk
    from clc import CLCException
except ImportError:
    CLC_FOUND = False
    clc_sdk = None
else:
    CLC_FOUND = True


class ClcPublicIp(object):
    clc = clc_sdk
    module = None

    def __init__(self, module):
        """
        Construct module
        """
        self.module = module
        if not CLC_FOUND:
            self.module.fail_json(
                msg='clc-python-sdk required for this module')
        if not REQUESTS_FOUND:
            self.module.fail_json(
                msg='requests library is required for this module')
        if requests.__version__ and LooseVersion(requests.__version__) < LooseVersion('2.5.0'):
            self.module.fail_json(
                msg='requests library  version should be >= 2.5.0')

        self._set_user_agent(self.clc)

    def process_request(self):
        """
        Process the request - Main Code Path
        :return: Returns with either an exit_json or fail_json
        """
        self._set_clc_credentials_from_env()
        params = self.module.params
        server_ids = params['server_ids']
        ports = params['ports']
        protocol = params['protocol']
        restrictions = params.get('source_restrictions')
        state = params['state']

        if state == 'present':
            changed, changed_server_ids, requests = self.ensure_public_ip_present(
                server_ids=server_ids, protocol=protocol, ports=ports, source_restrictions=restrictions)
        elif state == 'absent':
            changed, changed_server_ids, requests = self.ensure_public_ip_absent(
                server_ids=server_ids)
        else:
            return self.module.fail_json(msg="Unknown State: " + state)
        self._wait_for_requests_to_complete(requests)
        return self.module.exit_json(changed=changed,
                                     server_ids=changed_server_ids)

    @staticmethod
    def _define_module_argument_spec():
        """
        Define the argument spec for the ansible module
        :return: argument spec dictionary
        """
        argument_spec = dict(
            server_ids=dict(type='list', required=True),
            protocol=dict(default='TCP', choices=['TCP', 'UDP', 'ICMP']),
            ports=dict(type='list'),
            source_restrictions=dict(type='list'),
            wait=dict(type='bool', default=True),
            state=dict(default='present', choices=['present', 'absent']),
        )
        return argument_spec

    def ensure_public_ip_present(self, server_ids, protocol, ports, source_restrictions=None):
        """
        Ensures the given server ids having the public ip available
        :param server_ids: the list of server ids
        :param protocol: the ip protocol
        :param ports: the list of ports to expose
        :param source_restrictions: The list of IP range allowed to access the public IP, specified using CIDR notation.
        :return: (changed, changed_server_ids, results)
                  changed: A flag indicating if there is any change
                  changed_server_ids : the list of server ids that are changed
                  results: The result list from clc public ip call
        """
        changed = False
        results = []
        changed_server_ids = []
        restrictions_list = []
        servers = self._get_servers_from_clc(
            server_ids,
            'Failed to obtain server list from the CLC API')
        servers_to_change = [
            server for server in servers if len(
                server.PublicIPs().public_ips) == 0]
        ports_to_expose = [{'protocol': protocol, 'port': port}
                           for port in ports]
        if source_restrictions:
            restrictions_list = [{'cidr': cidr} for cidr in source_restrictions]
        for server in servers_to_change:
            if not self.module.check_mode:
                result = self._add_publicip_to_server(server, ports_to_expose, source_restrictions=restrictions_list)
                results.append(result)
            changed_server_ids.append(server.id)
            changed = True
        return changed, changed_server_ids, results

    def _add_publicip_to_server(self, server, ports_to_expose, source_restrictions=None):
        result = None
        try:
            result = server.PublicIPs().Add(ports=ports_to_expose, source_restrictions=source_restrictions)
        except CLCException, ex:
            self.module.fail_json(msg='Failed to add public ip to the server : {0}. {1}'.format(
                server.id, ex.response_text
            ))
        return result

    def ensure_public_ip_absent(self, server_ids):
        """
        Ensures the given server ids having the public ip removed if there is any
        :param server_ids: the list of server ids
        :return: (changed, changed_server_ids, results)
                  changed: A flag indicating if there is any change
                  changed_server_ids : the list of server ids that are changed
                  results: The result list from clc public ip call
        """
        changed = False
        results = []
        changed_server_ids = []
        servers = self._get_servers_from_clc(
            server_ids,
            'Failed to obtain server list from the CLC API')
        servers_to_change = [
            server for server in servers if len(
                server.PublicIPs().public_ips) > 0]
        for server in servers_to_change:
            if not self.module.check_mode:
                result = self._remove_publicip_from_server(server)
                results.append(result)
            changed_server_ids.append(server.id)
            changed = True
        return changed, changed_server_ids, results

    def _remove_publicip_from_server(self, server):
        result = None
        try:
            for ip_address in server.PublicIPs().public_ips:
                    result = ip_address.Delete()
        except CLCException, ex:
            self.module.fail_json(msg='Failed to remove public ip from the server : {0}. {1}'.format(
                server.id, ex.response_text
            ))
        return result

    def _wait_for_requests_to_complete(self, requests_lst):
        """
        Waits until the CLC requests are complete if the wait argument is True
        :param requests_lst: The list of CLC request objects
        :return: none
        """
        if not self.module.params['wait']:
            return
        for request in requests_lst:
            request.WaitUntilComplete()
            for request_details in request.requests:
                if request_details.Status() != 'succeeded':
                    self.module.fail_json(
                        msg='Unable to process public ip request')

    def _set_clc_credentials_from_env(self):
        """
        Set the CLC Credentials on the sdk by reading environment variables
        :return: none
        """
        env = os.environ
        v2_api_token = env.get('CLC_V2_API_TOKEN', False)
        v2_api_username = env.get('CLC_V2_API_USERNAME', False)
        v2_api_passwd = env.get('CLC_V2_API_PASSWD', False)
        clc_alias = env.get('CLC_ACCT_ALIAS', False)
        api_url = env.get('CLC_V2_API_URL', False)

        if api_url:
            self.clc.defaults.ENDPOINT_URL_V2 = api_url

        if v2_api_token and clc_alias:
            self.clc._LOGIN_TOKEN_V2 = v2_api_token
            self.clc._V2_ENABLED = True
            self.clc.ALIAS = clc_alias
        elif v2_api_username and v2_api_passwd:
            self.clc.v2.SetCredentials(
                api_username=v2_api_username,
                api_passwd=v2_api_passwd)
        else:
            return self.module.fail_json(
                msg="You must set the CLC_V2_API_USERNAME and CLC_V2_API_PASSWD "
                    "environment variables")

    def _get_servers_from_clc(self, server_ids, message):
        """
        Gets list of servers form CLC api
        """
        try:
            return self.clc.v2.Servers(server_ids).servers
        except CLCException as exception:
            self.module.fail_json(msg=message + ': %s' % exception)

    @staticmethod
    def _set_user_agent(clc):
        if hasattr(clc, 'SetRequestsSession'):
            agent_string = "ClcAnsibleModule/" + __version__
            ses = requests.Session()
            ses.headers.update({"Api-Client": agent_string})
            ses.headers['User-Agent'] += " " + agent_string
            clc.SetRequestsSession(ses)


def main():
    """
    The main function.  Instantiates the module and calls process_request.
    :return: none
    """
    module = AnsibleModule(
        argument_spec=ClcPublicIp._define_module_argument_spec(),
        supports_check_mode=True
    )
    clc_public_ip = ClcPublicIp(module)
    clc_public_ip.process_request()

from ansible.module_utils.basic import *  # pylint: disable=W0614
if __name__ == '__main__':
    main()
