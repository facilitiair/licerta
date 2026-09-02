"""Modelo de dados (SQLAlchemy) — espelha a seção 4 do SPEC.md."""

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, ForeignKey,
                        Integer, String, Text, UniqueConstraint, create_engine,
                        event)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .config import CAMINHO_DB, agora

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


class Usuario(Base):
    """Cada pessoa da empresa tem sua conta, seus perfis e seus canais de
    aviso (Telegram, e-mail, push no celular) — o app é multiusuário."""
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True)
    nome = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    senha_hash = Column(String, nullable=False)     # scrypt salgado
    papel = Column(String, default="usuario", nullable=False)  # admin|usuario
    # Plano comercial: recursos de análise profunda (perícia completa e
    # perito documental) são do plano premium; admin sempre tem acesso.
    plano = Column(String, default="padrao", nullable=False)  # padrao|premium
    ativo = Column(Boolean, default=True, nullable=False)
    # Canais de aviso — cada um liga e desliga o seu
    telegram_chat_id = Column(String, default="", nullable=False)
    telegram_codigo = Column(String, default="", nullable=False)  # p/ conectar
    receber_telegram = Column(Boolean, default=True, nullable=False)
    email_alertas = Column(String, default="", nullable=False)
    receber_email = Column(Boolean, default=True, nullable=False)
    receber_push = Column(Boolean, default=True, nullable=False)
    criado_em = Column(DateTime, default=agora, nullable=False)
    perfis = relationship("PerfilBusca", back_populates="usuario")
    assinaturas_push = relationship("PushAssinatura", back_populates="usuario",
                                    cascade="all, delete-orphan")


class PushAssinatura(Base):
    """Um aparelho que aceitou receber notificações push (celular, PC)."""
    __tablename__ = "push_assinaturas"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False,
                        index=True)
    endpoint = Column(Text, unique=True, nullable=False)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
    rotulo = Column(String, default="")             # ex.: "Chrome no Android"
    criado_em = Column(DateTime, default=agora, nullable=False)
    usuario = relationship("Usuario", back_populates="assinaturas_push")


class PerfilBusca(Base):
    __tablename__ = "perfis_busca"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True,
                        index=True)
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
    criado_em = Column(DateTime, default=agora, nullable=False)
    usuario = relationship("Usuario", back_populates="perfis")
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
    coletado_em = Column(DateTime, default=agora)
    matches = relationship("PerfilMatch", back_populates="licitacao",
                           cascade="all, delete-orphan")


class PerfilMatch(Base):
    __tablename__ = "perfil_matches"
    id = Column(Integer, primary_key=True)
    perfil_id = Column(Integer, ForeignKey("perfis_busca.id"), nullable=False)
    licitacao_id = Column(Integer, ForeignKey("licitacoes.id"), nullable=False)
    data_match = Column(DateTime, default=agora, nullable=False)
    notificado = Column(Boolean, default=False, nullable=False)
    lido = Column(Boolean, default=False, nullable=False)
    favorito = Column(Boolean, default=False, nullable=False)
    status = Column(String, default="novo", nullable=False)
    termos = Column(String, default="")        # quais palavras do perfil casaram
    anotacao = Column(Text, default="")
    # Triagem sugerida pela IA (participar|analisar|descartar) — SUGESTÃO:
    # quem move o cartão é sempre o usuário.
    sugestao = Column(String, default="")
    sugestao_motivo = Column(String, default="")
    perfil = relationship("PerfilBusca", back_populates="matches")
    licitacao = relationship("Licitacao", back_populates="matches")
    __table_args__ = (UniqueConstraint("perfil_id", "licitacao_id",
                                       name="uq_perfil_licitacao"),)


