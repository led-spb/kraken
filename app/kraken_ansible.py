import logging
from ansible.executor import playbook_executor
from ansible.inventory.manager import InventoryManager
from ansible.parsing.dataloader import DataLoader
from ansible.vars.manager import VariableManager
from ansible.utils.display import Display
from ansible import constants as C
from ansible.plugins.callback import CallbackBase

display = Display()
VERBOSITY = {
    'critical': logging.CRITICAL,
    'error': logging.ERROR,
    'warn': logging.WARN,
    'info': logging.INFO,
    'debug': logging.DEBUG
}


class JsonResultCallback(CallbackBase):
    def __init__(self, display=None):
        super(JsonResultCallback, self).__init__(display)
        self.results = []

    def _new_play(self, play):
        return {
            'play': {
                'name': play.name,
                'id': str(play._uuid)
            },
            'tasks': []
        }

    def _new_task(self, task):
        return {
            'task': {
                'name': task.name,
                'id': str(task._uuid)
            },
            'hosts': {}
        }

    def v2_playbook_on_play_start(self, play):
        self.results.append(self._new_play(play))

    def v2_playbook_on_task_start(self, task, is_conditional):
        self.results[-1]['tasks'].append(self._new_task(task))

    def v2_playbook_on_handler_task_start(self, task):
        self.results[-1]['tasks'].append(self._new_task(task))

    def v2_runner_on_ok(self, result, **kwargs):
        host = result._host
        self.results[-1]['tasks'][-1]['hosts'][host.name] = result._result

    def v2_playbook_on_stats(self, stats):
        hosts = sorted(stats.processed.keys())
        self.summary = {}
        for h in hosts:
            s = stats.summarize(h)
            self.summary[h] = s
        pass

    v2_runner_on_failed = v2_runner_on_ok
    v2_runner_on_unreachable = v2_runner_on_ok
    v2_runner_on_skipped = v2_runner_on_ok


class AnsibleRunner(object):
    """Run ansible playbook and retrieve results"""

    def __init__(self, hosts, playbook, verbosity='info', config={},
                 vars_filename='.variables', vault_password=""):
        required_defaults = (
            'forks',
            'remote_user',
            'private_key_file',
            'become',
            'become_method',
            'become_user'
        )
        for default in required_defaults:
            if default not in config:
                config[default] = getattr(
                    C, 'DEFAULT_{}'.format(default.upper())
                )
        config['connection'] = config.get('connection', 'smart')
        config['ssh_common_args'] = config.get('ssh_common_args', None)
        config['ssh_extra_args'] = config.get('ssh_extra_args', None)
        config['sftp_extra_args'] = config.get('sftp_extra_args', None)
        config['scp_extra_args'] = config.get('scp_extra_args', None)
        config['extra_vars'] = config.get('extra_vars', {})
        config['diff'] = config.get('diff', False)
        config['listhosts'] = config.get('listhosts', False)
        config['listtasks'] = config.get('listtasks', False)
        config['listtags'] = config.get('listtags', False)
        config['syntax'] = config.get('syntax', False)
        config['verbosity'] = VERBOSITY.get(verbosity)
        config['module_path'] = './'
        config['check'] = False

        self.options = options_as_class(config)

        # create default data loader
        self.loader = DataLoader()
        # self.loader.set_vault_password(vault_password)
        variables = {}
        try:
            variables = self.loader.load_from_file(vars_filename)
        except Exception:
            pass

        # loading inventory
        self.inventory = InventoryManager(
            loader=self.loader,
            sources=None
        )
        for group in hosts.keys():
            self.inventory.add_group(group)
            for host in hosts[group]:
                self.inventory.add_host(host=host, group=group)

        # create variable manager
        self.vm = VariableManager(
            loader=self.loader,
            inventory=self.inventory
        )
        self.vm.extra_vars = variables

        # create a playbook executor
        self.pbex = playbook_executor.PlaybookExecutor(
            playbooks=[playbook],
            inventory=self.inventory,
            variable_manager=self.vm,
            loader=self.loader,
            options=self.options,
            passwords={}
        )

        self.result_callback = JsonResultCallback()
        # self.result_callback.set_options(self.options)
        self.pbex._tqm._callback_plugins.append(self.result_callback)
        pass

    def run(self):
        self.pbex.run()
        return {
            'plays': self.result_callback.results,
            'stats': self.result_callback.summary
        }
        pass


def options_as_class(config):
    class Options(object):
        pass
    options = Options()
    for key, value in config.items():
        setattr(options, key, value)
    return options


if __name__ == "__main__":
    import json
    results = AnsibleRunner('localhost', 'test.yaml', config={
        'connection': 'local'
    }).run()
    print json.dumps(results, indent=2)
    pass
