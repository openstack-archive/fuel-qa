from nailgun.settings import NailgunSettings
from nailgun.objects.release import Release
from nailgun import consts
from nailgun.orchestrator import tasks_templates

settings = NailgunSettings()
master_ip = settings.config['MASTER_IP']

import six


release_id = 2

release = Release.get_by_uid(release_id)

packages_str = \
    release.attributes_metadata['editable']['provision']['packages']['value']
packages = list(
    six.moves.filter(bool, (s.strip() for s in packages_str.split('\n'))))
task = tasks_templates.make_provisioning_images_task(
    [consts.MASTER_NODE_UID],
    release.attributes_metadata['editable']['repo_setup']['repos']['value'],
    release.attributes_metadata['generated']['provision'],
    'prepare_release_ubuntu',
    packages)

release_str = 'release_{release_id}'.format(release_id=release_id)
with open('build_image.sh', 'w') as cmd_file:
    cmd_file.write(task['parameters']['cmd'].replace(
        "{cluster.release.environment_version}",
        release.environment_version).replace(
        '{cluster.release.version}',
        release.version).replace(
        '{settings.MASTER_IP}',
        master_ip).replace(  # any clean way?
        "{cluster.id}",
        release_str))
