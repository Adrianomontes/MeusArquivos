# Controle de acesso — Animo Serviços Administrativos

**Diretor:** Adriano Montes  
**Contato:** adrianomontes55@gmail.com

## Política

Somente **e-mails autorizados** podem:

- Ser convidados como colaboradores do repositório
- Clonar ou baixar o código (repositório privado)
- Baixar releases e executáveis publicados no GitHub

A lista oficial está em [`.github/access-control.json`](.github/access-control.json).

## Passo 1 — Tornar o repositório privado (obrigatório)

No GitHub: **Settings → General → Danger Zone → Change repository visibility → Private**

Enquanto o repositório for público, qualquer pessoa pode baixar o código sem restrição de e-mail.

## Passo 2 — Adicionar cliente autorizado

1. Confirme que o e-mail do cliente está em `emails_autorizados` no JSON
2. **Settings → Collaborators → Add people**
3. Convide pelo **usuário GitHub** ou e-mail vinculado à conta dele
4. Permissão recomendada: **Read** (só download) ou **Write** (se for parceiro de implantação)

## Passo 3 — Publicar executável (release)

1. Gere o `.exe` com `build_executavel.bat`
2. No GitHub: **Releases → Draft a new release**
3. Anexe `SistemaLogistico.exe` — visível apenas para colaboradores (repo privado)
4. O workflow `controle-acesso-repositorio.yml` bloqueia releases de usuários não autorizados

## Passo 4 — Incluir novo e-mail autorizado

Edite `.github/access-control.json`:

```json
"emails_autorizados": [
  "adrianomontes55@gmail.com",
  "cliente@empresa.com.br"
]
```

Faça commit e push. A landing page usa a mesma lista para a área de download.

## Landing page (verificação de e-mail)

A seção **Download** em `landing-sistema-logistico/index.html` valida o e-mail contra a lista antes de exibir o link de releases.

> A verificação na página é informativa. A proteção real é o **repositório privado** + convite de colaborador.
