# voicebot/bot.py
import os
import asyncio
import json
from typing import Union
from dotenv import load_dotenv
from fastapi import WebSocket, Request, Response
from loguru import logger

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.services.groq.stt import GroqSTTService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from openai._types import NOT_GIVEN
from pipecat.frames.frames import TextFrame

# Cargar variables de entorno
load_dotenv(override=True)

# ──────────────────────────────────────────
# 1) PIPELINE PARA LLAMADAS DE VOZ (WebSocket)
# ──────────────────────────────────────────
async def _voice_call(ws: WebSocket):
    """Maneja la conexión Media Streams de Twilio - Groq Whisper + Groq LLM + Cartesia."""
    logger.info("🎯 Iniciando pipeline de voz Groq Whisper + Groq LLM + Cartesia...")
    
    try:
        # ───── TWILIO HANDSHAKE (necesario para Media Streams) ─────
        start_iter = ws.iter_text()
        await start_iter.__anext__()  # CORREGIDO: __anext__() no _anext_()
        start_msg = await start_iter.__anext__()  # start message
        start_data = json.loads(start_msg)
        
        stream_sid = start_data["start"]["streamSid"]
        call_sid = start_data["start"]["callSid"]
        
        logger.info(f"📞 CallSid: {call_sid}")
        logger.info(f"📞 StreamSid: {stream_sid}")

        # ───── SERIALIZER CON DATOS DE TWILIO ─────
        serializer = TwilioFrameSerializer(
            stream_sid=stream_sid,
            call_sid=call_sid,
            account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
        )
        logger.info("✅ Twilio serializer creado")

        # ───── VAD CONFIGURADO PARA MAYOR SENSIBILIDAD ─────
        vad_analyzer = SileroVADAnalyzer(
            sample_rate=8000,
            params=VADParams(
                confidence=0.5,      # Más sensible para captar más audio
                start_secs=0.1,      # Respuesta más rápida
                stop_secs=0.5,       # Tiempo moderado antes de parar
                min_volume=0.3       # Volumen mínimo más bajo para captar audio débil
            )
        )
        logger.info("✅ Silero VAD creado con parámetros optimizados")

        # ───── TRANSPORT CON CONFIGURACIÓN OPTIMIZADA PARA AUDIO ─────
        transport = FastAPIWebsocketTransport(
            websocket=ws,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                add_wav_header=False,
                vad_analyzer=vad_analyzer,
                serializer=serializer,
                audio_in_sample_rate=8000,
                audio_out_sample_rate=8000,
                audio_in_channels=1,    # Mono channel explícito
                audio_out_channels=1,   # Mono channel explícito
            ),
        )
        logger.info("✅ Transport creado")

        # ───── GROQ WHISPER STT ─────
        stt = GroqSTTService(
            api_key=os.getenv("GROQ_API_KEY"),
            model="whisper-large-v3",
            language="es",
            temperature=0,  # Máxima precisión
        )
        logger.info("✅ Groq Whisper STT creado")
        
        # ───── GROQ LLM ─────
        llm = GroqLLMService(
            api_key=os.getenv("GROQ_API_KEY"), 
            model="llama-3.3-70b-versatile"
        )
        logger.info("✅ Groq LLM creado")
        
        # ───── CARTESIA TTS ─────
        cartesia_api_key = os.getenv("CARTESIA_API_KEY")
        if not cartesia_api_key:
            logger.error("❌ CARTESIA_API_KEY no configurada")
            raise ValueError("CARTESIA_API_KEY requerida")
            
        tts = CartesiaTTSService(
            api_key=cartesia_api_key,
            voice_id="a947d150-da06-4d02-8a43-f56d89da6ffd",  # Voice ID que funcionaba
            speed=0.8,  # Velocidad más natural
            sample_rate=8000,
        )
        logger.info("✅ Cartesia TTS creado")

        # ───── CONTEXTO LLM CORREGIDO ─────
        messages = [
            {
                "role": "system",
                "content": """# Guion de Llamada con Soluciones TDX

## **PERSONAJE: Freddy, SDR de TDX**

**PERSONALIDAD Y TONO:**
- **Consultor experto:** Formal-amigable, con la confianza de un par que entiende de tecnología y negocio.
- **Ritmo pausado y natural:** Sin muletillas coloquiales excesivas ni groserías.
- **Escucha activa:** Refleja las ideas del prospecto y conecta con lo que dice.
- **Conciso:** Máximo 2 oraciones por respuesta para mantener la fluidez.
- **Lenguaje orientado al beneficio:** Cada intervención se enfoca en el resultado que el líder obtiene.

**OBJETIVO DE LA LLAMADA:**
1. Descubrir dolores críticos del líder de tecnología.
2. Mapearlos a las soluciones de TDX.
3. Concretar una reunión de exploración de 25 minutos.

---

### **GUION DE LA LLAMADA**

**APERTURA** (usar SOLO después de que el prospecto hable primero - "Hola", "Buenos días", etc.):
"Buen día, le habla Freddy, de TDX. ¿Cómo está?"

(ESPERAR RESPUESTA Y RESPONDER CORTÉSMENTE)

**INTRO:**
"Qué bueno. El motivo de mi llamada es muy puntual: muchos líderes de tecnología nos comentan que sus equipos dedican casi un tercio de su tiempo a tareas repetitivas, en lugar de a innovar. De hecho, encontramos un método para devolverles ese tiempo para lo estratégico."

---

### **DESCUBRIMIENTO**

(usar estas preguntas según el flujo, asintiendo y conectando con la respuesta del prospecto):

- **Si el prospecto menciona desafíos con tareas repetitivas o carga de equipo:** "Eso que menciona es un reto muy frecuente, lo escucho constantemente en líderes de TI. Para entender mejor su caso, ¿dónde se están generando los **cuellos de botella** que más le quitan foco a su equipo hoy?"

- **Si el prospecto habla de lentitud en proyectos o innovación:** "Totalmente de acuerdo, la velocidad para innovar es crucial hoy en día. Pensando en esa agilidad, ¿cuánto tiempo le está tomando a su equipo llevar un nuevo prototipo desde la idea hasta que el usuario final puede interactuar con él?"

- **Si el prospecto menciona problemas de integración o manualidades:** "Claro, tener los sistemas hablando entre sí es la base para escalar sin fricción. A propósito de eso, ¿qué tantos **amarres manuales** tiene que hacer su equipo para que los canales como WhatsApp se entiendan con sus sistemas centrales como el ERP o CRM?"

- **Si el prospecto menciona problemas de atención al cliente o disponibilidad 24/7:** "Entiendo, la atención continua es clave hoy. ¿Cómo manejan actualmente los picos de consultas o la necesidad de soporte fuera del horario de oficina?"

---

### **SOLUCIONES TDX**

(mapear directamente al dolor identificado, conectando con la necesidad):

- **Para cuellos de botella en soporte (general o digital):** "Justo para ese dolor, con nuestro **AI Chatbot Multiagente por web o WhatsApp**, logramos que su equipo se libere de hasta el **ochenta por ciento** de esas consultas repetitivas. Así pueden dedicarse a lo que de verdad agrega valor."

- **Para cuellos de botella en soporte telefónico:** "Para esos momentos donde la línea telefónica se congestiona, nuestro **AI Voice para llamadas telefónicas** puede gestionar de forma autónoma gran parte de esas interacciones. Esto significa una resolución más rápida para el cliente y menos carga para su equipo."

- **Para tareas repetitivas (internas o cara a cliente):** "Entiendo, para **quitarse de encima** esas labores, nuestros **Flujos de Automatización** ejecutan esos procesos de forma autónoma. En la práctica, es devolverle horas muy valiosas a su gente para que innoven."

- **Para la velocidad de lanzamiento de MVPs:** "Para acelerar esa salida a producción, empaquetamos la solución en nuestro formato de **MVP en quince días**. Es la forma más rápida de validar sus ideas directamente en el mercado."

- **Para amarres manuales y sistemas desintegrados:** "Precisamente, para eliminar esa fricción, nuestras integraciones nativas con CRM y canales como WhatsApp logran que la información fluya sin reprocesos. Todo conversa de forma automática y natural."

- **Para ofrecer atención visual y personalizada 24/7:** "Si su objetivo es dar una experiencia más inmersiva, nuestros **AI Avatar para llamadas en vivo** pueden interactuar con sus clientes en tiempo real, resolviendo dudas y guiando procesos. Esto libera a su equipo y ofrece atención de alto nivel en todo momento."

- **Para atención al cliente en línea (web):** "Para una interacción más dinámica en su sitio web, nuestro **AI Voice asistente web** puede guiar a los usuarios a través de información compleja o procesos de compra. Esto mejora la experiencia del usuario y reduce la carga de consultas directas a su equipo."

---

### **CIERRE**

"Perfecto, [Nombre del prospecto]. Con base en lo que me comenta sobre [mencionar el dolor principal del prospecto], le propongo algo muy concreto y práctico: tengamos una conversación de **veinticinco minutos** para mostrarle con datos cómo un cliente con un reto similar al suyo logró resultados tangibles. ¿Le queda bien este **jueves a las diez a.m.** o prefiere el **viernes a primera hora**?"

---

### **MANEJO DE SITUACIONES**

- **Si el usuario dice "No" a las preguntas iniciales:** "Entiendo. ¿Y hay algún otro tema de eficiencia operativa o agilidad en proyectos que sea importante para usted en este momento?" o "Comprendo. ¿Quizás el tiempo que invierten en tareas de soporte repetitivas podría ser un área a mejorar?"
- **Si no entiende una transcripción:** "Disculpe, no logré escucharlo bien, ¿podría repetir por favor?"
- **Si hay silencio prolongado:** "Le pregunto esto porque he visto a muchos líderes con desafíos similares. ¿Hay algo que le genere inquietud en este tipo de soluciones?"
- **Nunca quedarse completamente callado,** siempre mantener la conversación activa y consultiva.

---

**INSTRUCCIONES CRÍTICAS:**
- ESPERAR siempre a que el usuario hable primero antes de usar la apertura.
- NO generar respuestas automáticas al conectarse.
- Responder SOLO cuando recibas input real del usuario.
- Seguir el guion paso a paso después de que el cliente hable.
- Escuchar 70%, hablar 30%.
- Siempre buscar agendar la reunión.
- Usar vocabulario formal-colombiano: "cuello de botella", "amarres", "quitarse de encima".
- Respuestas máximo 2 oraciones para mantener fluidez.
- No incluir caracteres especiales en las respuestas ya que se convertirán a audio.
- Ser adaptable y conversacional, mantener el flujo natural."""
            }
        ]
        
        # ───── CONTEXTO SIN MENSAJE INICIAL ─────
        context = OpenAILLMContext(messages)
        context_aggregator = llm.create_context_aggregator(context)
        logger.info("✅ Contexto de ventas B2B creado")

        # ───── PIPELINE ─────
        pipeline = Pipeline([
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ])
        logger.info("✅ Pipeline creado")

        # ───── TASK ─────
        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                audio_in_sample_rate=8000,
                audio_out_sample_rate=8000,
                allow_interruptions=True,
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
        )
        
        # ───── EVENTOS DE TRANSPORTE CON DEBUGGING ─────        
        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info(f"🔗 Cliente conectado: {client}")
            # NO enviar ningún frame inicial - esperar a que el usuario hable

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info(f"👋 Cliente desconectado: {client}")
            await task.cancel()

        # ───── EVENTOS PARA DEBUGGING DE STT (CORREGIDO) ─────
        try:
            @stt.event_handler("on_transcript")
            async def on_transcript(stt, transcript):
                logger.info(f"🎯 Groq Whisper transcripción: '{transcript}'")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo registrar event handler on_transcript: {e}")
            # Intentar con eventos alternativos
            try:
                @stt.event_handler("on_stt_final")
                async def on_stt_final(stt, text):
                    logger.info(f"🎯 Groq Whisper transcripción final: '{text}'")
            except:
                logger.warning("⚠️ Eventos STT no disponibles, continuando sin logging de transcripciones")

        # ───── EJECUTAR RUNNER ─────
        logger.info("🚀 Iniciando pipeline de ventas B2B con Groq Whisper...")
        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)
        logger.info("📞 Llamada de ventas finalizada")
        
    except Exception as e:
        logger.exception(f"💥 Error en pipeline de ventas: {e}")
        # Cierre limpio de WebSocket
        try:
            if not ws.client_state.DISCONNECTED:
                await ws.close()
        except:
            pass
        raise


