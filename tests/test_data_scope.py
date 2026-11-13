"""2989 acceptance tests.

A1: scoped_select visibility — self=3, site=6, org=12 (seed: 1 org/2 sites/2 emp/3 rec)
A2: check_object_scope single-record 404 semantics (out-of-scope -> 404, never 403;
    missing record -> same 404 body, indistinguishable)
A3: write rules — CREATE defaults site_id; PATCH keeps site (never relocates);
    self cannot reassign owner_id (403); org may; unknown payload key -> 400
A4: list total scoped; export endpoint reuses scoped_select (same counts)
A5: startup config error when model lacks site_id / owner field
A6: collaborator table grants visibility (list AND single-record paths)
"""
import pytest
from sqlalchemy.orm import Session

from app.data_scope import ConfigError, check_object_scope, scoped_select
from app.models import ProbeRecord
from tests.conftest import ORG, SITE_A, SITE_B, U_A1, U_A2, U_B1, make_ctx


def _ids(db, ctx):
    return {r.id for r in db.scalars(scoped_select(ProbeRecord, ctx)).all()}


# ---------- A1: list visibility ----------

def test_self_scope_sees_only_own_3(seed):
    with Session(seed) as db:
        assert len(_ids(db, make_ctx(U_A1, SITE_A, 'self'))) == 3


def test_site_scope_sees_6(seed):
    with Session(seed) as db:
        assert len(_ids(db, make_ctx(U_A1, SITE_A, 'site'))) == 6


def test_org_scope_sees_12(seed):
    with Session(seed) as db:
        assert len(_ids(db, make_ctx(U_A1, SITE_A, 'org'))) == 12


def test_org_scope_does_not_cross_tenant(seed):
    with Session(seed) as db:
        foreign = ProbeRecord(id='rec_foreign', org_id='org_other（虚构）', site_id=SITE_A,
                              owner_id=U_A1, title='foreign')
        db.add(foreign)
        db.commit()
        ids = _ids(db, make_ctx(U_A1, SITE_A, 'org'))
        assert 'rec_foreign' not in ids, 'org scope must stay inside tenant'


def test_site_scope_excludes_other_site(seed):
    with Session(seed) as db:
        a = _ids(db, make_ctx(U_A1, SITE_A, 'site'))
        b = _ids(db, make_ctx(U_B1, SITE_B, 'site'))
        assert a and b and not (a & b), 'site scopes must not overlap'


# ---------- A2: 404 semantics (single record) ----------

def test_out_of_scope_object_reads_as_404(seed):
    with Session(seed) as db:
        other_site_row = db.query(ProbeRecord).filter(
            ProbeRecord.site_id == SITE_B).first()
        ctx_self = make_ctx(U_A1, SITE_A, 'self')
        assert not check_object_scope(other_site_row, ctx_self)


def test_probe_patch_out_of_scope_returns_404(client, seed):
    with Session(seed) as db:
        b_row = db.query(ProbeRecord).filter(ProbeRecord.site_id == SITE_B).first()
        rid = b_row.id
    from app.permissions import Ctx
    client.app.state.auth_state = Ctx(org_id=ORG, user_id=U_A1, site_id=SITE_A, scope='self')
    r = client.patch(f'/__probe__/crm.customer.read/records/{rid}', json={'title': 'x'})
    assert r.status_code == 404, r.text
    assert r.json()['detail']['error'] == 'not_found'


def test_missing_and_out_of_scope_indistinguishable(client, seed):
    from app.permissions import Ctx
    client.app.state.auth_state = Ctx(org_id=ORG, user_id=U_A1, site_id=SITE_A, scope='self')
    r_missing = client.patch('/__probe__/crm.customer.read/records/no-such-id',
                             json={'title': 'x'})
    with Session(seed) as db:
        b_row = db.query(ProbeRecord).filter(ProbeRecord.site_id == SITE_B).first()
    r_oos = client.patch(f'/__probe__/crm.customer.read/records/{b_row.id}',
                         json={'title': 'x'})
    assert r_missing.status_code == r_oos.status_code == 404
    assert r_missing.json() == r_oos.json(), 'existence must not leak via body'


