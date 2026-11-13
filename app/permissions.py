"""Permissions stub: require_permission returns ctx with bound data_scope.

Real role matrix is S2-IAM-001/2981 scope; here a seed matrix fixes scopes per
permission code (acceptance: probe codes crm.customer.read=self,
crm.site.report.read=site, kb.article.read=org).
"""
from dataclasses import dataclass

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class Ctx:
    org_id: str
    user_id: str
    site_id: str
    scope: str  # self | site | org


# seed matrix: permission code -> data scope (platform contract alignment point)
SCOPE_MATRIX = {
    'crm.customer.read': 'self',
    'crm.site.report.read': 'site',
    'kb.article.read': 'org',
}


def scope_for(code: str) -> str:
    if code not in SCOPE_MATRIX:
        raise HTTPException(status_code=404, detail={'error': 'unknown_permission'})
    return SCOPE_MATRIX[code]


def get_ctx(request: Request, code: str | None = None) -> Ctx:
    state = getattr(request.app.state, 'auth_state', None)
    if state is None:
        raise HTTPException(status_code=401, detail={'error': 'unauthenticated'})
    ctx: Ctx = state
    if code:
        bound = scope_for(code)
        if bound != ctx.scope:
            ctx = Ctx(ctx.org_id, ctx.user_id, ctx.site_id, scope=bound)
    return ctx
