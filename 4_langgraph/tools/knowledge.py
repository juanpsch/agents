from langchain.tools import tool
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from dotenv import load_dotenv
from datetime import datetime
import os

load_dotenv(override=True)
CHROMA_DIR = "chroma_notes"
os.makedirs(CHROMA_DIR, exist_ok=True)

_embeddings = None
_vector_store = None

def _get_vector_store():
    global _embeddings, _vector_store
    if _vector_store is None:
        try:
            # Usar embeddings locales (HuggingFace) en lugar de OpenAI
            _embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
            _vector_store = Chroma(
                collection_name="notes",
                embedding_function=_embeddings,
                persist_directory=CHROMA_DIR
            )
            print("✓ Vector store inicializado correctamente")
        except Exception as e:
            print(f"✗ Error inicializando vector store: {str(e)}")
            raise RuntimeError(f"Error inicializando Chroma: {str(e)}")
    return _vector_store


@tool
def save_note(topic: str, content: str) -> str:
    """Guardar una nota con embedding para búsqueda semántica.

    Args:
        topic: El tema o categoría de la nota
        content: El contenido de la nota a guardar
    """
    note_id = f"{topic}_{datetime.now().timestamp()}"
    vs = _get_vector_store()
    vs.add_texts(
        texts=[content],
        metadatas=[{
            "topic": topic,
            "timestamp": datetime.now().isoformat()
        }],
        ids=[note_id]
    )
    return f"✓ Nota guardada en tema '{topic}'"


@tool
def search_notes(query: str) -> str:
    """Buscar notas relevantes por similitud semántica.

    Args:
        query: La pregunta o tema a buscar en las notas guardadas
    """
    vs = _get_vector_store()
    results = vs.similarity_search(query, k=3)

    if not results:
        return "No encontré notas relevantes"

    output = f"Encontré {len(results)} notas relevantes:\n\n"
    for i, doc in enumerate(results, 1):
        topic = doc.metadata.get("topic", "Sin tema")
        timestamp = doc.metadata.get("timestamp", "")
        output += f"**Nota {i} ({topic})** [{timestamp}]\n{doc.page_content}\n\n"

    return output


def get_knowledge_tools() -> list:
    """Retornar herramientas de conocimiento"""
    return [save_note, search_notes]
