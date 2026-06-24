from dotenv import load_dotenv
from openai import OpenAI
import json
import os
import requests
from pypdf import PdfReader
import gradio as gr

import json
import chromadb

# Configuración

load_dotenv(override=True)
client = OpenAI()
chroma_client = chromadb.PersistentClient(path="./mi_base_de_datos")
collection = chroma_client.get_or_create_collection(name="faq_cv")




def push(text):
    requests.post(
        "https://api.pushover.net/1/messages.json",
        data={
            "token": os.getenv("PUSHOVER_TOKEN"),
            "user": os.getenv("PUSHOVER_USER"),
            "message": text,
        }
    )


def record_user_details(email, name="Nombre no indicado", notes="no proporcionadas"):
    push(f"Registrando {name} con email {email} y notas {notes}")
    return {"recorded": "ok"}

def record_unknown_question(question):
    push(f"Registrando {question}")
    return {"recorded": "ok"}



def buscar_en_faq(query_usuario: str):
    # 1. Convertir pregunta a embedding
    res = client.embeddings.create(input=query_usuario, model="text-embedding-3-small")
    query_embedding = res.data[0].embedding
    
    # 2. Consultar Chroma
    resultados = collection.query(
        query_embeddings=[query_embedding],
        n_results=1
    )
    
    # 3. Extraer respuesta (el primer resultado es el más cercano)
    return resultados['metadatas'][0][0]['respuesta']



record_user_details_json = {
    "name": "record_user_details",
    "description": "Utiliza esta herramienta para registrar que un usuario está interesado en estar en contacto y proporcionó una dirección de correo electrónico.",
    "parameters": {
        "type": "object",
        "properties": {
            "email": {
                "type": "string",
                "description": "La dirección de email del usuario"
            },
            "name": {
                "type": "string",
                "description": "El nombre del usuario, si se indica"
            }
            ,
            "notes": {
                "type": "string",
                "description": "¿Alguna información adicional sobre la conversación que valga la pena registrar para dar contexto?"
            }
        },
        "required": ["email"],
        "additionalProperties": False
    }
}

record_unknown_question_json = {
    "name": "record_unknown_question",
    "description": "Utiliza esta herramienta ÚNICAMENTE como último recurso, si la pregunta NO pudo ser respondida ni utilizando la herramienta 'buscar_en_faq' ni utilizando la información de tu contexto (Resumen y perfil de LinkedIn).",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "La pregunta exacta del usuario que no supiste responder tras consultar todas tus fuentes."
            },
        },
        "required": ["question"],
        "additionalProperties": False
    }
}

buscar_en_faq_json = {
    "name": "buscar_en_faq",
    "description": "Usar primero cuando se busca información profesional, experiencia o preguntas frecuentes sobre el CV del candidato.",
    "parameters": {
        "type": "object",
        "properties": {
            "query_usuario": {
                "type": "string",
                "description": "La pregunta exacta del usuario sobre el CV"
            }
        },
        "required": ["query_usuario"],
        "additionalProperties": False
    }
}

tools = [{"type": "function", "function": record_user_details_json},
        {"type": "function", "function": record_unknown_question_json},
        {"type": "function", "function": buscar_en_faq_json}]


class Me:

    def __init__(self):
        self.openai = OpenAI()
        self.name = "Juan Pablo Schamun"
        reader = PdfReader("me/linkedin.pdf")
        self.linkedin = ""
        files = ["me/CV-AI_JPS.pdf", "me/CV Juan Pablo Schamun - BI Analyst Senior.pdf", "me/CV-JPS_Perfil Industrial.pdf"]
        for file in files:    
            reader = PdfReader(file)
            for page in reader.pages:                
                text = page.extract_text()
                if text:
                    self.linkedin += text
        with open("me/summaryjp.txt", "r", encoding="utf-8") as f:
            self.summary = f.read()


    def handle_tool_call(self, tool_calls):
        results = []
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            print(f"Tool called: {tool_name}", flush=True)
            tool = globals().get(tool_name)
            result = tool(**arguments) if tool else {}
            results.append({"role": "tool","content": json.dumps(result),"tool_call_id": tool_call.id})
        return results
    
    def system_prompt(self):
        system_prompt = f"""Actúas como {self.name}. Tu objetivo es representar a {self.name} en interacciones profesionales en su sitio web, enfocándote en su trayectoria, habilidades y experiencia.

            ### PRIORIDAD DE FUENTES DE INFORMACIÓN:
            Sigue este orden secuencial y estricto antes de responder:           
            1. Si es un saludo, no uses  herramientas
            2. HERRAMIENTA 'buscar_en_faq': Úsala primero siempre que la pregunta trate sobre experiencia, habilidades, trayectoria, formación o antecedentes.
            3. CONTEXTO (RESUMEN/LINKEDIN): Si la herramienta 'buscar_en_faq' no devuelve información útil, revisa el Resumen y Perfil de LinkedIn proporcionados abajo.
            43. REGISTRO DE DUDAS: SOLO si la respuesta NO se encuentra ni en 'buscar_en_faq' NI en el contexto proporcionado, utiliza la herramienta 'record_unknown_question'.

            ### DIRECTRICES DE CONVERSACIÓN:
            - Mantén un tono profesional, atractivo y fiel al personaje de {self.name}.
            - Si la información obtenida de 'buscar_en_faq' no es relevante, ignórala y apóyate exclusivamente en tu contexto.            
            - Si la conversación es fluida, invita al usuario a contactar por correo electrónico; si lo comparte, regístralo mediante 'record_user_details'.

            ## INFORMACIÓN DE RESPALDO:
            ## Resumen:
            {self.summary}

            ## Perfil de LinkedIn:
            {self.linkedin}

            En este contexto, mantente siempre en el personaje de {self.name} y responde de manera natural y precisa."""
                    
        return system_prompt
    
    
    def chat(self, message, history):
        # 1. LIMITAR EL HISTORIAL: Nos quedamos solo con los últimos 6 mensajes (3 intercambios)
        historial_reciente = history[-6:] if len(history) > 6 else history
        
        # 2. RECORDATORIO TÁCTICO: Reforzamos la regla en el último mensaje para que no lo olvide
        # 2. RECORDATORIO TÁCTICO ACTUALIZADO
        recordatorio = "\n\n[Instrucción interna: Si el mensaje es un simple saludo o cortesía, responde naturalmente saludando e invitando a consultar sobre tu experiencia SIN usar herramientas. Si es una pregunta sobre tu perfil, usa 'buscar_en_faq'.]"
        mensaje_reforzado = message + recordatorio

        # Armamos los mensajes con el historial recortado y el mensaje reforzado
        messages = [{"role": "system", "content": self.system_prompt()}] + historial_reciente + [{"role": "user", "content": mensaje_reforzado}]
        
        done = False
        while not done:
            response = self.openai.chat.completions.create(
                model="gpt-4o-mini", 
                messages=messages, 
                tools=tools,
                parallel_tool_calls=False # Mantenemos esto activado
            )
            
            if response.choices[0].finish_reason == "tool_calls":
                # Al reasignar 'message', evitamos que el recordatorio táctico 
                # cause problemas en el registro del historial de herramientas
                mensaje_herramienta = response.choices[0].message
                tool_calls = mensaje_herramienta.tool_calls
                results = self.handle_tool_call(tool_calls)
                messages.append(mensaje_herramienta)
                messages.extend(results)
            else:
                done = True
                
        return response.choices[0].message.content
    

if __name__ == "__main__":
    me = Me()
    gr.ChatInterface(me.chat, type="messages").launch()
    
