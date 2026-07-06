═══════════════════════════════════════════════════════════════════════
      MULTI ESCAPE ERP v1.2 — Guia de Build e Distribuição
═══════════════════════════════════════════════════════════════════════

ARQUIVOS DESTE PACOTE
───────────────────────────────────────────────────────────────────────
  sistema_oficina_v2.py   → Código-fonte principal do sistema
  construir_exe.bat       → Script de build com um clique (rode este!)
  MultiEscape.spec        → Configuração do PyInstaller
  versao_info.txt         → Informações de versão do .exe
  README_BUILD.txt        → Este arquivo

═══════════════════════════════════════════════════════════════════════
PASSO A PASSO PARA GERAR O .EXE
═══════════════════════════════════════════════════════════════════════

PRÉ-REQUISITO: Python 3.7 ou superior instalado na SUA máquina.
  → https://www.python.org/downloads/
  → IMPORTANTE: marque "Add Python to PATH" na instalação

  1. Coloque TODOS os arquivos acima na mesma pasta
  2. Clique duas vezes em:  construir_exe.bat
  3. Aguarde (1 a 3 minutos — o script instala tudo automaticamente)
  4. O executável é gerado em:  dist\MultiEscape_ERP.exe
  5. Uma janela do Explorer abrirá automaticamente na pasta dist\

═══════════════════════════════════════════════════════════════════════
O QUE O SCRIPT FAZ AUTOMATICAMENTE
═══════════════════════════════════════════════════════════════════════

  [1] Verifica se Python 3.7+ está instalado e no PATH
  [2] Atualiza o pip (gerenciador de pacotes)
  [3] Instala PyInstaller (empacotador de executáveis)
  [4] Instala reportlab (geração de PDF)
  [5] Instala Pillow (logos de marcas de veículos)
  [6] Executa o PyInstaller com as configurações otimizadas
  [7] Copia os arquivos de logos para a pasta dist\
  [8] Abre a pasta dist\ no Explorer ao final

═══════════════════════════════════════════════════════════════════════
PARA DISTRIBUIR AO DONO DA OFICINA
═══════════════════════════════════════════════════════════════════════

Após o build, envie a pasta  dist\  inteira contendo:

  dist\
  ├── MultiEscape_ERP.exe     ← Executável principal (clique duplo)
  └── logos_marcas\           ← Logos de marcas (se já baixados)
       ├── fiat.png
       ├── volkswagen.png
       └── ... (gerados automaticamente ao usar o sistema)

OPÇÃO 1 — Envio por email / WhatsApp:
  → Compacte a pasta dist\ em .zip e envie
  → O destinatário descompacta e clica em MultiEscape_ERP.exe

OPÇÃO 2 — Pendrive:
  → Copie a pasta dist\ para o pendrive
  → No computador destino, copie para o Desktop e execute

OPÇÃO 3 — Pasta na rede / nuvem:
  → Coloque dist\ em Google Drive / OneDrive e compartilhe o link

═══════════════════════════════════════════════════════════════════════
REQUISITOS NA MÁQUINA DO DESTINATÁRIO
═══════════════════════════════════════════════════════════════════════

  ✅ Windows 7, 8, 8.1, 10 ou 11 (32 ou 64 bits)
  ✅ NÃO precisa instalar Python
  ✅ NÃO precisa instalar nenhum outro programa
  ✅ NÃO precisa de internet para usar (exceto para baixar logos de marcas)
  ✅ O banco de dados (sistema_oficina.db) é criado automaticamente
     na mesma pasta do .exe na primeira execução

TAMANHO ESTIMADO DO EXECUTÁVEL
  Sem Pillow/reportlab: ~25 MB
  Com Pillow + reportlab: ~45 MB

═══════════════════════════════════════════════════════════════════════
ONDE O BANCO DE DADOS É SALVO
═══════════════════════════════════════════════════════════════════════

  O arquivo sistema_oficina.db é criado AUTOMATICAMENTE na mesma pasta
  onde o MultiEscape_ERP.exe estiver.

  ATENÇÃO: Não mova o .exe de pasta depois de começar a usar o sistema,
  pois o banco de dados ficará para trás!

  BACKUP: Faça cópia periódica do arquivo sistema_oficina.db.

═══════════════════════════════════════════════════════════════════════
POSSÍVEIS ERROS E SOLUÇÕES
═══════════════════════════════════════════════════════════════════════

ERRO: "Python nao encontrado no PATH"
  → Reinstale o Python e marque "Add Python to PATH"
  → Ou adicione manualmente: C:\Users\SEU_USUARIO\AppData\Local\Programs\Python\Python3X\

ERRO: "Falha ao instalar PyInstaller"
  → Verifique a conexão com a internet
  → Tente abrir o CMD como Administrador e rodar:
    pip install pyinstaller

ERRO: Antivírus bloqueia o .exe gerado
  → Normal — executáveis gerados por PyInstaller às vezes são flagrados
  → Adicione uma exceção no antivírus para a pasta dist\
  → Ou desative temporariamente durante o uso (é seguro — você criou o código)

ERRO: Tela preta ao abrir na máquina destino
  → Verifique se o Windows está atualizado
  → Tente copiar para C:\MultiEscape\ e executar de lá (evita problemas de permissão)

ERRO: "The application was unable to start correctly (0xc000007b)"
  → Visual C++ Redistributable não instalado na máquina destino
  → Baixe e instale: https://aka.ms/vs/17/release/vc_redist.x64.exe

═══════════════════════════════════════════════════════════════════════
PERSONALIZAÇÃO ANTES DO BUILD
═══════════════════════════════════════════════════════════════════════

ÍCONE PERSONALIZADO:
  1. Crie ou baixe um arquivo .ico (ícone Windows)
  2. Salve como icone_multiescap.ico na mesma pasta
  3. No arquivo MultiEscape.spec, descomente a linha:
     # icon='icone_multiescap.ico',
  4. Execute construir_exe.bat novamente

NOME DO EXECUTÁVEL:
  No arquivo MultiEscape.spec, altere a linha:
    name='MultiEscape_ERP',
  Para o nome desejado, ex:
    name='SistemaOficina',

═══════════════════════════════════════════════════════════════════════
  Multi Escape ERP v1.2 — Build System
  Gerado automaticamente pelo assistente de desenvolvimento
═══════════════════════════════════════════════════════════════════════
