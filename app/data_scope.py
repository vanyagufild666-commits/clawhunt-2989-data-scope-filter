"""Data scope: convert require_permission's data_scope into SQLAlchemy query conditions.

Contract (task 2989 / S2-IAM):
- scopes: self / site / org
- self: __owner_field__ (default owner_id) == ctx.user_id; optional __collaborator_table__
  (stub dict {record_id: user_id}) grants visibility to collaborators
- site: model.site_id == ctx.site_id
- org: only tenant (org_id) filter — all sites in the group
- check_object_scope: same logic per-record; False -> respond 404 (not 403) to
  avoid existence disclosure
- write rules:
  * CREATE: site_id defaults to the current site when absent
  * UPDATE (PATCH): absent site_id left untouched; explicit site_id change of
    another site requires org scope (self/site -> 403)
  * self-scope employee cannot reassign owner_id to someone else (403)
  * payload keys outside the whitelist -> 400 (never silently dropped)
- models missing site_id / owner field -> ConfigError raised at app startup
  (validate_models over the registry), not at first query
"""
from sqlalchemy import select

from .errors import ConfigError

WRITE_FIELDS = ('title', 'owner_id', 'site_id')


def _owner_field(model) -> str:
    return getattr(model, '__owner_field__', 'owner_id')


def _collab_map(model):
    """Collaborator stub: dict {record_id: user_id} (real table = S2-CRM dependency)."""
    return getattr(model, '__collaborator_table__', None)


def validate_models(registry) -> None:
    """Startup check: every mapped model must declare org_id/site_id/owner field.

    Models starting with '_' or listed in SKIP are exempt (internal).
    """
    for mapper in registry.mappers:
        model = mapper.class_
        if getattr(model, '__scope_exempt__', False):
            continue
        _validate_model(model)


def _validate_model(model):
    cols = set(model.__table__.columns.keys())
    missing = [c for c in ('org_id', 'site_id', _owner_field(model)) if c not in cols]
    if missing:
        raise ConfigError(
            f'{model.__name__} missing required scope columns: {", ".join(missing)}')


def scoped_conditions(model, ctx):
    """WHERE-conditions for `model` rows visible under ctx (org filter always applied)."""
    _validate_model(model)
    conds = [model.org_id == ctx.org_id]
    if ctx.scope == 'self':
        owner_cond = getattr(model, _owner_field(model)) == ctx.user_id
        collab = _collab_map(model)
        if collab:
            extra_ids = [rid for rid, uid in collab.items() if uid == ctx.user_id]
            conds.append(owner_cond | model.id.in_(extra_ids))
        else:
            conds.append(owner_cond)
    elif ctx.scope == 'site':
        conds.append(model.site_id == ctx.site_id)
    elif ctx.scope == 'org':
        pass  # org-wide: no extra filter beyond tenant
    else:
        raise ConfigError(f'unknown scope {ctx.scope!r}')
    return conds


def scoped_select(model, ctx):
    """SELECT over `model` filtered by ctx's data scope (acceptance 1 API)."""
    return select(model).where(*scoped_conditions(model, ctx))


def check_object_scope(obj, ctx) -> bool:
    """Single-record visibility under ctx. False -> respond 404 (never 403)."""
    model = type(obj)
    if obj.org_id != ctx.org_id:
        return False
    if ctx.scope == 'self':
        if getattr(obj, _owner_field(model)) == ctx.user_id:
            return True
        collab = _collab_map(model)
        if collab:
            return collab.get(obj.id) == ctx.user_id
        return False
    if ctx.scope == 'site':
        return obj.site_id == ctx.site_id
    if ctx.scope == 'org':
        return True
    raise ConfigError(f'unknown scope {ctx.scope!r}')


def apply_create_defaults(obj, ctx):
    """CREATE-time: site_id defaults to the current site when absent."""
    if getattr(obj, 'site_id', None) in (None, ''):
        obj.site_id = ctx.site_id
    return obj


def apply_write_rules(obj, ctx, payload: dict):
    """UPDATE-time rules. Returns (obj, error_status) — error_status None or 400/403.

    - unknown payload keys -> 400 (never silently dropped)
    - absent site_id: record keeps its site (PATCH never relocates)
    - explicit site_id change to another site: self/site scope -> 403, org -> allowed
    - self scope cannot reassign owner_id at all -> 403
    """
    model = type(obj)
    unknown = set(payload) - set(WRITE_FIELDS)
    if unknown:
        return obj, 400

    if 'site_id' in payload and payload['site_id'] != obj.site_id:
        if ctx.scope in ('self', 'site'):
            return obj, 403
        obj.site_id = payload['site_id']  # org-scope relocation is explicit

    owner_field = _owner_field(model)
    if 'owner_id' in payload and payload['owner_id'] != getattr(obj, owner_field):
        if ctx.scope == 'self':
            return obj, 403
        setattr(obj, owner_field, payload['owner_id'])

    if 'title' in payload:
        obj.title = payload['title']
    return obj, None
