# Sistema Logístico Integrado

Plataforma **white-label** de controle logístico ponta a ponta — do pedido ao indicador, com rastreio por NF e telas integradas.

Ideal para distribuidores, centros de distribuição, operadores logísticos e consultorias que desejam oferecer gestão logística profissional sem desenvolver do zero.

## O que o sistema cobre

| Fase | Capacidades |
|------|-------------|
| Pedidos & estoque | Saldo, curva ABC, integração ERP |
| WMS | Separação, apontamento de posição, embalagem, etiquetas |
| Faturamento | NF-e conciliada × expedição × entrega |
| Rotas & clusters | CEP/IBGE, mesorregiões, montagem de carga |
| Expedição | Multimodal: próprio, contratadas, FOB, CIF |
| Canhotos | Assinatura mobile, WhatsApp, baixa por NF |
| Exceções | Devoluções, ocorrências, coletas FOB |
| Gestão | Torre de controle, TVs, KPIs, lead times |

## Landing page estática (site comercial)

Pasta separada para hospedar no site ou GitHub Pages, **sem Flask**:

```
landing-sistema-logistico/
├── index.html
├── assets/          # fluxogramas SVG
└── COMO-PUBLICAR.txt
```

Abra `landing-sistema-logistico/index.html` no navegador ou publique a pasta no seu servidor.


```powershell
cd Controle_ocorrencias
pip install -r requisitos.txt
python app.py
```

- **Página comercial (pública):** http://localhost:5000/apresentacao  
- **Manual operacional:** http://localhost:5000/manual  
- **Portal:** http://localhost:5000/portal_operacional  

## Personalização white-label

Variáveis de ambiente:

| Variável | Descrição |
|----------|-----------|
| `NOME_SISTEMA` | Nome exibido no portal e manual |
| `TAGLINE_SISTEMA` | Frase de posicionamento comercial |
| `logo_sistema.png` | Logo na pasta do app (`/cdn/logo_sistema`) |

Build do executável: `build_executavel.bat`

## Repositório

Este repositório também contém outros arquivos pessoais em `MeusArquivos/`. O produto logístico está em `Controle_ocorrencias/`.