class LicitacaoAlteracao(Base):
    """Mudança relevante numa licitação já conhecida — republicação,
    suspensão, prorrogação de prazo, mudança de valor ou de objeto.

    Detectada no upsert da coleta comparando campo a campo (nunca o payload
    bruto, que muda a cada resposta). Alimenta o aviso a quem acompanha o
    edital; `avisada` marca que o ciclo de aviso já a processou.
    """
    __tablename__ = "licitacao_alteracoes"
    id = Column(Integer, primary_key=True)
    licitacao_id = Column(Integer, ForeignKey("licitacoes.id"), nullable=False,
                          index=True)
    campo = Column(String, nullable=False)
    valor_antigo = Column(Text, default="")
    valor_novo = Column(Text, default="")
    detectada_em = Column(DateTime, default=agora, nullable=False)
    avisada = Column(Boolean, default=False, nullable=False, index=True)
    licitacao = relationship("Licitacao")


class ColetaLog(Base):
    __tablename__ = "coletas_log"
    id = Column(Integer, primary_key=True)
    inicio = Column(DateTime, nullable=False)
    fim = Column(DateTime)
    sucesso = Column(Boolean, default=False)
    qtd_novas = Column(Integer, default=0)
    qtd_erros = Column(Integer, default=0)
    detalhe_erro = Column(Text, default="")


class VigiaProblema(Base):
    """Problema de saúde do próprio radar em aberto (módulo vigia).

    Uma linha por problema ativo; resolver = apagar a linha. `avisado_em`
    é o anti-fadiga: avisa ao surgir, relembra no máximo uma vez por dia
    enquanto durar — e só é gravado quando algum canal aceitou a mensagem.
    """
    __tablename__ = "vigia_problemas"
    chave = Column(String, primary_key=True)
    titulo = Column(String, default="", nullable=False)
    detalhe = Column(Text, default="", nullable=False)
    desde = Column(DateTime, nullable=False)
    avisado_em = Column(DateTime, nullable=True)


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
    coletado_em = Column(DateTime, default=agora)


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
    baixado_em = Column(DateTime, default=agora)
    licitacao = relationship("Licitacao")


class EmpresaDados(Base):
    """Identidade da empresa de UMA conta — uma linha por usuário.

    Vive no BANCO, não no código (produto genérico): entra nas peças
    jurídicas como dado. Nada aqui é obrigatório; o que faltar sai na
    minuta como [PREENCHER]. Cada login é privado: a empresa de um
    usuário nunca aparece na minuta de outro.
    """
    __tablename__ = "empresa_dados"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True,
                        index=True)
    razao_social = Column(String, default="")
    cnpj = Column(String, default="")
    endereco = Column(String, default="")
    representante_nome = Column(String, default="")
    representante_cargo = Column(String, default="")
    atualizado_em = Column(DateTime, default=agora)


class Minuta(Base):
    """Peça jurídica gerada sob demanda (camada 3) — SEMPRE rascunho.

    Fica guardada com o custo: geração é por clique do usuário, o custo é
    atribuível e dá para limitar por plano no futuro (arquitetura §7).
    """
    __tablename__ = "minutas"
    id = Column(Integer, primary_key=True)
    licitacao_id = Column(Integer, ForeignKey("licitacoes.id"),
                          nullable=False, index=True)
    tipo = Column(String, default="impugnacao", nullable=False)
    texto = Column(Text, default="")
    modelo = Column(String, default="")
    custo_usd = Column(Float, default=0.0)
    criado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    criada_em = Column(DateTime, default=agora, nullable=False)
    licitacao = relationship("Licitacao")


class CasoPericial(Base):
    """Caso do perito documental: um caderno de CONCORRENTE sob exame.

    Diferente do dossiê (documentos da própria empresa), aqui cada caso é
    um conjunto avulso de documentos de terceiro, examinado para
    fundamentar recurso ou diligência. Recurso do plano premium."""
    __tablename__ = "casos_periciais"
    id = Column(Integer, primary_key=True)
    titulo = Column(String, nullable=False)          # ex.: "Empresa X — PE 24/2026"
    observacao = Column(Text, default="")
    criado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    criado_em = Column(DateTime, default=agora, nullable=False)


