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

# URL del TwiML App
twiml_app_url = 'wss://e3fe-20-42-11-17.ngrok-free.app/ws'

# Crear un cliente de Twilio
client = Client(account_sid, auth_token)

# Enviar una solicitud para iniciar una llamada
call = client.calls.create(
    twiml=f"<Response><Connect><Stream url=\"{twiml_app_url}\"/></Connect></Response>",
    to=destination_number,
    from_=twilio_number
)

print(f"Llamada iniciada con SID: {call.sid}")
