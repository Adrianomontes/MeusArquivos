# -*- coding: utf-8 -*-
"""Catálogo único de módulos do portal — usado na tela inicial e na API de links."""

MODULOS_CATALOGO = [
    {
        "id": "operacional",
        "titulo": "Operacional — dia a dia",
        "icone": "⚡",
        "cor": "#10b981",
        "itens": [
            {"url": "/devolucao", "titulo": "Devoluções / Ocorrências", "icone": "📝", "desc": "Lançamento no pátio com NF, fotos e conferência."},
            {"url": "/formulario", "titulo": "Central Coletas FOB", "icone": "🚛", "desc": "Agendamento FOB com farol de prazo e minuta de e-mail."},
            {"url": "/registrar_coleta", "titulo": "Coleta Rápida", "icone": "➕", "desc": "Formulário simplificado de agendamento de coleta."},
            {"url": "/baixa_entrega_mobile", "titulo": "Baixa Manual de Entrega", "icone": "📥", "desc": "Registro de entrega com assinatura do recebedor."},
            {"url": "/buscar_nf_baixa", "titulo": "Efetuar Baixa por NF", "icone": "✅", "desc": "Busca NF e conclui baixa operacional."},
            {"url": "/gestor_emails", "titulo": "Triagem de E-mails", "icone": "📬", "desc": "Classificação e tratativa de e-mails recebidos."},
            {"url": "/gerenciar_motivos", "titulo": "Motivos de Ocorrência", "icone": "⚙️", "desc": "Cadastro dos motivos usados nos formulários."},
        ],
    },
    {
        "id": "canhotos",
        "titulo": "Canhotos e entregas",
        "icone": "🧾",
        "cor": "#8b5cf6",
        "itens": [
            {"url": "/validar_canhoto", "titulo": "Validar Canhotos (ZIP)", "icone": "📸", "desc": "Esteira de conferência de canhotos digitalizados."},
            {"url": "/canhoto", "titulo": "Tela de Assinatura", "icone": "✍️", "desc": "Captura de assinatura de canhoto."},
            {"url": "/canhoto_motorista", "titulo": "Canhoto Motorista", "icone": "🚚", "desc": "Interface mobile/offline para motoristas."},
            {"url": "/canhotos_assinados", "titulo": "Canhotos WhatsApp", "icone": "📱", "desc": "Canhotos recebidos e assinados via WhatsApp."},
            {"url": "/sistema_canhotos", "titulo": "Lista Local de Canhotos", "icone": "📋", "desc": "Consulta da base local de canhotos."},
            {"url": "/gerador_etiquetas", "titulo": "Gerador de Etiquetas", "icone": "🏷️", "desc": "Emissão rápida de etiquetas operacionais."},
        ],
    },
    {
        "id": "gestao_vista",
        "titulo": "Gestão à vista / TV",
        "icone": "📺",
        "cor": "#a855f7",
        "itens": [
            {"url": "/monitor", "titulo": "Painel TV Rotativo", "icone": "🚀", "desc": "Carrossel de telas para monitor/TV.", "nova_aba": True},
            {"url": "/torre_controle", "titulo": "Torre de Controle", "icone": "🗼", "desc": "Dashboard consolidado operacional."},
            {"url": "/auditoria_torre", "titulo": "Auditoria de Frota", "icone": "🕵️", "desc": "Carrossel de auditoria logística."},
            {"url": "/painel_indicadores", "titulo": "Indicadores Rotativos", "icone": "📊", "desc": "KPIs operacionais em tempo real."},
            {"url": "/painel_pracas", "titulo": "Painel de Praças", "icone": "🗺️", "desc": "Visão por praça de atendimento."},
            {"url": "/tv_pracas", "titulo": "TV Praças de Atendimento", "icone": "📡", "desc": "Modo TV para praças.", "nova_aba": True},
            {"url": "/tv_coletas_fob", "titulo": "TV Coletas FOB", "icone": "🚛", "desc": "Painel TV de coletas pendentes.", "nova_aba": True},
            {"url": "/tv_devolucoes", "titulo": "TV Devoluções", "icone": "🔄", "desc": "Painel TV de devoluções.", "nova_aba": True},
            {"url": "/tv_canhotos_whatsapp", "titulo": "TV Canhotos WhatsApp", "icone": "📺", "desc": "Painel TV de canhotos.", "nova_aba": True},
        ],
    },
    {
        "id": "relatorios",
        "titulo": "Relatórios e bases",
        "icone": "📊",
        "cor": "#6366f1",
        "itens": [
            {"url": "/relatorio", "titulo": "Base Coletas FOB", "icone": "🗃️", "desc": "Histórico e exportação de coletas FOB."},
            {"url": "/relatorio_coletas", "titulo": "Coletas Pendentes", "icone": "🚚", "desc": "Monitoramento de retiradas pendentes."},
            {"url": "/relatorio_faturamento", "titulo": "Faturamento Conciliado", "icone": "💸", "desc": "Conciliação faturamento × entregas."},
            {"url": "/custos_pessoais", "titulo": "Custos Pessoais", "icone": "R$", "desc": "Controle de despesas, créditos, parcelamentos e previsões."},
            {"url": "/relatorio_faturamento_local", "titulo": "Faturamento Local", "icone": "💰", "desc": "Painel local de faturamento."},
            {"url": "/relatorio_expedicao", "titulo": "Notas Expedidas", "icone": "📦", "desc": "Consulta de notas expedidas."},
            {"url": "/relatorio_transportadoras", "titulo": "Lista de Transportadoras", "icone": "📋", "desc": "Consulta e exportação de transportadoras."},
            {"url": "/auditar_apis_nomus", "titulo": "Auditoria APIs Nomus", "icone": "🔎", "desc": "Conferência de integrações Nomus ERP."},
        ],
    },
    {
        "id": "estoque",
        "titulo": "Estoque e inventário",
        "icone": "📦",
        "cor": "#0284c7",
        "itens": [
            {"url": "/ver_estoque", "titulo": "Saldo de Estoque", "icone": "📦", "desc": "Consulta avançada de saldo e busca."},
            {"url": "/curva_abc", "titulo": "Curva ABC", "icone": "📈", "desc": "Análise ABC / Pareto de inventário."},
            {"url": "/espiao", "titulo": "Espião de Inventário", "icone": "🔍", "desc": "Rastreamento e conferência de itens."},
            {"url": "/lancar_contagem", "titulo": "Lançar Contagem", "icone": "📝", "desc": "Registro de contagem física."},
            {"url": "/logistica/espiao", "titulo": "Espião Base Bruta", "icone": "🗄️", "desc": "Visão bruta da base logística."},
            {"url": "/gerenciar_ean", "titulo": "Gerenciar EAN", "icone": "🏷️", "desc": "Cadastro de códigos EAN de itens."},
        ],
    },
    {
        "id": "roteirizador",
        "titulo": "Roteirizador",
        "icone": "🗺️",
        "cor": "#0ea5e9",
        "itens": [
            {"url": "/roteirizador", "titulo": "Início do Roteirizador", "icone": "🗺️", "desc": "Hub com acesso às telas de rotas, auditoria e montagem."},
            {"url": "/roteirizador/cadastro", "titulo": "Cadastro de Rotas", "icone": "📋", "desc": "UF, faixas de CEP (cabeça 3 dígitos), transportadoras e salvar rota."},
            {"url": "/roteirizador/auditoria", "titulo": "Auditoria de Faixas", "icone": "🔍", "desc": "Clusters CEP × mesorregião × transportadoras direcionadas."},
            {"url": "/roteirizador/montagem", "titulo": "Montagem da Saída", "icone": "🚚", "desc": "Faturamento, rotas automáticas, drag-and-drop e saída do dia."},
        ],
    },
    {
        "id": "cadastros",
        "titulo": "Cadastros e administração",
        "icone": "🗂️",
        "cor": "#f59e0b",
        "itens": [
            {"url": "/gerenciar_transportadoras", "titulo": "Transportadoras", "icone": "🚛", "desc": "Cadastro mestre de transportadoras."},
            {"url": "/gerenciar_usuarios", "titulo": "Usuários e Acessos", "icone": "🔐", "desc": "Perfis, logins e permissões (ADMIN).", "admin_only": True},
            {"url": "/manual", "titulo": "Manual do Usuário", "icone": "📖", "desc": "Documentação operacional do sistema."},
        ],
    },
    {
        "id": "portal",
        "titulo": "Portal e acesso",
        "icone": "🏢",
        "cor": "#38bdf8",
        "itens": [
            {"url": "/portal_operacional", "titulo": "Portal Operacional", "icone": "🏢", "desc": "Shell principal com menu lateral.", "externo": True},
            {"url": "/login", "titulo": "Tela de Login", "icone": "🔒", "desc": "Autenticação de operadores.", "externo": True},
            {"url": "/tela_boas_vindas", "titulo": "Menu Inicial", "icone": "🏠", "desc": "Esta tela — catálogo de módulos."},
        ],
    },
]


def listar_modulos_flat():
    """Retorna lista plana de todos os módulos com grupo."""
    flat = []
    for grupo in MODULOS_CATALOGO:
        for item in grupo["itens"]:
            flat.append({
                **item,
                "grupo_id": grupo["id"],
                "grupo_titulo": grupo["titulo"],
            })
    return flat