def test_in_scope_patch_ok(client, seed):
    from app.permissions import Ctx
    client.app.state.auth_state = Ctx(org_id=ORG, user_id=U_A1, site_id=SITE_A, scope='self')
    with Session(seed) as db:
        own = db.query(ProbeRecord).filter(ProbeRecord.owner_id == U_A1).first()
        rid = own.id
    r = client.patch(f'/__probe__/crm.customer.read/records/{rid}', json={'title': 'upd-1'})
    assert r.status_code == 200
    assert r.json()['title'] == 'upd-1'


def test_site_scope_patch_out_of_site_returns_404(client, seed):
    """Site-scope user PATCHes another site's record: 404 (object site-check)."""
    from app.permissions import Ctx
    client.app.state.auth_state = Ctx(org_id=ORG, user_id=U_A1, site_id=SITE_A, scope='site')
    with Session(seed) as db:
        b_row = db.query(ProbeRecord).filter(ProbeRecord.site_id == SITE_B).first()
        rid = b_row.id
    r = client.patch(f'/__probe__/crm.site.report.read/records/{rid}', json={'title': 'x'})
    assert r.status_code == 404, r.text
    assert r.json()['detail']['error'] == 'not_found'


def test_site_scope_patch_in_site_ok(client, seed):
    from app.permissions import Ctx
    client.app.state.auth_state = Ctx(org_id=ORG, user_id=U_A1, site_id=SITE_A, scope='site')
    with Session(seed) as db:
        row = db.query(ProbeRecord).filter(ProbeRecord.site_id == SITE_A,
                                           ProbeRecord.owner_id == U_A2).first()
        rid = row.id
    r = client.patch(f'/__probe__/crm.site.report.read/records/{rid}', json={'title': 'ok'})
    assert r.status_code == 200
    assert r.json()['title'] == 'ok'


# ---------- A3: write rules ----------

def test_patch_absent_site_id_keeps_record_site(client, seed):
    """PATCH must never relocate: absent site_id -> record stays where it was."""
    from app.permissions import Ctx
    client.app.state.auth_state = Ctx(org_id=ORG, user_id=U_A1, site_id=SITE_A, scope='org')
    with Session(seed) as db:
        row = db.query(ProbeRecord).filter(ProbeRecord.site_id == SITE_B,
                                           ProbeRecord.owner_id == U_B1).first()
        rid = row.id
    r = client.patch(f'/__probe__/kb.article.read/records/{rid}', json={'title': 'typo fixed'})
    assert r.status_code == 200
    assert r.json()['site_id'] == SITE_B, 'PATCH must not move record to operator site'
    # verify persisted
    with Session(seed) as db:
        assert db.get(ProbeRecord, rid).site_id == SITE_B


def test_patch_explicit_site_change_forbidden_for_site_scope(client, seed):
    from app.permissions import Ctx
    client.app.state.auth_state = Ctx(org_id=ORG, user_id=U_A1, site_id=SITE_A, scope='site')
    with Session(seed) as db:
        row = db.query(ProbeRecord).filter(ProbeRecord.site_id == SITE_A).first()
        rid = row.id
    r = client.patch(f'/__probe__/crm.site.report.read/records/{rid}',
                     json={'site_id': SITE_B})
    assert r.status_code == 403


def test_patch_explicit_site_change_allowed_for_org(client, seed):
    from app.permissions import Ctx
    client.app.state.auth_state = Ctx(org_id=ORG, user_id=U_A1, site_id=SITE_A, scope='org')
    with Session(seed) as db:
        row = db.query(ProbeRecord).filter(ProbeRecord.site_id == SITE_A).first()
        rid = row.id
    r = client.patch(f'/__probe__/kb.article.read/records/{rid}',
                     json={'site_id': SITE_B})
    assert r.status_code == 200
    assert r.json()['site_id'] == SITE_B


