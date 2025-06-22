"""
check_call_full.py
Muestra TODA la info disponible de una llamada:
- Detalles básicos
- Eventos (Voice Insights)
- Notificaciones (webhooks, errores, etc.)
- Grabaciones
- Child calls (legs)
"""

import os
from pprint import pprint
from dotenv import load_dotenv
from twilio.rest import Client

# ────────────────────────────────
# 1) Credenciales y SID de llamada
# ────────────────────────────────
load_dotenv()
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token  = os.getenv("TWILIO_AUTH_TOKEN")
CALL_SID    = "CA64cb76ac39a0b2e850cdac09b34d9636"   # ← cambia por el tuyo

client = Client(account_sid, auth_token)


def dump(title: str, iterable):
    """Imprime cada recurso con todos sus atributos."""
    print(f"\n▶️  {title}")
    if not iterable:
        print("   (sin resultados)")
        return
    for item in iterable:
        props = getattr(item, "_properties", item.__dict__.get("_properties", {}))
        # Si aún así está vacío, recurre a vars() para versiones viejas
        if not props:
            props = {k: v for k, v in vars(item).items() if not k.startswith("_")}
        pprint(props, sort_dicts=False)
        print("-" * 60)


# ─────────── Detalles básicos ───────────
call = client.calls(CALL_SID).fetch()
dump("Detalles de la llamada", [call])

# ─────────── Eventos (Voice Insights) ───────────
events = client.calls(CALL_SID).events.list(limit=100)
dump("Eventos de la llamada (Voice Insights)", events)
print("ℹ️  Si ves la lista vacía, activa Voice Insights Advanced en tu cuenta.")

# ─────────── Notificaciones (request / response logs) ───────────
notes = client.calls(CALL_SID).notifications.list(limit=50)
dump("Notificaciones (webhooks, errores, etc.)", notes)

# ─────────── Grabaciones ───────────
recs = client.calls(CALL_SID).recordings.list(limit=20)
dump("Grabaciones asociadas", recs)

# ─────────── Child calls (leg A / leg B) ───────────
children = client.calls.list(parent_call_sid=CALL_SID)
dump("Sub-llamadas / child calls", children)