class DocumentoCaso(Base):
    """Um arquivo do caderno sob exame (PDF do concorrente)."""
    __tablename__ = "documentos_caso"
    id = Column(Integer, primary_key=True)
    caso_id = Column(Integer, ForeignKey("casos_periciais.id"),
                     nullable=False, index=True)
    nome = Column(String, nullable=False)
    caminho_local = Column(String, default="")       # relativo a data/
    criado_em = Column(DateTime, default=agora, nullable=False)


class LaudoPericial(Base):
    """Laudo do perito documental sobre um caso — sempre preliminar."""
    __tablename__ = "laudos_periciais"
    id = Column(Integer, primary_key=True)
    caso_id = Column(Integer, ForeignKey("casos_periciais.id"),
                     nullable=False, index=True)
    texto = Column(Text, default="")
    modelo = Column(String, default="")
    custo_usd = Column(Float, default=0.0)
    criado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    criado_em = Column(DateTime, default=agora, nullable=False)


class Parecer(Base):
    """Parecer completo do analista sobre um edital (camada 3, perícia).

    Diferente da ficha (ativo global, 1× por edital), o parecer cruza o
    edital com o DOSSIÊ da empresa no momento do clique — dossiê muda,
    parecer envelhece. Por isso cada geração é nova, sob demanda, com o
    custo gravado (dá para cobrar à parte, arquitetura §7).
    """
    __tablename__ = "pareceres"
    id = Column(Integer, primary_key=True)
    licitacao_id = Column(Integer, ForeignKey("licitacoes.id"),
                          nullable=False, index=True)
    texto = Column(Text, default="")
    modelo = Column(String, default="")
    custo_usd = Column(Float, default=0.0)
    criado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    criado_em = Column(DateTime, default=agora, nullable=False)
    licitacao = relationship("Licitacao")


class DocumentoEmpresa(Base):
    """Documento do dossiê da EMPRESA (certidão, atestado, balanço...).

    O dossiê é PRIVADO de quem subiu (`enviado_por`): cada login é uma
    empresa, e outro usuário nunca vê, baixa ou usa estes documentos —
    nem no checklist, nem no parecer. A validade é vigiada por
    CÓDIGO (arquitetura: 'IA lê, código calcula' — alerta de prazo errado
    encerra a confiança). `ultimo_aviso_dias` guarda o último marco avisado
    (30/15/7/3/1/0/-1=vencido) para não repetir aviso todo dia.
    """
    __tablename__ = "documentos_empresa"
    id = Column(Integer, primary_key=True)
    nome = Column(String, nullable=False)
    tipo = Column(String, default="Outro", nullable=False)
    caminho_local = Column(String, default="")      # relativo a data/
    validade = Column(String, nullable=True)        # ISO AAAA-MM-DD
    observacao = Column(Text, default="")
    enviado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    arquivado = Column(Boolean, default=False, nullable=False)
    ultimo_aviso_dias = Column(Integer, nullable=True)
    criado_em = Column(DateTime, default=agora, nullable=False)