# ──────────────────────────────────────────
# 2) PIPELINE SMS / WHATSAPP (webhook HTTP)
# ──────────────────────────────────────────
async def _sms(request: Request) -> Response:
    """Maneja mensajes SMS/WhatsApp de Twilio - Groq LLM."""
    try:
        form = await request.form()
        user_msg = form.get("Body", "") or "..."
        from_number = form.get("From", "")
        
        logger.info(f"💬 SMS de {from_number}: '{user_msg}'")

        # Usar Groq Llama para respuesta de texto
        llm = GroqLLMService(
            api_key=os.getenv("GROQ_API_KEY"),
            model="llama-3.3-70b-versatile"
        )
        
        # Contexto simple para SMS
        context = OpenAILLMContext([
            {
                "role": "system", 
                "content": "Eres Freddy, SDR de TDX. Responde de forma concisa y profesional en español. Enfócate en agendar una reunión para mostrar nuestras soluciones de IA conversacional."
            },
            {
                "role": "user",
                "content": user_msg
            }
        ])
        
        # Generar respuesta
        response = await llm._process_context(context)
        reply = response.choices[0].message.content
        
        logger.info(f"🤖 Respuesta SMS: '{reply}'")

        # TwiML para responder
        twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{reply}</Message></Response>'
        return Response(content=twiml, media_type="text/xml")
        
    except Exception as e:
        logger.exception(f"💥 Error en SMS: {e}")
        error_twiml = '<?xml version="1.0" encoding="UTF-8"?><Response><Message>Error procesando mensaje</Message></Response>'
        return Response(content=error_twiml, media_type="text/xml")