def test_create_defaults_site_to_current(seed):
    """CREATE path: apply_create_defaults fills site_id with ctx site."""
    from app.data_scope import apply_create_defaults
    row = ProbeRecord(id='rec_new', org_id=ORG, site_id=None, owner_id=U_A1, title='new')
    ctx = make_ctx(U_A1, SITE_A, 'self')
    apply_create_defaults(row, ctx)
    assert row.site_id == SITE_A


def test_self_scope_cannot_reassign_owner(client, seed):
    from app.permissions import Ctx
    client.app.state.auth_state = Ctx(org_id=ORG, user_id=U_A1, site_id=SITE_A, scope='self')
    with Session(seed) as db:
        own = db.query(ProbeRecord).filter(ProbeRecord.owner_id == U_A1).first()
        rid = own.id
    r = client.patch(f'/__probe__/crm.customer.read/records/{rid}',
                     json={'owner_id': U_A2})
    assert r.status_code == 403
    assert r.json()['detail']['error'] == 'permission_denied'


def test_org_scope_may_reassign_owner(client, seed):
    """Org-scope admins reassign per role matrix (spec: rule binds self-scope only)."""
    from app.permissions import Ctx
    client.app.state.auth_state = Ctx(org_id=ORG, user_id=U_A1, site_id=SITE_A, scope='org')
    with Session(seed) as db:
        row = db.query(ProbeRecord).filter(ProbeRecord.owner_id == U_B1).first()
        rid = row.id
    r = client.patch(f'/__probe__/kb.article.read/records/{rid}',
                     json={'owner_id': U_A2})
    assert r.status_code == 200
    assert r.json()['owner_id'] == U_A2


def test_unknown_payload_key_400(client, seed):
    from app.permissions import Ctx
    client.app.state.auth_state = Ctx(org_id=ORG, user_id=U_A1, site_id=SITE_A, scope='self')
    with Session(seed) as db:
        own = db.query(ProbeRecord).filter(ProbeRecord.owner_id == U_A1).first()
        rid = own.id
    r = client.patch(f'/__probe__/crm.customer.read/records/{rid}',
                     json={'secret_field': 'value'})
    assert r.status_code == 400
    assert r.json()['detail']['error'] == 'invalid_payload'


# ---------- A4: total scoped + export same filter ----------

def test_probe_list_total_scoped(client, seed):
    """Each scope via its own probe permission code (matrix-bound)."""
    from app.permissions import Ctx
    for code, expected in (('crm.customer.read', 3),
                           ('crm.site.report.read', 6),
                           ('kb.article.read', 12)):
        client.app.state.auth_state = Ctx(org_id=ORG, user_id=U_A1, site_id=SITE_A,
                                          scope='self')
        r = client.get(f'/__probe__/{code}/records')
        assert r.status_code == 200
        body = r.json()
        assert body['total'] == expected, f'{code}: {body["total"]} != {expected}'


def test_export_reuses_scoped_select(client, seed):
    """Export endpoint must produce the SAME visibility as the list."""
    from app.permissions import Ctx
    for code, expected in (('crm.customer.read', 3),
                           ('crm.site.report.read', 6),
                           ('kb.article.read', 12)):
        client.app.state.auth_state = Ctx(org_id=ORG, user_id=U_A1, site_id=SITE_A,
                                          scope='self')
        r = client.get(f'/__probe__/{code}/export')
        assert r.status_code == 200
        body = r.json()
        assert body['exported'] == expected, f'{code}: exported {body["exported"]} != {expected}'


# ---------- A5: startup config error ----------

def test_missing_site_column_raises_config_error_at_startup():
    from sqlalchemy import Column, String, create_engine
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

    from app.data_scope import validate_models

    class B2(DeclarativeBase):
        pass

    class Bad(B2):
        __tablename__ = 'bad_startup_model'
        id: Mapped[str] = mapped_column(String(36), primary_key=True)
        org_id: Mapped[str] = mapped_column(String(36))
        owner_id: Mapped[str] = mapped_column(String(36))

    eng = create_engine('sqlite://')
    B2.metadata.create_all(eng)
    with pytest.raises(ConfigError):
        validate_models(B2.registry)


