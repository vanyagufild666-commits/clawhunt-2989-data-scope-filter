"""Fixtures: 1 org, 2 sites, 2 employees per site, 3 records per employee.

Acceptance visibility: self=3, site=6, org=12.
"""
import os

os.environ.setdefault('APP_ENV', 'test')

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.main import create_app
from app.models import Base, Org, ProbeRecord, Site, User, new_uuid
from app.permissions import Ctx

ORG = 'org_test'
SITE_A = 'site_A'
SITE_B = 'site_B'
U_A1 = 'user_a1'
U_A2 = 'user_a2'
U_B1 = 'user_b1'
U_B2 = 'user_b2'


@pytest.fixture()
def engine():
    eng = create_engine('sqlite:///./test_2989.db', connect_args={'check_same_thread': False})
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()
    if os.path.exists('./test_2989.db'):
        os.remove('./test_2989.db')


@pytest.fixture()
def seed(engine):
    from sqlalchemy.orm import Session
    with Session(engine) as s:
        s.add(Org(id=ORG, name='（虚构）测试集团'))
        for sid, nm in ((SITE_A, '会所A'), (SITE_B, '会所B')):
            s.add(Site(id=sid, org_id=ORG, name=nm))
        for uid, nm in ((U_A1, '员工A1'), (U_A2, '员工A2'), (U_B1, '员工B1'), (U_B2, '员工B2')):
            s.add(User(id=uid, org_id=ORG, name=nm))
        n = 0
        for site, users in ((SITE_A, (U_A1, U_A2)), (SITE_B, (U_B1, U_B2))):
            for u in users:
                for i in range(3):
                    n += 1
                    s.add(ProbeRecord(org_id=ORG, site_id=site, owner_id=u,
                                      title=f'rec-{site}-{u}-{i}'))
        s.commit()
    return engine


def make_ctx(user, site, scope):
    return Ctx(org_id=ORG, user_id=user, site_id=site, scope=scope)


@pytest.fixture()
def client(seed):
    from sqlalchemy.orm import Session
    from app.main import create_app

    with Session(seed) as s:
        pass  # tables seeded
    app = create_app(seed, auth_state=None)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db(engine):
    from sqlalchemy.orm import Session
    with Session(engine) as s:
        yield s
