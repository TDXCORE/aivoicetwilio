"""
bot.py – Pipecat + Twilio + FastAPI
2025-06-22 - PATCHED VERSION - Con sugerencias específicas
"""

# ───────────────────────────── Logger global ──────────────────────────────
from loguru import logger
import sys, os, datetime as dt

logger.remove()
logger.add(
    sys.stderr,
    level="DEBUG",  # DEBUG para ver todos los frames
    format="[{time:HH:mm:ss.SSS}] {level} | {message}",
)

# ───────────────────────────── Imports Libs ──────────────────────────────
import json, os, asyncio
from typing import Union

from dotenv import load_dotenv
from fastapi import Request, WebSocket

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from openai._types import NOT_GIVEN
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.frames.frames import TextFrame

from pipecatcloud.agent import WebSocketSessionArguments

load_dotenv(override=True)

# ───────────────────────────── Spy Frame Processor ──────────────────────────────
class Spy(FrameProcessor):
    def __init__(self, spy_name: str = "Spy"):
        super().__init__()
        self.spy_name = spy_name  # Usar atributo propio en lugar de 'name'
        self.frame_count = 0

    async def process_frame(self, frame, direction: FrameDirection):
        self.frame_count += 1
        frame_type = type(frame).__name__
        
        # Log crítico para debugging
        if frame_type in ["AudioRawFrame", "TextFrame", "TranscriptionFrame", "LLMMessagesFrame"]:
            logger.info(f"🔍 {self.spy_name} - {direction.name} #{self.frame_count}: {frame_type}")
            
            # Log contenido para frames importantes
            if hasattr(frame, 'text') and frame.text:
                logger.info(f"   📝 Content: '{frame.text[:100]}{'...' if len(str(frame.text)) > 100 else ''}'")
            elif hasattr(frame, 'audio') and frame.audio:
                logger.debug(f"   🎵 Audio: {len(frame.audio)} bytes")
        else:
            logger.debug(f"🔍 {self.spy_name} - {direction.name} #{self.frame_count}: {frame_type}")
        
        await super().process_frame(frame, direction)

