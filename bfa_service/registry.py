"""Gerenciador de Catálogo e Índice Híbrido (FAISS + BM25) com fusão RRF."""

import os
import re
import unicodedata
import logging
from typing import Optional, Dict, Any, List
import numpy as np
import faiss
from rank_bm25 import BM25Okapi
from dotenv import load_dotenv
from pydantic import SecretStr

from langchain_openai import OpenAIEmbeddings

# Imports absolutos para evitar conflitos de top-level
from .database import save_skill
from .discovery import run_global_scan

logger = logging.getLogger("bfa.registry")

# Carrega as variáveis de ambiente
load_dotenv()

# Configuração do Embedder apontando para o seu LM Studio local
embedder = OpenAIEmbeddings(
    model=os.getenv("EMBEDDING_MODEL", "text-embedding-all-minilm-l6-v2-embedding"),
    base_url=os.getenv("OPENAI_BASE_URL", "http://host.docker.internal:1234/v1"),
    api_key=SecretStr(os.getenv("OPENAI_API_KEY", "lm-studio")),
    check_embedding_ctx_length=False,
)

# Catálogo em memória e estruturas globais dos índices
AGENT_REGISTRY: Dict[str, Dict[str, Any]] = {}
BM25_INDEX: Optional[BM25Okapi] = None
BM25_KEYS: List[str] = []
FAISS_INDEX: Optional[faiss.IndexFlatIP] = None
FAISS_KEYS: List[str] = []


def normalize(text: str) -> str:
    """Remove acentos, converte para minúsculas e limpa espaços."""
    if not text:
        return ""
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    return text.encode("ascii", "ignore").decode("utf-8")


def tokenize(text: str) -> List[str]:
    """Extrai tokens alfanuméricos de um texto normalizado."""
    return re.findall(r"\w+", normalize(text))


async def build_index() -> None:
    """Orquestra a coleta do discovery, persiste no SQL e compila os índices híbridos."""
    # pylint: disable=global-statement
    global BM25_INDEX, BM25_KEYS, FAISS_INDEX, FAISS_KEYS

    raw_data = await run_global_scan()
    if not raw_data:
        logger.warning("[Registry] Nenhum dado de capacidade foi coletado da rede.")
        return

    corpus_tokens: List[List[str]] = []
    texts_to_embed: List[str] = []
    keys: List[str] = []

    for skill_id, info in raw_data.items():
        save_skill(
            skill_id=skill_id,
            name=info["name"],
            desc=info["description"],
            tags=" ".join(info["tags"]),
            s_type=info["type"],
            execution_url=info["execution_url"],
            input_schema=info["input_schema"],
        )

        AGENT_REGISTRY[skill_id] = info
        search_text = f"{info['name']} {info['description']} {' '.join(info['tags'])}"
        tokens = tokenize(search_text)

        if not tokens:
            continue

        corpus_tokens.append(tokens)
        texts_to_embed.append(search_text)
        keys.append(skill_id)

    if not keys:
        return

    # Compilação do Índice Léxico (BM25)
    BM25_INDEX = BM25Okapi(corpus_tokens)
    BM25_KEYS = keys

    # Compilação do Índice Semântico (FAISS) usando LM Studio
    logger.info("[Registry] Gerando embeddings via LM Studio...")
    embeddings_list = await embedder.aembed_documents(texts_to_embed)

    # Converte a lista do LangChain para o array Numpy exigido pelo FAISS
    embeddings_array = np.array(embeddings_list).astype("float32")
    dimension = embeddings_array.shape[1]

    faiss_idx = faiss.IndexFlatIP(dimension)
    faiss.normalize_L2(embeddings_array)

    # Correção (E1120): Suprime o falso positivo do Pylint com as assinaturas C++ (SWIG) do FAISS
    # pylint: disable=no-value-for-parameter
    faiss_idx.add(embeddings_array)

    FAISS_INDEX = faiss_idx
    FAISS_KEYS = keys
    logger.info("[Registry] Índices Híbridos (FAISS + BM25) compilados para %d itens.", len(keys))


async def resolve_agent(
    query: str, top_k: int = 3, k_rrf: int = 60, filter_type: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Resolve o melhor agente/tool aplicando Reciprocal Rank Fusion (RRF)."""
    if not BM25_INDEX or not FAISS_INDEX:
        return None

    query_tokens = tokenize(query)
    if not query_tokens:
        return None

    # Ranking BM25 (Léxico)
    bm25_scores = BM25_INDEX.get_scores(query_tokens)
    bm25_ranked = np.argsort(bm25_scores)[::-1]
    bm25_rank = {BM25_KEYS[idx]: rank for rank, idx in enumerate(bm25_ranked)}

    # Ranking FAISS (Semântico) usando LM Studio
    query_vector_list = await embedder.aembed_query(query)

    # Transforma o vetor único em um array 2D para a busca do FAISS
    query_vector_array = np.array([query_vector_list]).astype("float32")
    faiss.normalize_L2(query_vector_array)

    # Correção (E1120): Falso positivo do C++ no FAISS
    # pylint: disable=no-value-for-parameter
    _, faiss_idx = FAISS_INDEX.search(query_vector_array, len(FAISS_KEYS))
    faiss_rank = {FAISS_KEYS[idx]: rank for rank, idx in enumerate(faiss_idx[0])}

    # Fusão RRF por Posição
    rrf_scores = {}

    # Correção (C0201/C0206): Iteração limpa de dicionários usando .items()
    for skill_id, agent_info in AGENT_REGISTRY.items():
        if filter_type and agent_info.get("type") != filter_type:
            continue

        r_bm25 = bm25_rank.get(skill_id, len(BM25_KEYS))
        r_faiss = faiss_rank.get(skill_id, len(FAISS_KEYS))

        rrf_scores[skill_id] = (1.0 / (k_rrf + r_bm25)) + (1.0 / (k_rrf + r_faiss))

    if not rrf_scores:
        return None

    sorted_candidates = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    results = []
    for skill_id, score in sorted_candidates[:top_k]:
        results.append(
            {
                "skill": skill_id,
                "rrf_score": score,
                "type": AGENT_REGISTRY[skill_id].get("type"),
                "data": AGENT_REGISTRY[skill_id],
            }
        )

    if not results:
        return None

    return {"type": "hybrid_rrf", "best": results[0], "candidates": results}
