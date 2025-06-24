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

# ✅ DEBUG: Verificar que las credenciales se cargaron
print(f"Account SID: {account_sid}")
print(f"Auth Token: {'*' * len(auth_token) if auth_token else 'NOT LOADED'}")
print(f"Twilio Number: {twilio_number}")
print(f"Destination: {destination_number}")

# Verificar que todas las variables están presentes
if not all([account_sid, auth_token, twilio_number, destination_number]):
    print("❌ ERROR: Faltan variables de entorno")
    exit(1)

# URL del endpoint
twiml_url = 'https://aivoicetwilio-vf.onrender.com/voice-twiml'

try:
    # Crear un cliente de Twilio
    client = Client(account_sid, auth_token)
    
    # Hacer la llamada
    call = client.calls.create(
        url=twiml_url,
        to=destination_number,
        from_=twilio_number
    )
    
    print(f"✅ Llamada iniciada con SID: {call.sid}")
    
except Exception as e:
    print(f"❌ Error al crear la llamada: {e}")