class EditalFicha(Base):
    """Ficha estruturada do edital, extraída por IA — ativo GLOBAL.

    Processa uma vez, serve para todos (arquitetura, princípio 1): a ficha
    pertence ao edital, nunca a um usuário, e o custo de IA é por documento.
    `ficha_json` é o JSON validado da extração; `erro` preenchido = a última
    tentativa falhou (PDF sem texto, IA fora do ar) e a ficha pode ser
    regerada. O custo fica aqui E em data/ia_custos.jsonl.
    """
    __tablename__ = "edital_fichas"
    id = Column(Integer, primary_key=True)
    licitacao_id = Column(Integer, ForeignKey("licitacoes.id"), nullable=False,
                          unique=True, index=True)
    ficha_json = Column(Text, default="")
    erro = Column(Text, default="")
    modelo = Column(String, default="")
    versao_prompt = Column(String, default="")
    custo_usd = Column(Float, default=0.0)
    caracteres_lidos = Column(Integer, default=0)
    gerada_em = Column(DateTime, default=agora, nullable=False)
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
        "perfil_matches": [("termos", "TEXT DEFAULT ''"),
                           ("sugestao", "TEXT DEFAULT ''"),
                           ("sugestao_motivo", "TEXT DEFAULT ''")],
        "usuarios": [("plano", "TEXT DEFAULT 'padrao'")],
        "empresa_dados": [("usuario_id", "INTEGER")],
        "perfis_busca": [("modo_busca", "TEXT DEFAULT 'ou'"),
                         ("situacoes", "TEXT DEFAULT '[]'"),
                         ("somente_vigentes", "BOOLEAN DEFAULT 1"),
                         ("frequencia", "TEXT DEFAULT 'diario'"),
                         ("intervalo_horas", "INTEGER DEFAULT 3"),
                         ("dia_semana", "INTEGER DEFAULT 0"),
                         ("dia_mes", "INTEGER DEFAULT 1"),
                         ("mes_ano", "INTEGER DEFAULT 1"),
                         ("hora_envio", "TEXT DEFAULT ''"),
                         ("ultimo_envio", "DATETIME"),
                         ("usuario_id", "INTEGER")],
    }
    indices = [
        # Consultas mais quentes do despacho de alertas e do funil
        "CREATE INDEX IF NOT EXISTS ix_matches_perfil_notificado "
        "ON perfil_matches (perfil_id, notificado)",
        "CREATE INDEX IF NOT EXISTS ix_matches_status "
        "ON perfil_matches (status)",
        "CREATE INDEX IF NOT EXISTS ix_licitacoes_fonte ON licitacoes (fonte)",
    ]
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
        for indice in indices:
            con.exec_driver_sql(indice)
        con.commit()
    _migrar_para_multiusuario()


def _adotar_orfaos(sessao, admin_id):
    """Dado de empresa sem dono (anterior à privacidade por conta) passa
    ao primeiro administrador — era ele quem o via e mantinha."""
    for modelo, coluna in ((DocumentoEmpresa, DocumentoEmpresa.enviado_por),
                           (CasoPericial, CasoPericial.criado_por),
                           (LaudoPericial, LaudoPericial.criado_por),
                           (Parecer, Parecer.criado_por),
                           (Minuta, Minuta.criado_por),
                           (EmpresaDados, EmpresaDados.usuario_id)):
        sessao.query(modelo).filter(coluna.is_(None)).update(
            {coluna.key: admin_id}, synchronize_session=False)


def _migrar_para_multiusuario():
    """Instalação antiga (senha única no .env) vira multiusuário sem perder
    nada: o dono atual vira o primeiro administrador, herda todos os perfis
    e os canais de aviso que estavam no .env (chat do Telegram, e-mail).

    Idempotente: só age quando não existe nenhum usuário ainda.
    """
    from .config import config
    from .usuarios import gerar_hash
    sessao = Sessao()
    try:
        if sessao.query(Usuario).count():
            # Já é multiusuário; só garante que nenhum perfil ficou órfão
            # (ex.: criado por versão antiga entre migrações).
            admin = (sessao.query(Usuario).filter_by(papel="admin")
                     .order_by(Usuario.id).first())
            if admin:
                sessao.query(PerfilBusca).filter(
                    PerfilBusca.usuario_id.is_(None)).update(
                    {"usuario_id": admin.id})
                _adotar_orfaos(sessao, admin.id)
                sessao.commit()
            return
        if not config.APP_SENHA:
            return          # instalação nova: a tela /registrar cria o admin
        # Só o primeiro endereço, em minúsculas: o login compara em
        # minúsculas e "Paulo@Gmail.com" nunca casaria.
        email = ((config.EMAIL_DESTINO or "").split(",")[0].strip().lower()
                 or "admin@radar.local")
        admin = Usuario(
            nome="Administrador", email=email,
            senha_hash=gerar_hash(config.APP_SENHA), papel="admin",
            telegram_chat_id=config.TELEGRAM_CHAT_ID or "",
            email_alertas=config.EMAIL_DESTINO or "")
        sessao.add(admin)
        sessao.flush()
        sessao.query(PerfilBusca).filter(
            PerfilBusca.usuario_id.is_(None)).update({"usuario_id": admin.id})
        sessao.commit()
    finally:
        sessao.close()
