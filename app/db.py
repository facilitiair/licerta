"""Modelo de dados (SQLAlchemy) — espelha a seção 4 do SPEC.md."""
from datetime import datetime

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, ForeignKey,
                        Integer, String, Text, UniqueConstraint, create_engine,
                        event)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .config import CAMINHO_DB

engine = create_engine(f"sqlite:///{CAMINHO_DB}",
                       connect_args={"check_same_thread": False,
                                     "timeout": 30})


@event.listens_for(engine, "connect")
def _configurar_sqlite(conexao, _registro):
    """WAL: leituras funcionam DURANTE a coleta (sem 'database is locked'),
    e quem esbarrar numa escrita espera até 30s em vez de dar erro 500."""
    cursor = conexao.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()
Sessao = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()


class PerfilBusca(Base):
    __tablename__ = "perfis_busca"
    id = Column(Integer, primary_key=True)
    nome = Column(Text, nullable=False)
    ativo = Column(Boolean, default=True, nullable=False)
    ufs = Column(JSON, default=list)               # vazio = Brasil inteiro
    municipios_ibge = Column(JSON, default=list)   # vazio = todos da UF
    modalidades = Column(JSON, default=list)       # vazio = todas
    palavras_incluir = Column(JSON, default=list)  # casa se qualquer uma aparecer
    palavras_excluir = Column(JSON, default=list)  # descarta se qualquer uma aparecer
    valor_min = Column(Float, nullable=True)
    valor_max = Column(Float, nullable=True)
    somente_srp = Column(Boolean, default=False, nullable=False)
    modo_busca = Column(String, default="ou", nullable=False)  # 'ou' | 'e'
    ordenacao = Column(String, default="encerramento_asc", nullable=False)
    situacoes = Column(JSON, default=list)         # vazio = qualquer situação
    # Nunca alertar sobre disputa cujo prazo de proposta já passou
    somente_vigentes = Column(Boolean, default=True, nullable=False)
    # --- agendamento do alerta deste perfil ---
    notificar = Column(Boolean, default=True, nullable=False)
    frequencia = Column(String, default="diario", nullable=False)
    intervalo_horas = Column(Integer, default=3, nullable=False)  # freq 'horas'
    dia_semana = Column(Integer, default=0, nullable=False)   # 0=segunda
    dia_mes = Column(Integer, default=1, nullable=False)      # 1..28
    mes_ano = Column(Integer, default=1, nullable=False)      # 1..12 (anual)
    hora_envio = Column(String, default="", nullable=False)   # "" = HORA_ALERTA
    ultimo_envio = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, default=datetime.now, nullable=False)
    matches = relationship("PerfilMatch", back_populates="perfil",
                           cascade="all, delete-orphan")


class Licitacao(Base):
    __tablename__ = "licitacoes"
    id = Column(Integer, primary_key=True)
    numero_controle_pncp = Column(String, unique=True, nullable=False, index=True)
    objeto = Column(Text)
    modalidade_codigo = Column(Integer, index=True)
    modalidade_nome = Column(String)
    orgao_cnpj = Column(String)
    orgao_nome = Column(String)
    unidade_nome = Column(String)
    municipio_nome = Column(String)
    uf = Column(String, index=True)
    municipio_ibge = Column(String)
    numero_compra = Column(String)
    ano_compra = Column(Integer)
    processo = Column(String)
    valor_total_estimado = Column(Float, nullable=True)
    srp = Column(Boolean, default=False)
    data_publicacao_pncp = Column(String)      # ISO, como vem da API
    data_abertura_proposta = Column(String)
    data_encerramento_proposta = Column(String, index=True)
    link_sistema_origem = Column(String)
    link_pncp = Column(String)
    situacao = Column(String)                  # Divulgada, Retificada, Suspensa...
    objeto_norm = Column(Text)                 # objeto sem acentos p/ busca livre
    payload_json = Column(Text)                # resposta bruta completa
    fonte = Column(String, default="pncp")     # 'pncp' | 'tcepi'
    coletado_em = Column(DateTime, default=datetime.now)
    matches = relationship("PerfilMatch", back_populates="licitacao",
                           cascade="all, delete-orphan")


class PerfilMatch(Base):
    __tablename__ = "perfil_matches"
    id = Column(Integer, primary_key=True)
    perfil_id = Column(Integer, ForeignKey("perfis_busca.id"), nullable=False)
    licitacao_id = Column(Integer, ForeignKey("licitacoes.id"), nullable=False)
    data_match = Column(DateTime, default=datetime.now, nullable=False)
    notificado = Column(Boolean, default=False, nullable=False)
    lido = Column(Boolean, default=False, nullable=False)
    favorito = Column(Boolean, default=False, nullable=False)
    status = Column(String, default="novo", nullable=False)
    termos = Column(String, default="")        # quais palavras do perfil casaram
    anotacao = Column(Text, default="")
    perfil = relationship("PerfilBusca", back_populates="matches")
    licitacao = relationship("Licitacao", back_populates="matches")
    __table_args__ = (UniqueConstraint("perfil_id", "licitacao_id",
                                       name="uq_perfil_licitacao"),)


