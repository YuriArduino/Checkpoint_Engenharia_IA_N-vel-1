"""Metadatastore persistente em SQLite para o barramento do BFA Service."""

import os
import sqlite3
from typing import Any, Dict, Optional

# Aponta para o arquivo unificado dentro do volume compartilhado do Docker
DB_PATH = "/app/shared_db/mvp_database.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def init_db() -> None:
    """Cria a tabela de metadados do barramento se ela não existir."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS registry (
                faiss_id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_id TEXT UNIQUE,
                name TEXT,
                description TEXT,
                tags TEXT,
                type TEXT,
                execution_url TEXT,
                input_schema TEXT
            )
        """)
        conn.commit()


def save_skill(
    skill_id: str,
    name: str,
    desc: str,
    tags: str,
    s_type: str,
    execution_url: str,
    input_schema: Optional[str] = None,
) -> int:
    """Salva ou atualiza uma capacidade e retorna o faiss_id gerado."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO registry (
                skill_id, name, description, tags, type, execution_url, input_schema
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(skill_id) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                tags=excluded.tags,
                type=excluded.type,
                execution_url=excluded.execution_url,
                input_schema=excluded.input_schema
        """,
            (skill_id, name, desc, tags, s_type, execution_url, input_schema),
        )

        # Pega o ID gerado ou atualizado para sincronizar perfeitamente com o FAISS
        cursor.execute("SELECT faiss_id FROM registry WHERE skill_id = ?", (skill_id,))
        row = cursor.fetchone()
        conn.commit()
        return int(row[0])


def get_skill_by_id(faiss_id: int) -> Optional[Dict[str, Any]]:
    """Recupera os dados completos da capacidade para o roteamento do Broker."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row  # Otimização: Retorna chaves nomeadas
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT skill_id, name, description, type, execution_url, input_schema
            FROM registry
            WHERE faiss_id = ?
        """,
            (faiss_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
