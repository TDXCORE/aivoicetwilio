import os
from dotenv import load_dotenv
from twilio.rest import Client

# Cargar variables de entorno desde .env
load_dotenv()

# Credenciales de Twilio
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')

# Números de teléfono
twilio_number = os.getenv('TWILIO_PHONE_NUMBER')
destination_number = os.getenv('DESTINATION_PHONE_NUMBER')

# ✅ USAR EL ENDPOINT DE TU SERVIDOR, NO TwiML INLINE
twiml_url = 'https://aivoicetwilio-vf.onrender.com/voice-twiml'

# Crear un cliente de Twilio
client = Client(account_sid, auth_token)

# ✅ USAR URL EN LUGAR DE TwiML INLINE
call = client.calls.create(
    url=twiml_url,  # ← CAMBIO CRÍTICO
    to=destination_number,
    from_=twilio_number
)

print(f"Llamada iniciada con SID: {call.sid}")