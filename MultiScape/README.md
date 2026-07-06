# Multi Escape ERP

ERP desktop para **oficinas mecânicas** e pequenas empresas automotivas.

## Estrutura (separada do sistema logístico)

```
MultiScape/
├── files/                    # Código-fonte e build (.exe)
│   ├── sistema_oficina_v2.py
│   ├── modulo_licenca_trial.py
│   └── construir_exe.bat
├── modulo_licenca_trial.py   # Cópia na raiz do produto
├── scripts/
│   └── gerar_licenca_trial.py
└── trial_distribuicao/
    └── releases/             # ZIP trial publicado no GitHub

docs/multiscape/              # Landing publicada (GitHub Pages)
landing-multiscape/           # Cópia-fonte da landing
```

## Site publicado

- **Logística:** https://adrianomontes.github.io/sistema-gestao-logistico/
- **Oficinas:** https://adrianomontes.github.io/sistema-gestao-logistico/multiscape/

## Trial 30 dias

1. Cliente solicita na landing com e-mail corporativo.
2. Adicione o e-mail em `.github/access-control-multiscape.json`.
3. Gere licença: `py scripts/gerar_licenca_trial.py --email cliente@oficina.com.br --empresa "Oficina X"`
4. Monte o ZIP com `MultiEscape_ERP_Trial.exe` + `trial.lic` em `trial_distribuicao/releases/MultiEscapeTrial-v1.zip`.

## Build do executável

```bat
cd files
construir_exe.bat
```

Para edição trial, renomeie o exe para conter `Trial` no nome ou inclua `trial.lic` na pasta.

## Origem

Projeto desenvolvido a partir de `C:\Users\adria\OneDrive\Desktop\MultiScape`.
