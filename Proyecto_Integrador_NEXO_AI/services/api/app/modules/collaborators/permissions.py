"""Permission allow-list for restricted operators, legacy operators unchanged."""
import json
from fastapi import HTTPException

PERMISSIONS=frozenset({
 'orders.read','orders.write','quotes.read','quotes.write','products.read',
 'inventory.read','capacity.read',
 'dashboard.read','calendar.read','calendar.write','purchasing.read','purchasing.write',
 'notifications.read','notifications.write','reports.read','organization.read',
 'documents.read','documents.write','templates.read','ai.read','ai.write',
})

def validate_permissions(values):
    if not isinstance(values,list) or len(values)>len(PERMISSIONS) or len(set(values))!=len(values) or any(v not in PERMISSIONS for v in values):
        raise HTTPException(status_code=422,detail='Permisos desconocidos o repetidos')
    return sorted(values)

def readable_permissions(user):
    if user.role=='owner':return sorted(PERMISSIONS)
    if user.permissions_json is None:return sorted(PERMISSIONS) # legacy backwards compatibility
    try:return json.loads(user.permissions_json)
    except (TypeError,ValueError):return []

def required_for_path(path,method):
    category='read' if method=='GET' else 'write'
    prefixes=[('/api/v1/orders','orders'),('/api/v1/order','orders'),('/api/v1/voice-notes','orders'),
       ('/api/v1/quotes','quotes'),('/api/v1/products','products'),('/api/v1/materials','inventory'),
       ('/api/v1/capacity','capacity'),('/api/v1/operations','dashboard'),('/api/v1/purchasing','purchasing'),
       ('/api/v1/scheduling','calendar'),('/api/v1/notifications','notifications'),('/api/v1/reports','reports'),
       ('/api/v1/organizations/me','organization'),('/api/v1/ai','ai'),('/api/v1/documents/ocr','documents'),('/api/v1/sector-templates','templates')]
    for prefix,name in prefixes:
        if path==prefix or path.startswith(prefix+'/'):
            # routes with read-only permission: reject writes for restricted operators
            return name+'.'+category
    return None

def ensure_permission(user,permission):
    if user.role=='owner':return
    if permission not in readable_permissions(user):
        raise HTTPException(status_code=403,detail='Permiso específico requerido: '+permission)
