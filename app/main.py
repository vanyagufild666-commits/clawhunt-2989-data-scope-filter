"""App factory + probe endpoints (mounted only when APP_ENV=test).

Probes per task spec:
  GET   /__probe__/{code}/records      -> scoped list (3/6/12 visibility)
  PATCH /__probe__/{code}/records/{id} -> scoped single-record write (404 semantics)

Startup validates every mapped model (acceptance 5: config error at startup).
"""
import os

from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy.orm import Session

from .data_scope import apply_write_rules, check_object_scope, scoped_conditions, scoped_select, validate_models
from .models import Base, ProbeRecord
from .permissions import get_ctx


def create_app(engine, auth_state=None):
    # acceptance 5: fail fast at startup when a model lacks scope columns
    validate_models(Base.registry)
    app = FastAPI(title='data-scope (test slice)')
    factory = __import__('sqlalchemy.orm', fromlist=['sessionmaker']).sessionmaker(bind=engine)
    app.state.db_factory = factory
    app.state.auth_state = auth_state

    if os.environ.get('APP_ENV', '').lower() == 'test':
        _mount_probes(app)
    return app


def _mount_probes(app: FastAPI):

    def db(request: Request) -> Session:
        s = app.state.db_factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    @app.get('/__probe__/{code}/records')
    def list_records(code: str, request: Request, s: Session = Depends(db)):
        ctx = get_ctx(request, code)
        # acceptance 4: list pagination AND export share scoped_select (one filter)
        rows = s.scalars(scoped_select(ProbeRecord, ctx)).all()
        return {'total': len(rows),
                'items': [{'id': r.id, 'title': r.title, 'site_id': r.site_id,
                           'owner_id': r.owner_id} for r in rows]}

    @app.get('/__probe__/{code}/export')
    def export_records(code: str, request: Request, s: Session = Depends(db)):
        """Export reuses the same scoped filter (acceptance 4)."""
        ctx = get_ctx(request, code)
        rows = s.scalars(scoped_select(ProbeRecord, ctx)).all()
        return {'exported': len(rows),
                'rows': [{'id': r.id, 'site_id': r.site_id, 'owner_id': r.owner_id}
                         for r in rows]}

    @app.patch('/__probe__/{code}/records/{rid}')
    def patch_record(code: str, rid: str, request: Request,
                     payload: dict, s: Session = Depends(db)):
        ctx = get_ctx(request, code)
        obj = s.get(ProbeRecord, rid)
        # 404 semantics: missing OR out-of-scope must be indistinguishable
        if obj is None or not check_object_scope(obj, ctx):
            raise HTTPException(status_code=404, detail={'error': 'not_found'})
        obj, deny = apply_write_rules(obj, ctx, payload)
        if deny:
            raise HTTPException(status_code=deny,
                                detail={'error': 'permission_denied' if deny == 403
                                        else 'invalid_payload'})
        return {'id': obj.id, 'title': obj.title, 'owner_id': obj.owner_id,
                'site_id': obj.site_id}
