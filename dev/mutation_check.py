"""Mutation verification for 2989 v2 (post-review): kill each defense, expect failures."""
import os
import re
import subprocess

D = r'clawhunt/pipeline/tasks/2989'


def run_tests():
    env = dict(os.environ, APP_ENV='test', PYTHONDONTWRITEBYTECODE='1')
    r = subprocess.run([os.sys.executable, '-m', 'pytest', 'tests/', '-q', '--no-header'],
                       cwd=D, capture_output=True, text=True, env=env)
    out = r.stdout + r.stderr
    f = re.search(r'(\d+) failed', out)
    p = re.search(r'(\d+) passed', out)
    if not f and not p:
        return None, out.strip().splitlines()[-3:]
    return (int(f.group(1)) if f else 0), None


def mutated(rel, old, new, desc):
    p = os.path.join(D, rel)
    orig = open(p, encoding='utf-8').read()
    if old not in orig:
        print('ERR not found in', rel, ':', old[:60])
        return False
    try:
        open(p, 'w', encoding='utf-8', newline='\n').write(orig.replace(old, new))
        failed, err = run_tests()
        if err:
            print('ERR', desc, err)
            return False
        if failed > 0:
            print(f'MUTATED ok: {desc} -> {failed} failed (caught)')
            return True
        print(f'MUTATION SURVIVED: {desc} -> 0 failed (fake positive!)')
        return False
    finally:
        open(p, 'w', encoding='utf-8', newline='\n').write(orig)


failed, err = run_tests()
if err or failed:
    print('BASELINE ERROR:', failed, err)
    raise SystemExit(1)
print('== baseline: 0 failed ==')

results = [
    # A1: self filter disabled (falls through to org behavior)
    mutated('app/data_scope.py',
            "conds = [model.org_id == ctx.org_id]\n    if ctx.scope == 'self':",
            "conds = [model.org_id == ctx.org_id]\n    if False and ctx.scope == 'self':",
            'self filter disabled'),
    # A1: site filter disabled
    mutated('app/data_scope.py',
            "elif ctx.scope == 'site':\n        conds.append(model.site_id == ctx.site_id)",
            "elif ctx.scope == 'site':\n        pass",
            'site filter disabled'),
    # tenant filter disabled
    mutated('app/data_scope.py',
            'conds = [model.org_id == ctx.org_id]',
            'conds = []',
            'tenant (org_id) filter disabled'),
    # A2: object scope site-check disabled (404 semantics)
    mutated('app/data_scope.py',
            "if ctx.scope == 'site':\n        return obj.site_id == ctx.site_id",
            "if ctx.scope == 'site':\n        return True",
            'object scope site-check disabled'),
    # A2: object scope self-check disabled (owner part)
    mutated('app/data_scope.py',
            "if getattr(obj, _owner_field(model)) == ctx.user_id:\n            return True",
            "if False:\n            return True",
            'object scope self owner-check disabled'),
    # A3: PATCH relocation guard disabled (site change for site/self scope)
    mutated('app/data_scope.py',
            "if 'site_id' in payload and payload['site_id'] != obj.site_id:\n        if ctx.scope in ('self', 'site'):\n            return obj, 403",
            "if False:\n        if ctx.scope in ('self', 'site'):\n            return obj, 403",
            'PATCH explicit-site guard disabled'),
    # A3: owner-reassign guard disabled
    mutated('app/data_scope.py',
            "if 'owner_id' in payload and payload['owner_id'] != getattr(obj, owner_field):\n        if ctx.scope == 'self':\n            return obj, 403",
            "if False:\n        if ctx.scope == 'self':\n            return obj, 403",
            'self-scope owner-reassign guard disabled'),
    # A3: unknown payload key 400 disabled (silent drop returns)
    mutated('app/data_scope.py',
            "unknown = set(payload) - set(WRITE_FIELDS)\n    if unknown:\n        return obj, 400",
            "unknown = set() - set(WRITE_FIELDS)\n    if unknown:\n        return obj, 400",
            'unknown-key 400 disabled (silent drop)'),
    # A5: startup validation disabled
    mutated('app/data_scope.py',
            "    if missing:\n        raise ConfigError(",
            "    if False and missing:\n        raise ConfigError(",
            'startup config validation disabled'),
    # A5: create_app skips validate_models
    mutated('app/main.py',
            'validate_models(Base.registry)',
            'None',
            'create_app skips startup validation'),
    # A6: collaborator visibility disabled (check_object_scope)
    mutated('app/data_scope.py',
            'if collab:\n            return collab.get(obj.id) == ctx.user_id',
            'if False:\n            return collab.get(obj.id) == ctx.user_id',
            'collaborator visibility disabled (single record)'),
    # A6: collaborator list extension disabled
    mutated('app/data_scope.py',
            'if collab:\n            extra_ids = [rid for rid, uid in collab.items() if uid == ctx.user_id]\n            conds.append(owner_cond | model.id.in_(extra_ids))',
            'if False:\n            extra_ids = []\n            conds.append(owner_cond)',
            'collaborator list extension disabled'),
    # CREATE defaulting disabled
    mutated('app/data_scope.py',
            "if getattr(obj, 'site_id', None) in (None, ''):\n        obj.site_id = ctx.site_id",
            "if False:\n        obj.site_id = ctx.site_id",
            'CREATE site_id defaulting disabled'),
]

ok = all(results)
print('ALL MUTATIONS CAUGHT' if ok else 'SOME MUTATIONS SURVIVED')
