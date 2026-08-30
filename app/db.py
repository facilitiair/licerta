"""Modelo de dados (SQLAlchemy) — espelha a seção 4 do SPEC.md."""
from datetime import datetime

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, ForeignKey,
                        Integer, String, Text, UniqueConstraint, create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .config import CAMINHO_DB

engine = create_engine(f"sqlite:///{CAMINHO_DB}",
                       connect_args={"check_same_thread": False})
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
    ordenacao = Column(String, default="encerramento_asc", nullable=False)
    notificar = Column(Boolean, default=True, nullable=False)
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
    payload_json = Column(Text)                # resposta bruta completa
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
