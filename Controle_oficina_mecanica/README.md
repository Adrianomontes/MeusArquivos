# Controle de Oficina Mecânica

ERP desktop genérico para **oficinas mecânicas** e pequenas empresas automotivas.

## Estrutura (separada do sistema logístico)

```
Controle_oficina_mecanica/
├── files/                         # Código-fonte e build (.exe)
├── scripts/gerar_licenca_trial.py
└── trial_distribuicao/releases/   # ZIP trial

docs/controle-oficina-mecanica/    # Landing (GitHub Pages)
landing-controle-oficina-mecanica/ # Cópia-fonte
```

## Site

- **Logística:** https://adrianomontes.github.io/sistema-gestao-logistico/
- **Oficina:** https://adrianomontes.github.io/sistema-gestao-logistico/controle-oficina-mecanica/

## Trial 30 dias

1. Cliente solicita na landing com e-mail corporativo.
2. Adicione o e-mail em `.github/access-control-oficina.json`.
3. `py Controle_oficina_mecanica\scripts\gerar_licenca_trial.py --email cliente@oficina.com.br --empresa "Oficina"`
4. ZIP: `ControleOficina_Trial.exe` + `trial.lic` → `trial_distribuicao/releases/ControleOficinaTrial-v1.zip`

## Build

```bat
cd Controle_oficina_mecanica\files
construir_exe.bat
```

Executável: `dist\ControleOficina.exe`
