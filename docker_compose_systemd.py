import os
import yaml

UNIT_TEMPLATE = """[Unit]
Description=Run {container_name}
{dependencies}

[Service]
Restart=always
RestartSec=10s
ExecStartPre=-/usr/bin/docker kill {container_name}
ExecStartPre=-/usr/bin/docker rm {container_name}
ExecStart=/usr/bin/docker run --rm --name "{container_name}" \\
        --label "com.docker.compose.project={project}" --label "com.docker.compose.service={service}" \\
        --label "com.docker.compose.container-number=1" \\
        {args} \\
        {image}
ExecStop=/usr/bin/docker stop {container_name}
ExecStopPost=-/usr/bin/docker rm {container_name}

[Install]
WantedBy=multi-user.target
"""

DEPENDENCY_TEMPLATE = "After={unit}\nRequires={unit}"

IMG_NAME = "{project}-{service}"
CTNR_NAME = "{project}-{service}-1"
UNIT_NAME = "{project}-{service}.docker-compose.service"


DOCKER_CONFIG_KEYS = [
    'cap_add',
    'cap_drop',
    'cpu_shares',
    'cpuset',
    'command',
    # 'detach',
    # 'devices',
    'dns',
    'dns_search',
    'domainname',
    'entrypoint',
    'env_file',
    'environment',
    'extra_hosts',
    # 'read_only',
    'hostname',
    'image',
    'label',
    'links',
    'mem_limit',
    'net',
    'log_driver',
    'pid',
    'ports',
    'privileged',
    'restart',
    # 'stdin_open',
    # 'tty',
    'user',
    'volumes',
    'volumes_from',
    'working_dir']

ALLOWED_KEYS = DOCKER_CONFIG_KEYS + [
    'build',
    'dockerfile',
    'expose',
    # 'external_links',
    # 'name',
]

KEYS_OPTION_MAP = {
    'extra_hosts': '--add-host',
    'environment': '--env'
}

def _load_yaml(filename, *args, **kwargs):
    with open(filename, 'r') as f:
        return yaml.safe_load(f, *args, **kwargs)

def _write_yaml(filename, o, *args, **kwargs):
    with open(filename, 'w') as f:
        f.write(yaml.dump(o, *args, **kwargs))


def _check_host_dependencies(project):
    for container, config in project.items():
        if any(':' in x for x in config.get('ports', [])):
            raise Exception('Container \'%s\' has explicit port bindings' % container)
        if any(':' in x for x in config.get('volumes', [])):
            raise Exception('Container \'%s\' has volume bindings' % container)

        dependencies = set()
        if 'volumes_from' in config:
            dependencies.update(config['volumes_from'])
        if 'links' in config:
            dependencies.update(x.split(':')[0] for x in config['links'])
        if 'net' in config and 'container:' in config['net']:
            dependencies.add(config['net'].split(':')[-1])

        if not dependencies <= set(project.keys()) or 'external_links' in config:
            raise Exception('Container \'%s\' depends on external containers' % container)

def _combine_project_override(project, override):
    for c in override:
        project[c] = project.get(c, {})
        for k, v in override[c].items():
            if isinstance(v, list):
                project[c][k] = project[c].get(k, []) + v
            else:
                project[c][k] = v

def _mount_volumes_at_path(project, volume_mount_path):
    for container, config in project.items():
        if 'volumes' not in config:
            continue
        for i, vol in enumerate(config['volumes']):
            if ':' in vol:
                continue
            dir_name = vol.replace('/', '$')
            mount_dir = os.path.join(volume_mount_path, dir_name)
            config['volumes'][i] = "%s:%s" % (mount_dir, vol)

def _generate_units(project_name, project):
    def convert_option_to_param(opt, value):
        param = '--' + opt.replace('_', '-')
        param = KEYS_OPTION_MAP.get(opt, param)
        return '%s "%s"' % (param, value)

    units = {}
    for service_name, config in project.items():
        outfile = UNIT_NAME.format(project=project_name, service=service_name)
        container_name = CTNR_NAME.format(project=project_name, service=service_name)
        default_image = IMG_NAME.format(project=project_name, service=service_name)

        if 'image' in config and 'build' in config:
            raise Exception('Cannot specify both \'image\' and \'build\' options')

        args = []
        image = None
        for k, v in config.items():
            if k not in ALLOWED_KEYS:
                print "Unsupported option '%s' in service '%s' definition. Ignoring" % (k, service_name)
                continue

            if k == 'image':
                image = v
            elif k == 'build':
                image = default_image

            elif isinstance(v, list):
                args += [convert_option_to_param(k, x) for x in v]
            else:
                args.append(convert_option_to_param(k, v))


        dependencies = set()
        if 'volumes_from' in config:
            dependencies.update(config['volumes_from'])
        if 'links' in config:
            dependencies.update(x.split(':')[0] for x in config['links'])
        if 'net' in config and 'container:' in config['net']:
            dependencies.add(config['net'].split(':')[-1])

        if len(dependencies) != 0:
            dependencies = [UNIT_NAME.format(project=project_name, service=dep) for dep in dependencies]
            dependencies = '\n'.join(DEPENDENCY_TEMPLATE.format(unit=dep) for dep in dependencies)
        else:
            dependencies = DEPENDENCY_TEMPLATE.format(unit='docker.service')

        units[outfile] = UNIT_TEMPLATE.format(project=project_name, service=service_name, \
                                                container_name=container_name, image=image, \
                                                args=' '.join(args), dependencies=dependencies)

    return units

if __name__ == '__main__':
    filename = "test/docker-compose.yml"
    project = _load_yaml(filename)
    project_name = 'test'
    override = {}

    _check_host_dependencies(project)
    _combine_project_override(project, override)
    _mount_volumes_at_path(project, '/srv/%s' % project_name)
    for filename, content in _generate_units(project_name, project).items():
        with open("out/" + filename, 'w') as f:
            f.write(content)

    # print yaml.dump(project, default_flow_style=False)
    # _write_yaml(filename, project, default_flow_style=False)
