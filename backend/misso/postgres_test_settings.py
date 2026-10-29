"""PostgreSQL tests must target a disposable local cluster, never DATABASE_URL."""
from .test_settings import *

test_url = os.environ.get('MISSO_TEST_DATABASE_URL', '')
if not test_url:
    raise RuntimeError('Set MISSO_TEST_DATABASE_URL to a disposable local PostgreSQL database.')
test_database = dj_database_url.parse(test_url)
if (test_database['ENGINE'] != 'django.db.backends.postgresql'
        or test_database.get('HOST') not in ('localhost', '127.0.0.1')
        or not test_database.get('NAME', '').startswith('misso_test_')):
    raise RuntimeError('PostgreSQL tests require localhost and a misso_test_ database name.')
DATABASES = {'default': test_database}
DATABASES['default']['TEST'] = {'TEMPLATE': 'template0', 'CHARSET': 'UTF8'}