# ───────────────────────────── Core WebSocket flow ───────────────────────
async def main(ws: WebSocket) -> None:
    logger.info("🚀 PATCHED VERSION - Con AudioBuffer y Silence Fix")
    logger.info("🔖 VERSION: 2025-06-22-PATCHED")
    
    try:
        # ───── TWILIO HANDSHAKE ─────
        start_iter = ws.iter_text()
        await start_iter.__anext__()  # handshake
        start_msg = await start_iter.__anext__()
        start_data = json.loads(start_msg)
        
        stream_sid = start_data["start"]["streamSid"]
        call_sid = start_data["start"]["callSid"]
        
        logger.info(f"📞 CallSid: {call_sid}")
        logger.info(f"📞 StreamSid: {stream_sid}")

        # ───── CREAR SERVICIOS ─────
        serializer = TwilioFrameSerializer(
            stream_sid=stream_sid,
            call_sid=call_sid,
            account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
        )
        logger.info("✅ Twilio serializer created")

        stt = DeepgramSTTService(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            language="es",
            sample_rate=8000,
            audio_passthrough=True,
        )
        logger.info("✅ Deepgram STT created")
        
        llm = OpenAILLMService(
            api_key=os.getenv("OPENAI_API_KEY"), 
            model="gpt-4o-mini"
        )
        logger.info("✅ OpenAI LLM created")
        
        # ───── TTS CON SILENCE FIX ─────
        tts = CartesiaTTSService(
            api_key=os.getenv("CARTESIA_API_KEY"),
            voice_id="a0e99841-438c-4a64-b679-ae501e7d6091",
            push_silence_after_stop=True,  # 🔑 CLAVE: Cierra con silencio
        )
        logger.info("✅ Cartesia TTS created with silence fix")

        # ───── CONTEXTO LLM ─────
        messages = [
            {
                "role": "system",
                "content": "Eres Lorenzo, un asistente de voz amigable de TDX. Responde en español de forma natural y breve. Máximo 2 oraciones por respuesta."
            }
        ]
        context = OpenAILLMContext(messages, NOT_GIVEN)
        ctx_aggr = llm.create_context_aggregator(context)
        logger.info("✅ LLM context created")

        # ───── AUDIO BUFFER PROCESSOR ─────
        audiobuffer = AudioBufferProcessor(
            user_continuous_stream=True  # 🔑 CLAVE: Stream continuo
        )
        logger.info("✅ Audio buffer processor created")

        # ───── TRANSPORT CON VAD OPTIMIZADO ─────
        vad = SileroVADAnalyzer(
            sample_rate=8000,
            threshold=0.3,                    # ← Vuelve a 'threshold', no 'speech_threshold'
            min_speech_duration_ms=250,       # Detecta habla más rápido
            min_silence_duration_ms=300       # Menos tiempo de silencio
        )
        
        transport = FastAPIWebsocketTransport(
            websocket=ws,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                add_wav_header=False,
                vad_analyzer=vad,
                serializer=serializer,
            ),
        )
        logger.info("✅ Transport created with optimized VAD")

        # ───── PIPELINE CON SPY Y BUFFER ─────
        pipeline = Pipeline([
            transport.input(),
            Spy("INPUT"),           # 🔍 Log frames entrantes
            stt,
            ctx_aggr.user(),
            llm,
            tts,
            transport.output(),
            audiobuffer,            # 🔑 Buffer para stream continuo
            Spy("OUTPUT"),          # 🔍 Log frames salientes
            ctx_aggr.assistant(),
        ])
        logger.info("✅ Pipeline created with Spy processors and AudioBuffer")

        # ───── TASK ─────
        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                audio_in_sample_rate=8000,
                audio_out_sample_rate=8000,
                allow_interruptions=True,
                enable_metrics=True,
            ),
        )
        logger.info("✅ Pipeline task created")

        # ───── EVENT HANDLER PARA KICKOFF ─────
        @transport.event_handler("on_client_connected")
        async def _kickoff(transport_obj, client):
            logger.info("🎬 Client connected - Starting audio buffer and seeding context")
            
            # Iniciar grabación del buffer
            await audiobuffer.start_recording()
            logger.info("🎙️ Audio buffer recording started")
            
            # Seed del contexto para arrancar el flujo
            try:
                context_frame = ctx_aggr.user().get_context_frame()
                await task.queue_frames([context_frame])
                logger.info("🌱 Context seeded")
            except Exception as e:
                logger.warning(f"⚠️ Context seeding error: {e}")
            
            # Saludo inicial después de un momento
            async def delayed_greeting():
                await asyncio.sleep(2)
                logger.info("👋 Sending initial greeting...")
                greeting = TextFrame("¡Hola! Soy Lorenzo de TDX. Ya estoy listo para conversar contigo.")
                await task.queue_frame(greeting)
                logger.info("✅ Greeting sent")
            
            asyncio.create_task(delayed_greeting())

        # ───── MONITOREO CON FRAME COUNTING ─────
        async def frame_monitor():
            last_input_count = 0
            last_output_count = 0
            
            while True:
                await asyncio.sleep(15)  # Monitor cada 15 segundos
                
                # Obtener contadores de los Spy processors
                input_spy = None
                output_spy = None
                
                for processor in pipeline.processors:
                    if isinstance(processor, Spy):
                        if processor.spy_name == "INPUT":
                            input_spy = processor
                        elif processor.spy_name == "OUTPUT":
                            output_spy = processor
                
                input_count = input_spy.frame_count if input_spy else 0
                output_count = output_spy.frame_count if output_spy else 0
                
                logger.info(f"📊 FRAME MONITOR - Input: {input_count} | Output: {output_count}")
                
                # Detectar problemas
                if input_count > last_input_count and output_count == last_output_count:
                    logger.warning("⚠️ Input frames flowing but no output - pipeline may be stuck")
                elif input_count == last_input_count and input_count > 0:
                    logger.info("ℹ️ No new input frames - user may not be speaking")
                
                last_input_count = input_count
                last_output_count = output_count

        asyncio.create_task(frame_monitor())

        # ───── EJECUTAR PIPELINE ─────
        logger.info("🚀 Starting patched pipeline with enhanced debugging...")
        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)

    except Exception as e:
        logger.exception(f"💥 Pipeline error: {e}")
        raise

# ───────────────────────────── SMS webhook ──────────────────────────────
async def handle_twilio_request(request: Request):
    logger.info("📱 SMS request received")
    try:
        data = await request.form()
        body = data.get("Body", "")
        from_n = data.get("From", "")
        
        logger.info(f"📱 SMS from {from_n}: {body}")
        
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response><Message>SMS recibido: {body}</Message></Response>'
        )
    except Exception as e:
        logger.exception(f"💥 SMS error: {e}")
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response><Message>Error procesando SMS</Message></Response>'
        )

# ───────────────────────────── Entry Point ───────────────────────────────
async def bot(args: Union[WebSocketSessionArguments, WebSocket, Request]):
    logger.info(f"🎯 Bot called with: {type(args)}")

    try:
        if isinstance(args, WebSocketSessionArguments):
            await main(args.websocket)
        elif isinstance(args, WebSocket):
            await main(args)
        elif isinstance(args, Request):
            return await handle_twilio_request(args)
        else:
            logger.error(f"❌ Unsupported argument type: {type(args)}")
            
    except Exception as e:
        logger.exception(f"💥 Bot execution error: {e}")
        raise

# ───────────────────────────── Health Check ──────────────────────────────
async def health_check():
    logger.info("🏥 Health check requested")
    return {
        "status": "healthy", 
        "timestamp": dt.datetime.now().isoformat(),
        "version": "2025-06-22-PATCHED"
    }