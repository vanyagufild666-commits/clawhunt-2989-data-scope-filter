"""2989 structure check: live files are the source of truth (no embedded copies)."""
import os

D = os.path.dirname(os.path.abspath(__file__))

EXPECTED = [
    'README.md',
    '.gitignore',
    'app/__init__.py',
    'app/models.py',
    'app/data_scope.py',
    'app/errors.py',
    'app/permissions.py',
    'app/main.py',
    'tests/__init__.py',
    'tests/conftest.py',
    'tests/test_data_scope.py',
    'migrations/0001_probe_records.sql',
]

missing = [f for f in EXPECTED if not os.path.exists(os.path.join(D, f))]
assert not missing, f'missing: {missing}'
print('structure OK:', len(EXPECTED), 'files present')