# ──────────────────────────────────────────
# 3) HEALTH CHECK
# ──────────────────────────────────────────
async def health_check():
    """Health check endpoint."""
    logger.info("🏥 Health check Pipeline de Ventas B2B")
    return {
        "status": "healthy", 
        "service": "TDX Sales Bot - Groq Whisper + Groq LLM + Cartesia",
        "version": "2025-06-25-GROQ-WHISPER-CLEAN",
        "apis": {
            "groq": bool(os.getenv("GROQ_API_KEY")),
            "cartesia": bool(os.getenv("CARTESIA_API_KEY")),
            "twilio": bool(os.getenv("TWILIO_ACCOUNT_SID")),
        },
        "services": {
            "stt": "Groq Whisper Large V3",
            "llm": "Groq Llama 3.3 70B", 
            "tts": "Cartesia optimizado",
            "purpose": "Sales Development Representative (SDR)"
        }
    }


# ──────────────────────────────────────────
# 4) PUNTO ÚNICO DE ENTRADA
# ──────────────────────────────────────────
async def bot(ctx):
    """
    Función principal para Sales Bot B2B.
    Compatible con tu main.py existente.
    """
    if isinstance(ctx, WebSocket):
        logger.info("📞 Llamada de ventas → Freddy SDR de TDX")
        await _voice_call(ctx)
    elif isinstance(ctx, Request):
        logger.info("💬 Mensaje SMS/WhatsApp → Freddy SDR")
        return await _sms(ctx)
    else:
        logger.error(f"❌ Tipo no soportado: {type(ctx)}")
        raise TypeError("bot() sólo acepta WebSocket o Request de FastAPI")