def test_missing_owner_column_raises_config_error_at_startup():
    from sqlalchemy import String, create_engine
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

    from app.data_scope import validate_models

    class B3(DeclarativeBase):
        pass

    class Bad2(B3):
        __tablename__ = 'bad_startup_model2'
        id: Mapped[str] = mapped_column(String(36), primary_key=True)
        org_id: Mapped[str] = mapped_column(String(36))
        site_id: Mapped[str] = mapped_column(String(36))

    eng = create_engine('sqlite://')
    B3.metadata.create_all(eng)
    with pytest.raises(ConfigError):
        validate_models(B3.registry)


def test_create_app_raises_config_error_on_bad_registry():
    """Acceptance 5 end-to-end: create_app fails at startup when the shared registry
    contains a bad model. Uses patch of the registry iteration to inject a bad mapper
    without registering into the shared Base (no cross-test pollution)."""
    from unittest.mock import patch as mock_patch

    from sqlalchemy import String, create_engine
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

    from app import models as app_models
    from app.main import create_app

    class B4(DeclarativeBase):
        pass

    class BadCreate(B4):
        __tablename__ = 'bad_isolated_model'
        id: Mapped[str] = mapped_column(String(36), primary_key=True)
        org_id: Mapped[str] = mapped_column(String(36))

    eng = create_engine('sqlite://')
    B4.metadata.create_all(eng)

    real_mappers = list(app_models.Base.registry.mappers)
    bad_mappers = list(B4.registry.mappers)  # snapshot BEFORE patching
    RegistryCls = type(app_models.Base.registry)

    with mock_patch.object(RegistryCls, 'mappers',
                           property(lambda self: real_mappers + bad_mappers)):
        with pytest.raises(ConfigError):
            create_app(eng)


# ---------- A6: collaborator visibility (list + single record) ----------

def test_collaborator_visibility_single_record():
    """__collaborator_table__ on the MODEL CLASS grants collaborator access (self scope)."""
    from app.data_scope import check_object_scope
    from app.models import ProbeRecord

    ProbeRecord.__collaborator_table__ = {'rec_c1': U_A2}
    try:
        row = ProbeRecord(id='rec_c1', org_id=ORG, site_id=SITE_A, owner_id=U_B1,
                          title='collab')
        ctx_u_a2_self = make_ctx(U_A2, SITE_A, 'self')
        ctx_stranger = make_ctx(U_A1, SITE_A, 'self')
        assert check_object_scope(row, ctx_u_a2_self), 'collaborator must see the record'
        assert not check_object_scope(row, ctx_stranger), 'non-collaborator must not'
    finally:
        del ProbeRecord.__collaborator_table__


def test_collaborator_visibility_in_list(seed):
    """Collaborator record must APPEAR in the list result, stranger's must not."""
    from app.models import ProbeRecord

    with Session(seed) as db:
        db.add(ProbeRecord(id='rec_c1', org_id=ORG, site_id=SITE_A, owner_id=U_B1,
                           title='collab'))
        db.commit()
        ProbeRecord.__collaborator_table__ = {'rec_c1': U_A2}
        try:
            ids = _ids(db, make_ctx(U_A2, SITE_A, 'self'))
            # U_A2 owns 3 + collaborates on rec_c1
            assert 'rec_c1' in ids, 'collaborator record must appear in list'
            assert len(ids) == 4, f'self(own 3) + collab(1) = 4, got {len(ids)}'
            # stranger U_A1 does not collaborate: still exactly own 3
            ids_stranger = _ids(db, make_ctx(U_A1, SITE_A, 'self'))
            assert 'rec_c1' not in ids_stranger
            assert len(ids_stranger) == 3
        finally:
            del ProbeRecord.__collaborator_table__
