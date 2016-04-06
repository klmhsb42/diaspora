from os import environ
from os.path import isdir, join
import shutil
from subprocess import check_output

from syncloud_app import logger

from syncloud_platform.systemd.systemctl import remove_service, add_service
from syncloud_platform.tools import app
from syncloud_platform.api import storage
from syncloud_platform.tools import chown, locale
from syncloud_platform.api import info
from syncloud_platform.api import app as platform_app
from diaspora import postgres
from diaspora.config import Config
from diaspora.config import UserConfig
import yaml

SYSTEMD_NGINX_NAME = 'diaspora-nginx'
SYSTEMD_POSTGRESQL = 'diaspora-postgresql'
SYSTEMD_REDIS = 'diaspora-redis'
SYSTEMD_SIDEKIQ = 'diaspora-sidekiq'
SYSTEMD_UNICORN = 'diaspora-unicorn'


class DiasporaInstaller:
    def __init__(self):
        self.log = logger.get_logger('diaspora.installer')
        self.config = Config()

    def install(self):

        locale.fix_locale()

        self.log.info(chown.chown(self.config.app_name(), self.config.install_path()))

        app_data_dir = app.get_app_data_root(self.config.app_name(), self.config.app_name())

        if not isdir(join(app_data_dir, 'config')):
            app.create_data_dir(app_data_dir, 'config', self.config.app_name())

        if not isdir(join(app_data_dir, 'postgresql')):
            app.create_data_dir(app_data_dir, 'postgresql', self.config.app_name())

        if not isdir(join(app_data_dir, 'redis')):
            app.create_data_dir(app_data_dir, 'redis', self.config.app_name())

        if not isdir(join(app_data_dir, 'log')):
            app.create_data_dir(app_data_dir, 'log', self.config.app_name())

        if not isdir(join(app_data_dir, 'nginx')):
            app.create_data_dir(app_data_dir, 'nginx', self.config.app_name())

        print("setup systemd")

        add_service(self.config.install_path(), SYSTEMD_POSTGRESQL)

        self.update_configuraiton()

        if not UserConfig().is_installed():
            self.initialize()

        #self.recompile_assets()

        self.log.info(chown.chown(self.config.app_name(), self.config.install_path()))

        add_service(self.config.install_path(), SYSTEMD_REDIS)
        add_service(self.config.install_path(), SYSTEMD_SIDEKIQ)
        add_service(self.config.install_path(), SYSTEMD_UNICORN)
        add_service(self.config.install_path(), SYSTEMD_NGINX_NAME)

        self.prepare_storage()

        platform_app.register_app('diaspora', self.config.port())

    def remove(self):

        platform_app.unregister_app('diaspora')
        remove_service(SYSTEMD_NGINX_NAME)
        remove_service(SYSTEMD_UNICORN)
        remove_service(SYSTEMD_SIDEKIQ)
        remove_service(SYSTEMD_REDIS)
        remove_service(SYSTEMD_POSTGRESQL)

        if isdir(self.config.install_path()):
            shutil.rmtree(self.config.install_path())

    def initialize(self):

        print("initialization")
        postgres.execute("ALTER USER {0} WITH PASSWORD '{0}';".format(self.config.app_name()), database="postgres")

        self.environment()
        print(check_output(self.config.rake_db_cmd(), shell=True, cwd=self.config.diaspora_dir()))

        UserConfig().set_activated(True)

    def environment(self):
        environ['RAILS_ENV'] = self.config.rails_env()
        environ['DB'] = self.config.db()
        environ['GEM_HOME'] = self.config.gem_home()
        environ['PATH'] = self.config.path()

    def prepare_storage(self):
        storage.init(self.config.app_name(), self.config.app_name())

    def update_domain(self):
        self.update_configuraiton()
        self.recompile_assets()

    #def recompile_assets(self):
    #    self.environment()
    #    print(check_output(self.config.rake_assets(), shell=True, cwd=self.config.diaspora_dir()))

    def update_configuraiton(self):
        url = info.url('diaspora')
        config = yaml.load(open(self.config.diaspora_config()))

        config['configuration']['environment']['url'] = url
        config['configuration']['environment']['assets']['host'] = url

        yaml.dump(config, open(self.config.diaspora_config(), 'w'))