class ColetaLog(Base):
    __tablename__ = "coletas_log"
    id = Column(Integer, primary_key=True)
    inicio = Column(DateTime, nullable=False)
    fim = Column(DateTime)
    sucesso = Column(Boolean, default=False)
    qtd_novas = Column(Integer, default=0)
    qtd_erros = Column(Integer, default=0)
    detalhe_erro = Column(Text, default="")


class Ata(Base):
    """Atas de registro de preços vigentes que casaram com algum perfil (Fase 3)."""
    __tablename__ = "atas"
    id = Column(Integer, primary_key=True)
    numero_controle_ata = Column(String, unique=True, nullable=False, index=True)
    numero_controle_compra = Column(String, index=True)
    numero_ata = Column(String)
    ano_ata = Column(Integer)
    objeto = Column(Text)
    orgao_cnpj = Column(String)
    orgao_nome = Column(String)
    unidade_nome = Column(String)
    data_assinatura = Column(String)
    vigencia_inicio = Column(String)
    vigencia_fim = Column(String, index=True)
    possibilidade_adesao = Column(Boolean, default=False)
    cancelado = Column(Boolean, default=False)
    perfis_casados = Column(JSON, default=list)   # nomes dos perfis que casaram
    link_pncp = Column(String)
    payload_json = Column(Text)
    coletado_em = Column(DateTime, default=datetime.now)


class ArquivoEdital(Base):
    """PDFs de edital baixados automaticamente da API de documentos (Fase 3)."""
    __tablename__ = "arquivos_edital"
    id = Column(Integer, primary_key=True)
    licitacao_id = Column(Integer, ForeignKey("licitacoes.id"), nullable=False,
                          index=True)
    titulo = Column(String)
    tipo = Column(String)
    url_origem = Column(String)
    caminho_local = Column(String)      # relativo à pasta data/
    baixado_em = Column(DateTime, default=datetime.now)
    licitacao = relationship("Licitacao")


class Modalidade(Base):
    __tablename__ = "modalidades"
    codigo = Column(Integer, primary_key=True)
    nome = Column(String, nullable=False)


class Municipio(Base):
    __tablename__ = "municipios"
    codigo_ibge = Column(String, primary_key=True)
    nome = Column(String, nullable=False, index=True)
    uf = Column(String, nullable=False, index=True)


def criar_tabelas():
    Base.metadata.create_all(engine)
    _migrar()


def _migrar():
    """Migrações leves para bancos criados em fases anteriores."""
    pendencias = {
        "licitacoes": [("fonte", "TEXT DEFAULT 'pncp'"), ("situacao", "TEXT"),
                       ("objeto_norm", "TEXT")],
        "perfil_matches": [("termos", "TEXT DEFAULT ''")],
        "perfis_busca": [("modo_busca", "TEXT DEFAULT 'ou'"),
                         ("situacoes", "TEXT DEFAULT '[]'"),
                         ("somente_vigentes", "BOOLEAN DEFAULT 1"),
                         ("frequencia", "TEXT DEFAULT 'diario'"),
                         ("intervalo_horas", "INTEGER DEFAULT 3"),
                         ("dia_semana", "INTEGER DEFAULT 0"),
                         ("dia_mes", "INTEGER DEFAULT 1"),
                         ("mes_ano", "INTEGER DEFAULT 1"),
                         ("hora_envio", "TEXT DEFAULT ''"),
                         ("ultimo_envio", "DATETIME")],
    }
    with engine.connect() as con:
        criadas = set()
        for tabela, novas in pendencias.items():
            colunas = [linha[1] for linha in
                       con.exec_driver_sql(f"PRAGMA table_info({tabela})")]
            for nome, tipo in novas:
                if nome not in colunas:
                    con.exec_driver_sql(
                        f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}")
                    criadas.add(f"{tabela}.{nome}")
        # Perfis anteriores ao filtro de situação nasceriam aceitando tudo,
        # inclusive cancelada e revogada. Só na criação da coluna: se depois
        # o usuário desmarcar todas de propósito, a escolha dele permanece.
        if "perfis_busca.situacoes" in criadas:
            con.exec_driver_sql(
                """UPDATE perfis_busca SET situacoes = '["Divulgada", "Aberta"]'
                   WHERE situacoes IS NULL OR situacoes = '[]'""")
        # Unifica a situação entre as fontes (PNCP dizia "Divulgada no PNCP",
        # o Mural TCE-PI diz "Divulgada") — idempotente, roda a cada partida
        con.exec_driver_sql(
            "UPDATE licitacoes SET situacao = REPLACE(situacao, ' no PNCP', '') "
            "WHERE situacao LIKE '% no PNCP'")
        con.commit()
