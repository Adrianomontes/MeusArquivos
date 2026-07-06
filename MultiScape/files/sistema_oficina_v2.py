import os
import re
import sys
import shutil
import sqlite3
import logging
import platform
import subprocess
import threading
import urllib.parse
import urllib.request
from calendar import monthrange
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ══════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO GLOBAL DE COMPATIBILIDADE
# Populado pela TelaCompatibilidade antes de abrir o app principal.
# ══════════════════════════════════════════════════════════════════════════
CONFIG = {
    "python_ok":    False,
    "python_ver":   "",
    "windows_ver":  "",
    "fonte_ui":     "Arial",        # fallback seguro para todas as versões
    "fonte_mono":   "Courier New",  # fallback seguro para todas as versões
    "reportlab":    False,
    "pillow":       False,
    "tema_ttk":     "clam",         # tema mais compatível
    "dpi_aware":    False,
}


# ══════════════════════════════════════════════════════════════════════════
# TELA DE SPLASH / COMPATIBILIDADE
# ══════════════════════════════════════════════════════════════════════════
class TelaCompatibilidade:
    """
    Janela que aparece antes do app principal.
    Detecta ambiente, instala dependências opcionais e configura fallbacks.
    """

    # Versão mínima do Python suportada
    PY_MIN = (3, 7)

    # Fontes por ordem de preferência (a primeira disponível é usada)
    FONTES_UI   = ["Segoe UI", "Calibri", "Tahoma", "Arial"]
    FONTES_MONO = ["Consolas", "Lucida Console", "Courier New", "Courier"]

    # Paleta da tela de splash
    C_BG      = "#1B2631"
    C_CARD    = "#212F3D"
    C_ACENTO  = "#2E86C1"
    C_VERDE   = "#27AE60"
    C_AMARELO = "#F39C12"
    C_VERMELHO= "#C0392B"
    C_TEXTO   = "#ECF0F1"
    C_MUTED   = "#7F8C8D"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Multi Escape ERP — Verificando Compatibilidade")
        self.root.configure(bg=self.C_BG)
        self.root.resizable(False, False)
        self._continuar = False
        self._itens_check = []   # (texto_label, icone_label, resultado_label)
        self._construir_ui()
        self._centralizar()

    def _centralizar(self):
        self.root.update_idletasks()
        w, h = 520, 540
        x = (self.root.winfo_screenwidth()  - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _construir_ui(self):
        # ── Cabeçalho ────────────────────────────────────────────────────
        frame_top = tk.Frame(self.root, bg=self.C_ACENTO, height=80)
        frame_top.pack(fill="x")
        frame_top.pack_propagate(False)

        tk.Label(frame_top, text="🔧  MULTI ESCAPE ERP",
                 font=("Arial", 16, "bold"),
                 bg=self.C_ACENTO, fg="white").pack(pady=(14, 2))
        tk.Label(frame_top, text="Verificando compatibilidade do ambiente...",
                 font=("Arial", 9),
                 bg=self.C_ACENTO, fg="#D6EAF8").pack()

        # ── Área de checks ────────────────────────────────────────────────
        frame_checks = tk.Frame(self.root, bg=self.C_CARD,
                                relief="flat", bd=0)
        frame_checks.pack(fill="both", expand=True, padx=20, pady=15)

        self._frame_checks = frame_checks

        # Itens que serão verificados
        self._itens = [
            ("python",    "🐍  Versão do Python"),
            ("windows",   "🖥️  Sistema Operacional Windows"),
            ("tkinter",   "🪟  Interface Gráfica (tkinter)"),
            ("sqlite",    "🗄️  Banco de Dados (SQLite)"),
            ("fontes",    "🔤  Fontes do Sistema"),
            ("reportlab", "📄  Geração de PDF (reportlab)"),
            ("pillow",    "🖼️  Logos de Marcas (Pillow)"),
            ("internet",  "🌐  Conexão para Logos (opcional)"),
        ]

        self._labels = {}
        for chave, texto in self._itens:
            f = tk.Frame(frame_checks, bg=self.C_CARD)
            f.pack(fill="x", padx=12, pady=4)

            icone = tk.Label(f, text="⏳", font=("Arial", 12),
                             bg=self.C_CARD, fg=self.C_AMARELO, width=3)
            icone.pack(side="left")

            lbl_txt = tk.Label(f, text=texto, font=("Arial", 10),
                               bg=self.C_CARD, fg=self.C_TEXTO, anchor="w")
            lbl_txt.pack(side="left", fill="x", expand=True, padx=6)

            lbl_res = tk.Label(f, text="verificando...", font=("Arial", 9),
                               bg=self.C_CARD, fg=self.C_MUTED, anchor="e")
            lbl_res.pack(side="right", padx=4)

            self._labels[chave] = (icone, lbl_res)

        # ── Barra de progresso ─────────────────────────────────────────────
        self._progress_frame = tk.Frame(self.root, bg=self.C_BG)
        self._progress_frame.pack(fill="x", padx=20, pady=(0,6))

        self._progress_bar = ttk.Progressbar(self._progress_frame,
                                              mode="determinate", length=480)
        self._progress_bar.pack(fill="x")

        # ── Mensagem de status ─────────────────────────────────────────────
        self._lbl_status = tk.Label(self.root, text="Iniciando verificação...",
                                     font=("Arial", 8, "italic"),
                                     bg=self.C_BG, fg=self.C_MUTED)
        self._lbl_status.pack(pady=(0,4))

        # ── Painel de instalação opcional ─────────────────────────────────
        self._frame_instalar = tk.Frame(self.root, bg=self.C_BG)
        self._frame_instalar.pack(fill="x", padx=20, pady=4)
        # (preenchido dinamicamente se faltarem pacotes)

        # ── Botões ─────────────────────────────────────────────────────────
        frame_btns = tk.Frame(self.root, bg=self.C_BG)
        frame_btns.pack(fill="x", padx=20, pady=(6,14))

        self._btn_continuar = tk.Button(
            frame_btns,
            text="▶  Abrir Sistema",
            font=("Arial", 10, "bold"),
            bg=self.C_VERDE, fg="white",
            relief="flat", bd=0,
            padx=20, pady=8,
            state="disabled",
            cursor="hand2",
            command=self._ao_continuar
        )
        self._btn_continuar.pack(side="right", padx=4)

        self._btn_fechar = tk.Button(
            frame_btns,
            text="✕  Fechar",
            font=("Arial", 10),
            bg=self.C_VERMELHO, fg="white",
            relief="flat", bd=0,
            padx=16, pady=8,
            cursor="hand2",
            command=self.root.destroy
        )
        self._btn_fechar.pack(side="right", padx=4)

    # ── Helpers de atualização de UI (thread-safe) ────────────────────────
    def _set_check(self, chave, icone, texto_res, cor_icone, cor_res=None):
        def _upd():
            if chave in self._labels:
                ic, res = self._labels[chave]
                ic.config(text=icone, fg=cor_icone)
                res.config(text=texto_res, fg=cor_res or self.C_MUTED)
        self.root.after(0, _upd)

    def _set_status(self, msg):
        self.root.after(0, lambda: self._lbl_status.config(text=msg))

    def _set_progress(self, val):
        self.root.after(0, lambda: self._progress_bar.config(value=val))

    # ── Checagens ─────────────────────────────────────────────────────────
    def _checar_python(self):
        ver = sys.version_info
        ver_str = f"{ver.major}.{ver.minor}.{ver.micro}"
        CONFIG["python_ver"] = ver_str
        if (ver.major, ver.minor) >= (3, 9):
            self._set_check("python", "✅", f"Python {ver_str} — Excelente",
                            self.C_VERDE, self.C_VERDE)
            CONFIG["python_ok"] = True
        elif (ver.major, ver.minor) >= self.PY_MIN:
            self._set_check("python", "✅", f"Python {ver_str} — Compatível",
                            self.C_VERDE, self.C_VERDE)
            CONFIG["python_ok"] = True
        elif ver.major == 3 and ver.minor >= 6:
            self._set_check("python", "⚠️", f"Python {ver_str} — Funcional (recomendado 3.7+)",
                            self.C_AMARELO, self.C_AMARELO)
            CONFIG["python_ok"] = True
        else:
            self._set_check("python", "❌", f"Python {ver_str} — Muito antigo! Atualize.",
                            self.C_VERMELHO, self.C_VERMELHO)
            CONFIG["python_ok"] = False

    def _checar_windows(self):
        sistema = platform.system()
        versao  = platform.version()
        release = platform.release()

        if sistema == "Windows":
            # Detecta build para classificar versão
            try:
                build = int(versao.split(".")[2])
            except Exception:
                build = 0

            if build >= 22000:
                nome = "Windows 11"
                cor  = self.C_VERDE
                ic   = "✅"
            elif build >= 10240:
                nome = "Windows 10"
                cor  = self.C_VERDE
                ic   = "✅"
            elif release == "8.1":
                nome = "Windows 8.1"
                cor  = self.C_AMARELO
                ic   = "⚠️"
            elif release == "8":
                nome = "Windows 8"
                cor  = self.C_AMARELO
                ic   = "⚠️"
            elif release == "7":
                nome = "Windows 7"
                cor  = self.C_AMARELO
                ic   = "⚠️"
            else:
                nome = f"Windows {release}"
                cor  = self.C_AMARELO
                ic   = "⚠️"

            CONFIG["windows_ver"] = nome
            # Windows 7/8: Segoe UI disponível mas DPI pode variar
            self._set_check("windows", ic, f"{nome}  (build {build})", cor, cor)

            # Configurações específicas por versão
            if build < 9600:   # anterior ao Win 8.1
                CONFIG["tema_ttk"] = "clam"   # mais estável em Win7/8
        else:
            CONFIG["windows_ver"] = f"{sistema} {release}"
            self._set_check("windows", "⚠️",
                            f"{sistema} {release} — não testado oficialmente",
                            self.C_AMARELO, self.C_AMARELO)

    def _checar_tkinter(self):
        try:
            import tkinter
            ver = tkinter.TkVersion
            if ver >= 8.6:
                self._set_check("tkinter", "✅", f"Tk {ver:.1f} — Completo",
                                self.C_VERDE, self.C_VERDE)
            else:
                self._set_check("tkinter", "⚠️", f"Tk {ver:.1f} — Funcional (recomendado 8.6+)",
                                self.C_AMARELO, self.C_AMARELO)
        except Exception as e:
            self._set_check("tkinter", "❌", f"Erro: {e}",
                            self.C_VERMELHO, self.C_VERMELHO)

    def _checar_sqlite(self):
        try:
            ver = sqlite3.sqlite_version
            self._set_check("sqlite", "✅", f"SQLite {ver} — Pronto",
                            self.C_VERDE, self.C_VERDE)
        except Exception as e:
            self._set_check("sqlite", "❌", f"Erro: {e}",
                            self.C_VERMELHO, self.C_VERMELHO)

    def _checar_fontes(self):
        """Detecta a melhor fonte disponível e configura CONFIG."""
        import tkinter.font as tkfont
        try:
            familias = set(tkfont.families())
        except Exception:
            familias = set()

        for f in self.FONTES_UI:
            if f in familias or f.lower() in {x.lower() for x in familias}:
                CONFIG["fonte_ui"] = f
                break

        for f in self.FONTES_MONO:
            if f in familias or f.lower() in {x.lower() for x in familias}:
                CONFIG["fonte_mono"] = f
                break

        self._set_check("fontes", "✅",
                        f"UI: {CONFIG['fonte_ui']}  |  Mono: {CONFIG['fonte_mono']}",
                        self.C_VERDE, self.C_VERDE)

    def _checar_reportlab(self):
        try:
            import reportlab
            CONFIG["reportlab"] = True
            self._set_check("reportlab", "✅",
                            f"v{reportlab.Version} — PDF habilitado",
                            self.C_VERDE, self.C_VERDE)
        except ImportError:
            CONFIG["reportlab"] = False
            self._set_check("reportlab", "⚠️",
                            "Não instalado — PDF desabilitado",
                            self.C_AMARELO, self.C_AMARELO)

    def _checar_pillow(self):
        try:
            from PIL import Image
            import PIL
            CONFIG["pillow"] = True
            self._set_check("pillow", "✅",
                            f"v{PIL.__version__} — Logos em alta qualidade",
                            self.C_VERDE, self.C_VERDE)
        except ImportError:
            CONFIG["pillow"] = False
            self._set_check("pillow", "⚠️",
                            "Não instalado — logos em qualidade básica",
                            self.C_AMARELO, self.C_AMARELO)

    def _checar_internet(self):
        try:
            import urllib.request
            urllib.request.urlopen("https://raw.githubusercontent.com", timeout=3)
            self._set_check("internet", "✅",
                            "Conectado — logos serão baixados automaticamente",
                            self.C_VERDE, self.C_VERDE)
        except Exception:
            self._set_check("internet", "ℹ️",
                            "Sem conexão — logos carregados do cache local",
                            self.C_MUTED)

    # ── Instalação de pacotes faltantes ───────────────────────────────────
    def _oferecer_instalacao(self, pacotes_faltantes):
        if not pacotes_faltantes:
            return

        def _montar_ui():
            for w in self._frame_instalar.winfo_children():
                w.destroy()

            nomes = " + ".join(pacotes_faltantes)
            tk.Label(self._frame_instalar,
                     text=f"📦  Pacotes opcionais não encontrados: {nomes}",
                     font=("Arial", 8), bg=self.C_BG,
                     fg=self.C_AMARELO).pack(anchor="w")

            frame_btn_inst = tk.Frame(self._frame_instalar, bg=self.C_BG)
            frame_btn_inst.pack(fill="x", pady=3)

            btn_inst = tk.Button(
                frame_btn_inst,
                text=f"⬇  Instalar {nomes} automaticamente (pip)",
                font=("Arial", 9, "bold"),
                bg=self.C_ACENTO, fg="white",
                relief="flat", bd=0, padx=10, pady=5,
                cursor="hand2",
                command=lambda: self._instalar_pacotes(pacotes_faltantes, btn_inst)
            )
            btn_inst.pack(side="left")

            tk.Label(frame_btn_inst,
                     text="  (requer internet)",
                     font=("Arial", 8), bg=self.C_BG,
                     fg=self.C_MUTED).pack(side="left")

        self.root.after(0, _montar_ui)

    def _instalar_pacotes(self, pacotes, btn_orig):
        btn_orig.config(state="disabled", text="⏳ Instalando...", bg=self.C_AMARELO)
        self._set_status("Instalando pacotes... aguarde.")

        def _instalar():
            erros = []
            for pkg in pacotes:
                try:
                    subprocess.check_call(
                        [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
                        creationflags=0x08000000 if sys.platform == "win32" else 0
                    )
                except Exception as e:
                    erros.append(pkg)

            def _pos():
                if not erros:
                    btn_orig.config(text="✅ Instalado com sucesso!", bg=self.C_VERDE)
                    self._set_status("Pacotes instalados. Reinicie o sistema para ativar.")
                    # Re-checa
                    if "reportlab" in pacotes: self._checar_reportlab()
                    if "Pillow"    in pacotes: self._checar_pillow()
                else:
                    btn_orig.config(text=f"❌ Falha em: {', '.join(erros)}", bg=self.C_VERMELHO)
                    self._set_status("Falha na instalação. Tente manualmente: pip install " + " ".join(erros))
                btn_orig.config(state="normal")
            self.root.after(0, _pos)

        threading.Thread(target=_instalar, daemon=True).start()

    # ── Sequência principal de verificação ────────────────────────────────
    def _executar_checks(self):
        total = len(self._itens)
        passos = [
            ("python",    self._checar_python,    "Verificando Python..."),
            ("windows",   self._checar_windows,   "Verificando Windows..."),
            ("tkinter",   self._checar_tkinter,   "Verificando interface gráfica..."),
            ("sqlite",    self._checar_sqlite,     "Verificando banco de dados..."),
            ("fontes",    self._checar_fontes,     "Detectando fontes disponíveis..."),
            ("reportlab", self._checar_reportlab,  "Verificando gerador de PDF..."),
            ("pillow",    self._checar_pillow,     "Verificando suporte a imagens..."),
            ("internet",  self._checar_internet,   "Testando conexão com a internet..."),
        ]

        for i, (chave, fn, msg) in enumerate(passos):
            self._set_status(msg)
            fn()
            self._set_progress(int((i + 1) / total * 100))
            import time; time.sleep(0.25)   # pausa visual para o usuário acompanhar

        # Verifica quais opcionais faltam
        faltantes = []
        if not CONFIG["reportlab"]: faltantes.append("reportlab")
        if not CONFIG["pillow"]:    faltantes.append("Pillow")
        self._oferecer_instalacao(faltantes)

        # Decide se pode continuar
        if CONFIG["python_ok"]:
            self._set_status("✅ Verificação concluída. Pronto para abrir o sistema!")
            self.root.after(0, lambda: self._btn_continuar.config(state="normal"))
        else:
            self._set_status("❌ Versão do Python incompatível. Atualize em python.org")
            self.root.after(0, lambda: self._btn_continuar.config(
                state="disabled",
                text="Python incompatível — atualize em python.org",
                bg=self.C_VERMELHO
            ))

    def _ao_continuar(self):
        self._continuar = True
        self.root.destroy()

    def executar(self):
        """Inicia a tela, roda os checks em background e retorna True se deve continuar."""
        # Inicia checks em thread separada para não travar a UI
        threading.Thread(target=self._executar_checks, daemon=True).start()
        self.root.mainloop()
        return self._continuar


# ══════════════════════════════════════════════════════════════════════════
# APLICA CONFIG DE COMPATIBILIDADE NO APP
# Chamado após TelaCompatibilidade.executar() e antes de AplicacaoOficina()
# ══════════════════════════════════════════════════════════════════════════
def aplicar_config_dpi():
    """Ativa DPI awareness no Windows 8.1+ para evitar UI borrada em telas HiDPI."""
    if sys.platform != "win32":
        return
    try:
        build = int(platform.version().split(".")[2])
        if build >= 9600:   # Windows 8.1+
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
                CONFIG["dpi_aware"] = True
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass
    except Exception:
        pass


def configurar_janela_monitor(root, min_largura=1024, min_altura=700):
    """Maximiza a janela principal na área útil do monitor."""
    root.minsize(min_largura, min_altura)
    root.update_idletasks()
    if sys.platform == "win32":
        root.state("zoomed")
    else:
        try:
            root.attributes("-zoomed", True)
        except tk.TclError:
            w = root.winfo_screenwidth()
            h = root.winfo_screenheight()
            root.geometry(f"{w}x{h}+0+0")


BANDEIRAS_CARTAO = ["Visa", "Mastercard", "Elo", "Amex", "Hipercard", "Outros"]
FORMAS_PAGAMENTO = ["À Vista / PIX", "Cartão de Crédito", "Cartão de Débito", "Outros"]

DEFAULT_TAXAS_REF = {
    "Visa":         [2.29, 2.89, 3.19, 3.49, 3.79, 4.09, 4.39, 4.69, 4.99, 5.29],
    "Mastercard":   [2.29, 2.89, 3.19, 3.49, 3.79, 4.09, 4.39, 4.69, 4.99, 5.29],
    "Elo":          [2.49, 3.09, 3.39, 3.69, 3.99, 4.29, 4.59, 4.89, 5.19, 5.49],
    "Amex":         [3.09, 3.69, 3.99, 4.29, 4.59, 4.89, 5.19, 5.49, 5.79, 6.09],
    "Hipercard":    [2.69, 3.29, 3.59, 3.89, 4.19, 4.49, 4.79, 5.09, 5.39, 5.69],
    "Outros":       [2.49, 3.09, 3.39, 3.69, 3.99, 4.29, 4.59, 4.89, 5.19, 5.49],
}


def calcular_valor_com_juros(valor_base, taxa_percentual):
    """Soma juros percentuais ao valor base (ex.: R$ 1000 + 3,5% = R$ 1035)."""
    if not taxa_percentual:
        return valor_base
    return valor_base * (1 + taxa_percentual / 100)


def calcular_valor_liquido(valor_bruto, taxa_percentual):
    """Valor líquido após desconto MDR (uso interno/legado)."""
    if not taxa_percentual:
        return valor_bruto
    return valor_bruto * (1 - taxa_percentual / 100)


def carregar_taxas_bandeira(bandeira):
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT num_parcelas, taxa_percentual FROM taxas_cartao WHERE bandeira = ? ORDER BY num_parcelas",
            (bandeira,),
        )
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return None
        return {r[0]: r[1] for r in rows}
    except sqlite3.OperationalError:
        return None


def obter_taxas_bandeira(bandeira):
    cadastro = carregar_taxas_bandeira(bandeira)
    if cadastro:
        return cadastro
    ref = DEFAULT_TAXAS_REF.get(bandeira, DEFAULT_TAXAS_REF["Outros"])
    return {i + 1: ref[i] for i in range(10)}


def salvar_taxas_bandeira(bandeira, taxas_dict, fonte="manual"):
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    conn = conectar_banco()
    cursor = conn.cursor()
    for num_p, taxa in taxas_dict.items():
        cursor.execute(
            """INSERT INTO taxas_cartao (bandeira, num_parcelas, taxa_percentual, fonte, atualizado_em)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(bandeira, num_parcelas) DO UPDATE SET
                   taxa_percentual=excluded.taxa_percentual,
                   fonte=excluded.fonte,
                   atualizado_em=excluded.atualizado_em""",
            (bandeira, num_p, taxa, fonte, agora),
        )
    conn.commit()
    conn.close()


def buscar_taxas_web(bandeira):
    query = f"taxa MDR {bandeira} cartão crédito parcelado Brasil {datetime.now().year}"
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; MultiEscapeERP/1.2)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return None

    pct_re = re.compile(r"(\d{1,2}[,.]\d{1,2})\s*%")
    encontrados = []
    for m in pct_re.finditer(html):
        try:
            v = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        if 0.5 <= v <= 15.0:
            encontrados.append(v)

    if not encontrados:
        return None

    unicos = sorted(set(encontrados))
    base = unicos[0]
    taxas = {}
    for i in range(1, 11):
        if len(unicos) >= i:
            taxas[i] = round(unicos[i - 1], 2)
        else:
            taxas[i] = round(base + (i - 1) * 0.25, 2)
    return taxas


def _normalizar_data_br(data_str):
    """Converte data para DD/MM/AAAA ou retorna None."""
    if not data_str:
        return None
    data_str = str(data_str).strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(data_str, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    partes = data_str.split("/")
    if len(partes) == 3:
        try:
            d, m, a = int(partes[0]), int(partes[1]), int(partes[2])
            if a < 100:
                a += 2000
            return f"{d:02d}/{m:02d}/{a:04d}"
        except ValueError:
            pass
    return None


def _data_br_para_iso(data_str):
    data_norm = _normalizar_data_br(data_str)
    if not data_norm:
        return None
    return datetime.strptime(data_norm, "%d/%m/%Y").strftime("%Y-%m-%d")


def _mes_ano_da_data(data_norm):
    if not data_norm:
        return None
    p = data_norm.split("/")
    return f"{p[1]}/{p[2]}" if len(p) == 3 else None


def _normalizar_mes_ano(mes_ano):
    if not mes_ano:
        return None
    partes = str(mes_ano).strip().split("/")
    if len(partes) != 2:
        return mes_ano
    try:
        return f"{int(partes[0]):02d}/{int(partes[1]):04d}"
    except ValueError:
        return mes_ano


DB_NAME = "sistema_oficina.db"
BACKUP_DIR = "backups"
LOG_DIR = "logs"

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "app.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)

def conectar_banco():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def criar_backup_banco(max_backups=14):
    """Cria um backup diario do banco antes de iniciar o sistema."""
    if not os.path.exists(DB_NAME):
        return None

    os.makedirs(BACKUP_DIR, exist_ok=True)
    hoje = datetime.now().strftime("%Y-%m-%d")
    destino = os.path.join(BACKUP_DIR, f"sistema_oficina_{hoje}.db")

    if os.path.exists(destino):
        return destino

    try:
        shutil.copy2(DB_NAME, destino)
        backups = sorted(
            os.path.join(BACKUP_DIR, nome)
            for nome in os.listdir(BACKUP_DIR)
            if nome.startswith("sistema_oficina_") and nome.endswith(".db")
        )
        for antigo in backups[:-max_backups]:
            try:
                os.remove(antigo)
            except OSError:
                logging.exception("Falha ao remover backup antigo: %s", antigo)
        logging.info("Backup do banco criado: %s", destino)
        return destino
    except Exception:
        logging.exception("Falha ao criar backup do banco")
        return None

def _detectar_escala():
    """Retorna fator de escala adequado para a versao do Windows detectada."""
    try:
        build = int(platform.version().split(".")[2])
        if build >= 22000:   return 1.25   # Windows 11
        if build >= 10240:   return 1.0    # Windows 10
        if build >= 9200:    return 1.0    # Windows 8/8.1
        return 0.9                         # Windows 7
    except Exception:
        logging.exception("Falha ao detectar escala da interface")
        return 1.0

def inicializar_banco():
    conn = conectar_banco()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            placa TEXT NOT NULL UNIQUE,
            marca TEXT,
            modelo TEXT,
            ano TEXT,
            contato TEXT,
            email TEXT,
            cor TEXT,
            data_cadastro TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orcamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            servico_solicitado TEXT,
            valor_mao_de_obra REAL DEFAULT 0.0,
            observacao TEXT,
            pagamento_info TEXT,
            parcelas_impressao TEXT,
            status TEXT DEFAULT 'Aguardando Retorno',
            data_orcamento TEXT,
            previsao_entrega TEXT,
            caminho_imagem_ocr TEXT,
            qtd_parcelas_v11 INTEGER DEFAULT 1,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS produtos_orcamento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orcamento_id INTEGER,
            codigo TEXT,
            descricao TEXT,
            quantidade INTEGER,
            valor_unitario REAL,
            fornecedor_id INTEGER,
            valor_compra_custo REAL DEFAULT 0.0,
            forma_pagamento_fornecedor TEXT,
            FOREIGN KEY(orcamento_id) REFERENCES orcamentos(id) ON DELETE CASCADE,
            FOREIGN KEY(fornecedor_id) REFERENCES fornecedores(id) ON DELETE SET NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fornecedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_empresa TEXT NOT NULL,
            contato_pessoa TEXT,
            telefone TEXT,
            email TEXT,
            endereco TEXT,
            dias_atendimento TEXT DEFAULT 'Segunda a Sábado',
            horario_funcionamento TEXT,
            previsao_entrega TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS catalogo_pecas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_peca TEXT NOT NULL,
            valor_compra REAL DEFAULT 0.0,
            fornecedor_id INTEGER,
            FOREIGN KEY(fornecedor_id) REFERENCES fornecedores(id) ON DELETE SET NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS marcas_modelos_veiculos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            marca_nome TEXT NOT NULL,
            modelo_motor TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contas_receber (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orcamento_id INTEGER,
            cliente_id INTEGER,
            num_parcela TEXT,
            valor_parcela REAL,
            data_vencimento TEXT,
            status_pago TEXT DEFAULT 'A Receber',
            FOREIGN KEY(orcamento_id) REFERENCES orcamentos(id) ON DELETE CASCADE,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contas_pagar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orcamento_id INTEGER,
            fornecedor_id INTEGER,
            num_parcela TEXT DEFAULT '1/1',
            peca_descricao TEXT,
            valor_custo REAL,
            data_vencimento TEXT,
            status_pago TEXT DEFAULT 'A Pagar',
            FOREIGN KEY(orcamento_id) REFERENCES orcamentos(id) ON DELETE CASCADE,
            FOREIGN KEY(fornecedor_id) REFERENCES fornecedores(id) ON DELETE CASCADE
        )
    ''')
    
    # Migrações seguras
    try: cursor.execute("ALTER TABLE catalogo_pecas ADD COLUMN codigo_fabrica TEXT;")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE clientes ADD COLUMN ano TEXT;")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE clientes ADD COLUMN email TEXT;")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE fornecedores ADD COLUMN email TEXT;")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE orcamentos ADD COLUMN status TEXT DEFAULT 'Aguardando Retorno';")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE orcamentos ADD COLUMN previsao_entrega TEXT;")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE orcamentos ADD COLUMN qtd_parcelas_v11 INTEGER DEFAULT 1;")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE produtos_orcamento ADD COLUMN fornecedor_id INTEGER;")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE produtos_orcamento ADD COLUMN valor_compra_custo REAL DEFAULT 0.0;")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE produtos_orcamento ADD COLUMN forma_pagamento_fornecedor TEXT;")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE contas_pagar ADD COLUMN num_parcela TEXT DEFAULT '1/1';")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE orcamentos ADD COLUMN bandeira_cartao TEXT;")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE orcamentos ADD COLUMN taxa_cartao_percentual REAL DEFAULT 0;")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE orcamentos ADD COLUMN valor_liquido_estimado REAL;")
    except sqlite3.OperationalError: pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS taxas_cartao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bandeira TEXT NOT NULL,
            num_parcelas INTEGER NOT NULL,
            taxa_percentual REAL NOT NULL,
            fonte TEXT,
            atualizado_em TEXT,
            UNIQUE(bandeira, num_parcelas)
        )
    ''')

    cursor.execute("SELECT COUNT(*) FROM taxas_cartao")
    if cursor.fetchone()[0] == 0:
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
        for bandeira, taxas in DEFAULT_TAXAS_REF.items():
            for n, taxa in enumerate(taxas, 1):
                cursor.execute(
                    "INSERT INTO taxas_cartao (bandeira, num_parcelas, taxa_percentual, fonte, atualizado_em) VALUES (?,?,?,?,?)",
                    (bandeira, n, taxa, "referencia", agora),
                )

    cursor.execute("SELECT COUNT(*) FROM marcas_modelos_veiculos")
    if cursor.fetchone()[0] == 0:
        veiculos_base = [
            # ── FIAT ──────────────────────────────────────────────────────
            ("Fiat", "Strada 1.3 Flex Freedom"),
            ("Fiat", "Strada 1.3 Turbo Volcano"),
            ("Fiat", "Argo 1.0 Drive"),
            ("Fiat", "Argo 1.3 Trekking"),
            ("Fiat", "Argo 1.8 Precision"),
            ("Fiat", "Mobi 1.0 Like"),
            ("Fiat", "Mobi 1.0 Drive"),
            ("Fiat", "Cronos 1.3 Drive"),
            ("Fiat", "Cronos 1.3 Precision"),
            ("Fiat", "Pulse 1.0 Turbo Drive"),
            ("Fiat", "Pulse 1.3 Turbo Audace"),
            ("Fiat", "Fastback 1.0 Turbo Audace"),
            ("Fiat", "Fastback 1.3 Turbo Impetus"),
            ("Fiat", "Toro 1.3 Turbo Freedom"),
            ("Fiat", "Toro 2.0 Turbo Diesel Ultra"),
            ("Fiat", "Ducato 2.3 Diesel Cargo"),
            ("Fiat", "Doblo 1.4 Fire Cargo"),
            ("Fiat", "Uno 1.0 Fire Way"),
            ("Fiat", "Grand Siena 1.4 Attractive"),
            ("Fiat", "Bravo 1.8 Essence"),
            # ── VOLKSWAGEN ────────────────────────────────────────────────
            ("Volkswagen", "Polo 1.0 TSI Comfortline"),
            ("Volkswagen", "Polo 1.0 TSI Highline"),
            ("Volkswagen", "Polo 1.4 TSI GTS"),
            ("Volkswagen", "T-Cross 1.0 TSI Comfortline"),
            ("Volkswagen", "T-Cross 1.4 TSI Highline"),
            ("Volkswagen", "Nivus 1.0 TSI Comfortline"),
            ("Volkswagen", "Nivus 1.0 TSI Highline"),
            ("Volkswagen", "Saveiro 1.6 MSI Trendline"),
            ("Volkswagen", "Saveiro 1.6 MSI Cabine Dupla"),
            ("Volkswagen", "Virtus 1.0 TSI Comfortline"),
            ("Volkswagen", "Virtus 1.6 MSI Comfortline"),
            ("Volkswagen", "Jetta 1.4 TSI Comfortline"),
            ("Volkswagen", "Jetta 1.4 TSI GLi"),
            ("Volkswagen", "Tiguan 1.4 TSI Allspace"),
            ("Volkswagen", "Gol 1.0 MPI Trendline"),
            ("Volkswagen", "Gol 1.6 MSI Track"),
            ("Volkswagen", "Fox 1.0 MPI Connect"),
            ("Volkswagen", "Amarok 3.0 V6 TDI Extreme"),
            ("Volkswagen", "Amarok 2.0 TDI Trendline"),
            # ── CHEVROLET ─────────────────────────────────────────────────
            ("Chevrolet", "Onix 1.0 Turbo LT"),
            ("Chevrolet", "Onix 1.0 Turbo LTZ"),
            ("Chevrolet", "Onix 1.0 Turbo RS"),
            ("Chevrolet", "Onix Plus 1.0 Turbo LT"),
            ("Chevrolet", "Onix Plus 1.0 Turbo LTZ"),
            ("Chevrolet", "Tracker 1.0 Turbo LT"),
            ("Chevrolet", "Tracker 1.2 Turbo Premier"),
            ("Chevrolet", "Tracker 1.2 Turbo RS"),
            ("Chevrolet", "Cruze 1.4 Turbo LT"),
            ("Chevrolet", "Cruze 1.4 Turbo Sport6 RS"),
            ("Chevrolet", "S10 2.8 Turbo Diesel LTZ"),
            ("Chevrolet", "S10 2.5 Flex LT"),
            ("Chevrolet", "Montana 1.2 Turbo Premier"),
            ("Chevrolet", "Equinox 1.5 Turbo LT"),
            ("Chevrolet", "Trailblazer 2.8 Turbo Diesel Premier"),
            ("Chevrolet", "Spin 1.8 LT"),
            ("Chevrolet", "Spin 1.8 Activ"),
            # ── HYUNDAI ───────────────────────────────────────────────────
            ("Hyundai", "HB20 1.0 Sense"),
            ("Hyundai", "HB20 1.0 Turbo Comfort Plus"),
            ("Hyundai", "HB20 1.6 R Spec"),
            ("Hyundai", "HB20S 1.0 Comfort"),
            ("Hyundai", "HB20S 1.0 Turbo Evolution"),
            ("Hyundai", "Creta 1.0 Turbo Comfort"),
            ("Hyundai", "Creta 1.0 Turbo Platinum"),
            ("Hyundai", "Creta 2.0 Ultimate"),
            ("Hyundai", "Tucson 1.6 Turbo GLS"),
            ("Hyundai", "Tucson 1.6 GDI GL"),
            ("Hyundai", "ix35 2.0 GL"),
            ("Hyundai", "Santa Fe 3.3 V6"),
            # ── NISSAN ────────────────────────────────────────────────────
            ("Nissan", "Kicks 1.6 Sense"),
            ("Nissan", "Kicks 1.6 Advance"),
            ("Nissan", "Kicks 1.6 Exclusive"),
            ("Nissan", "Versa 1.6 Sense"),
            ("Nissan", "Versa 1.6 Advance"),
            ("Nissan", "Frontier 2.3 Turbo Diesel XE"),
            ("Nissan", "Frontier 2.3 Turbo Diesel PRO-4X"),
            # ── RENAULT ───────────────────────────────────────────────────
            ("Renault", "Kwid 1.0 Zen"),
            ("Renault", "Kwid 1.0 Outsider"),
            ("Renault", "Kwid E-Tech Elétrico"),
            ("Renault", "Sandero 1.0 Zen"),
            ("Renault", "Sandero 1.6 Stepway"),
            ("Renault", "Logan 1.6 Zen"),
            ("Renault", "Duster 1.3 Turbo Iconic"),
            ("Renault", "Duster 2.0 Dynamique"),
            ("Renault", "Captur 1.3 Turbo Intense"),
            ("Renault", "Kardian 1.0 Turbo Techno"),
            # ── JEEP ──────────────────────────────────────────────────────
            ("Jeep", "Renegade 1.3 Turbo Longitude"),
            ("Jeep", "Renegade 2.0 Turbo Diesel Trailhawk"),
            ("Jeep", "Compass 1.3 Turbo Longitude"),
            ("Jeep", "Compass 2.0 Turbo Diesel Trailhawk"),
            ("Jeep", "Commander 1.3 Turbo Longitude"),
            ("Jeep", "Commander 2.0 Turbo Diesel Overland"),
            ("Jeep", "Gladiator 3.0 V6 Diesel Rubicon"),
            # ── TOYOTA ────────────────────────────────────────────────────
            ("Toyota", "Corolla 2.0 XEi"),
            ("Toyota", "Corolla 2.0 Altis Hybrid"),
            ("Toyota", "Corolla Cross 2.0 XRE"),
            ("Toyota", "Yaris 1.3 Sedan XS"),
            ("Toyota", "Yaris 1.5 Hatch GR-S"),
            ("Toyota", "Hilux 2.8 Turbo Diesel SRX"),
            ("Toyota", "Hilux 2.8 Turbo Diesel GR-S"),
            ("Toyota", "SW4 2.8 Turbo Diesel Diamond"),
            ("Toyota", "RAV4 2.5 Hybrid"),
            # ── HONDA ─────────────────────────────────────────────────────
            ("Honda", "Civic 2.0 Sport"),
            ("Honda", "Civic 1.5 Turbo Touring"),
            ("Honda", "City 1.5 EXL"),
            ("Honda", "City Hatchback 1.5 EXL"),
            ("Honda", "HR-V 1.5 Turbo EX"),
            ("Honda", "HR-V 1.5 Turbo Touring"),
            ("Honda", "WR-V 1.5 Touring"),
            ("Honda", "CR-V 1.5 Turbo EXL"),
            # ── FORD ──────────────────────────────────────────────────────
            ("Ford", "Ranger 2.0 Turbo Diesel Storm"),
            ("Ford", "Ranger 2.0 Turbo XLS"),
            ("Ford", "Ranger 3.0 Turbo Diesel Raptor"),
            ("Ford", "Bronco Sport 2.0 Turbo Wildtrak"),
            ("Ford", "Territory 1.5 Titanium"),
            ("Ford", "Maverick 2.0 Turbo Storm"),
            # ── PEUGEOT ───────────────────────────────────────────────────
            ("Peugeot", "208 1.0 Like"),
            ("Peugeot", "208 1.6 THP GT"),
            ("Peugeot", "2008 1.6 THP Griffe"),
            ("Peugeot", "3008 1.6 THP Allure"),
            # ── CITROËN ───────────────────────────────────────────────────
            ("Citroën", "C3 1.0 Feel"),
            ("Citroën", "C3 Aircross 1.0 Feel"),
            ("Citroën", "Basalt 1.0 Turbo Feel"),
            # ── MITSUBISHI ────────────────────────────────────────────────
            ("Mitsubishi", "L200 Triton Sport 2.4 Turbo Diesel HPE"),
            ("Mitsubishi", "Eclipse Cross 1.5 Turbo HPE-S"),
            ("Mitsubishi", "Outlander 2.0 MIVEC"),
            ("Mitsubishi", "ASX 2.0 Flex HPE"),
            # ── CAOA CHERY ────────────────────────────────────────────────
            ("Caoa Chery", "Tiggo 5X 1.5 Turbo TXS"),
            ("Caoa Chery", "Tiggo 7 Pro 1.5 Turbo TXS"),
            ("Caoa Chery", "Tiggo 8 Pro 1.6 Turbo TXS"),
            ("Caoa Chery", "Arrizo 6 Pro 1.5 Turbo TXS"),
            # ── GWM / HAVAL ───────────────────────────────────────────────
            ("GWM", "Haval H6 1.5 Turbo Ultra"),
            ("GWM", "Haval H6 Plug-in Hybrid"),
            ("GWM", "ORA 03 Elétrico"),
            ("GWM", "Poer 2.0 Turbo Diesel Luxo"),
            # ── BYD ───────────────────────────────────────────────────────
            ("BYD", "Dolphin Elétrico"),
            ("BYD", "Atto 3 Elétrico"),
            ("BYD", "Seal Elétrico"),
            ("BYD", "King Pro 1.5 Plug-in Hybrid"),
            ("BYD", "Tan Elétrico"),
            # ── MERCEDES-BENZ ─────────────────────────────────────────────
            ("Mercedes-Benz", "Classe A 200 Sedan"),
            ("Mercedes-Benz", "GLA 200 Enduro"),
            ("Mercedes-Benz", "GLC 300 4MATIC"),
            ("Mercedes-Benz", "Sprinter 2.1 CDI Cargo"),
            # ── BMW ───────────────────────────────────────────────────────
            ("BMW", "320i 2.0 Turbo Sport"),
            ("BMW", "X1 2.0 sDrive20i"),
            ("BMW", "X3 2.0 xDrive20i"),
            # ── LAND ROVER ────────────────────────────────────────────────
            ("Land Rover", "Defender 110 3.0 D300"),
            ("Land Rover", "Discovery Sport 1.5 P300e"),
            ("Land Rover", "Range Rover Evoque 1.5 P300e"),
            # ── VOLVO ─────────────────────────────────────────────────────
            ("Volvo", "XC40 2.0 Recharge"),
            ("Volvo", "XC60 2.0 B5 Inscription"),
        ]
        cursor.executemany("INSERT INTO marcas_modelos_veiculos (marca_nome, modelo_motor) VALUES (?,?)", veiculos_base)

    # ── Fornecedores da Zona Sul de SP — carga inicial ─────────────────
    cursor.execute("SELECT COUNT(*) FROM fornecedores")
    if cursor.fetchone()[0] == 0:
        fornecedores_base = [
            # nome_empresa, contato_pessoa, telefone, email, endereco, dias_atend, horario, prev_entrega
            (
                "Mello Autopeças",
                "Atendimento Comercial",
                "(11) 5013-9999",
                "contato@melloautopecas.com.br",
                "Av. Dr. Luis Rocha Miranda, 206/210 - Jabaquara, SP - CEP 04344-010",
                "Segunda a Sábado",
                "07:30 às 18:30",
                "Até 1 hora (motoboy próprio)"
            ),
            (
                "KMK Auto Peças",
                "Vendas KMK",
                "(11) 99498-8699",
                "vendas@kmkautopecas.com.br",
                "Região Jabaquara / Americanópolis / Cidade Ademar - SP",
                "Segunda a Sábado",
                "08:00 às 18:00",
                "Até 2 horas (delivery zona sul)"
            ),
            (
                "Potência Auto Peças",
                "Balcão Comercial",
                "(11) 2274-5390",
                "contato@potenciaautopecas.com.br",
                "Rua Paulo Bregaro, 50 - Ipiranga, SP",
                "Segunda a Sábado",
                "08:00 às 18:00",
                "Até 2 horas"
            ),
            (
                "Auto Peças Jamaris",
                "Atendimento",
                "(11) 5051-7269",
                "contato@autopecasjamaris.com.br",
                "Av. Jamaris, 504 - Moema, SP",
                "Segunda a Sábado",
                "08:00 às 18:00",
                "Até 2 horas"
            ),
            (
                "MercadoCar Shopping de Auto Peças",
                "Gerência Comercial",
                "(11) 5546-3555",
                "contato@mercadocar.com.br",
                "Av. Victor Manzini, 420 - Santo Amaro, SP",
                "Segunda a Sábado",
                "08:00 às 18:00",
                "Até 3 horas"
            ),
            (
                "Voli Shopping de Auto Peças",
                "Vendas",
                "(11) 5523-8411",
                "contato@voli.com.br",
                "Rua Suzana Rodrigues, 310 - Santo Amaro, SP",
                "Segunda a Sábado",
                "08:00 às 18:00",
                "Até 2 horas"
            ),
            (
                "Kaçula Auto Peças",
                "Atendimento Comercial",
                "(11) 2307-6067",
                "contato@kaculaautopecas.com.br",
                "Av. Prof. Abraão de Morais, 880 - Saúde, SP",
                "Segunda a Sábado",
                "08:00 às 18:00",
                "Até 2 horas"
            ),
            (
                "São Paulo Auto Peças (Saúde)",
                "Vendas",
                "(11) 5594-3465",
                "contato@saopauloautopecas.com.br",
                "Av. Prof. Abraão de Morais, 200 - Saúde, SP",
                "Segunda a Sábado",
                "08:00 às 18:00",
                "Até 2 horas"
            ),
            (
                "Saratani Auto Peças",
                "Atendimento",
                "(11) 5080-7575",
                "contato@saratani.com.br",
                "Rua Domingos de Morais, 1086 - Vila Mariana, SP",
                "Segunda a Sábado",
                "08:00 às 18:00",
                "Até 2 horas"
            ),
            (
                "Auto Peças Meocar",
                "Balcão Comercial",
                "(11) 5575-2885",
                "contato@autopecasmeocar.com.br",
                "Av. Dr. Ricardo Jafet, 2512 - Vila Mariana, SP",
                "Segunda a Sábado",
                "08:00 às 18:00",
                "Até 2 horas"
            ),
            (
                "Regicar Auto Peças (Santo Amaro)",
                "Vendas",
                "(11) 5527-4877",
                "contato@regicarautopecas.com.br",
                "Santo Amaro, São Paulo - SP",
                "Segunda a Sábado",
                "08:00 às 18:00",
                "Até 2 horas"
            ),
            (
                "AutoZone Diadema",
                "Atendimento",
                "(11) 4043-0555",
                "atendimento@autozone.com.br",
                "Av. Antonio Piranga, 779 - Centro, Diadema - SP",
                "Segunda a Domingo",
                "08:00 às 22:00",
                "Retirada em loja / Até 4 horas"
            ),
            (
                "AutoZone Santo André (Av. Dos Estados)",
                "Atendimento",
                "(11) 4435-0800",
                "atendimento@autozone.com.br",
                "Av. Dos Estados, 5911 - Santo André - SP - CEP 09210-580",
                "Segunda a Domingo",
                "08:00 às 21:00",
                "Retirada em loja / Até 4 horas"
            ),
            (
                "AutoZone São Bernardo do Campo",
                "Atendimento",
                "(11) 4435-0800",
                "atendimento@autozone.com.br",
                "Av. do Taboão, 3764 - São Bernardo do Campo - SP",
                "Segunda a Domingo",
                "08:00 às 22:00",
                "Retirada em loja / Até 4 horas"
            ),
            (
                "Suporte Distribuidora (Zona Sul)",
                "Televendas",
                "(11) 5000-0000",
                "contato@suportedistribuidora.com.br",
                "Zona Sul de São Paulo - SP",
                "Segunda a Sábado",
                "08:00 às 18:00",
                "Até 1 dia útil (motoboy)"
            ),
            (
                "Injesan Distribuidora SP",
                "Comercial",
                "(11) 3000-0000",
                "contato@injesan.com.br",
                "São Paulo - SP (Injeção Eletrônica / Híbridos / Elétricos)",
                "Segunda a Sexta",
                "08:00 às 18:00",
                "Até 1 dia útil"
            ),
            (
                "Autopeças 2000 (Jabaquara)",
                "Atendimento",
                "(11) 5011-6770",
                "",
                "Rua das Canjeranas - Vila Parque Jabaquara, SP",
                "Segunda a Sábado",
                "08:00 às 18:00",
                "Até 2 horas"
            ),
            (
                "Auto Peças M'Boi Mirim",
                "Vendas",
                "(11) 5666-0000",
                "",
                "Estrada do M'Boi Mirim, 3242 - Jd. Coimbra, SP - CEP 04932-306",
                "Segunda a Sábado",
                "08:00 às 18:00",
                "Até 3 horas"
            ),
            (
                "Auto Peças Interlagos",
                "Comercial",
                "(11) 5584-2300",
                "",
                "Av. Manuel Alves Soares, 185 - Interlagos, SP - CEP 04821-270",
                "Segunda a Sábado",
                "08:00 às 18:00",
                "Até 2 horas"
            ),
            (
                "Auto Peças Sacomã",
                "Balcão",
                "(11) 2272-2520",
                "",
                "Rua do Manifesto, 1993 - Vila Independência (Sacomã), SP",
                "Segunda a Sábado",
                "08:00 às 18:00",
                "Até 2 horas"
            ),
        ]
        cursor.executemany(
            "INSERT INTO fornecedores (nome_empresa, contato_pessoa, telefone, email, endereco, dias_atendimento, horario_funcionamento, previsao_entrega) VALUES (?,?,?,?,?,?,?,?)",
            fornecedores_base
        )

    conn.commit()
    conn.close()

# ==========================================
# 2. GERADOR DE IMPRESSÃO A4 (PDF)
# ==========================================
def gerar_pdf_orcamento(orcamento_id):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                        Table, TableStyle, HRFlowable, KeepTogether)
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
        from reportlab.lib import colors
        from reportlab.lib.units import mm
    except ImportError:
        return None

    # ── Busca dados ────────────────────────────────────────────────────────
    conn = conectar_banco(); cursor = conn.cursor()
    cursor.execute('''
        SELECT c.nome, c.placa, c.marca, c.modelo, c.ano, c.contato, c.email, c.cor,
               o.servico_solicitado, o.valor_mao_de_obra, o.observacao,
               o.pagamento_info, o.parcelas_impressao, o.status,
               o.data_orcamento, o.previsao_entrega, o.qtd_parcelas_v11,
               o.bandeira_cartao, o.taxa_cartao_percentual, o.valor_liquido_estimado
        FROM orcamentos o
        JOIN clientes c ON o.cliente_id = c.id
        WHERE o.id = ?
    ''', (orcamento_id,))
    res = cursor.fetchone()
    if not res: conn.close(); return None

    (nome, placa, marca, modelo, ano, contato, email, cor,
     serv_sol, v_mo, obs, pag_info, parc_imprimir, status_orc,
     data_orc, prev_entrega, qtd_parc, bandeira_cartao, taxa_cartao, valor_liquido_est) = res

    cursor.execute(
        "SELECT codigo, descricao, quantidade, valor_unitario "
        "FROM produtos_orcamento WHERE orcamento_id = ?",
        (orcamento_id,)
    )
    pecas = cursor.fetchall()
    conn.close()

    # ── Paleta ────────────────────────────────────────────────────────────
    AZUL_ESC   = colors.HexColor("#1B2631")
    AZUL_MED   = colors.HexColor("#2E86C1")
    AZUL_CLAR  = colors.HexColor("#D6EAF8")
    CINZA_ESC  = colors.HexColor("#5D6D7E")
    CINZA_CLAR = colors.HexColor("#F2F3F4")
    BRANCO     = colors.white
    VERDE      = colors.HexColor("#1E8449")
    AMARELO    = colors.HexColor("#F9E547")
    BORDA      = colors.HexColor("#AEB6BF")

    # ── Estilos de parágrafo ───────────────────────────────────────────────
    def S(name, **kw):
        return ParagraphStyle(name, **kw)

    st_empresa   = S("emp",   fontSize=18, fontName="Helvetica-Bold",
                              textColor=BRANCO,   alignment=TA_LEFT,   leading=22)
    st_slogan    = S("slog",  fontSize=8,  fontName="Helvetica",
                              textColor=colors.HexColor("#AED6F1"), alignment=TA_LEFT)
    st_orc_num   = S("onum",  fontSize=14, fontName="Helvetica-Bold",
                              textColor=BRANCO,   alignment=TA_RIGHT,  leading=18)
    st_orc_data  = S("odat",  fontSize=8,  fontName="Helvetica",
                              textColor=colors.HexColor("#AED6F1"), alignment=TA_RIGHT)
    st_label     = S("lbl",   fontSize=7,  fontName="Helvetica-Bold",
                              textColor=CINZA_ESC, leading=9)
    st_valor     = S("val",   fontSize=9,  fontName="Helvetica",
                              textColor=AZUL_ESC,  leading=11)
    st_valor_b   = S("valb",  fontSize=9,  fontName="Helvetica-Bold",
                              textColor=AZUL_ESC,  leading=11)
    st_col_head  = S("ch",    fontSize=8,  fontName="Helvetica-Bold",
                              textColor=BRANCO,    alignment=TA_CENTER)
    st_cell      = S("cell",  fontSize=8,  fontName="Helvetica",
                              textColor=AZUL_ESC,  leading=10)
    st_cell_r    = S("cellr", fontSize=8,  fontName="Helvetica",
                              textColor=AZUL_ESC,  alignment=TA_RIGHT, leading=10)
    st_total_lbl = S("tl",    fontSize=9,  fontName="Helvetica-Bold",
                              textColor=CINZA_ESC, alignment=TA_RIGHT)
    st_total_val = S("tv",    fontSize=9,  fontName="Helvetica-Bold",
                              textColor=AZUL_MED,  alignment=TA_RIGHT)
    st_grand_lbl = S("gl",    fontSize=11, fontName="Helvetica-Bold",
                              textColor=BRANCO,    alignment=TA_RIGHT)
    st_grand_val = S("gv",    fontSize=13, fontName="Helvetica-Bold",
                              textColor=AMARELO,   alignment=TA_RIGHT)
    st_obs       = S("obs",   fontSize=8,  fontName="Helvetica",
                              textColor=CINZA_ESC, leading=11)
    st_rodape    = S("rod",   fontSize=7,  fontName="Helvetica",
                              textColor=BORDA,     alignment=TA_CENTER)
    st_assin     = S("ass",   fontSize=8,  fontName="Helvetica",
                              textColor=CINZA_ESC, alignment=TA_CENTER)

    # ── Layout A4: margem 1 cm e largura única para todos os quadros ───────
    MARGEM = 10 * mm
    CONTENT_W = A4[0] - 2 * MARGEM
    W3 = CONTENT_W / 3.0
    TOT_W = min(90 * mm, CONTENT_W * 0.42)
    TOT_C1 = TOT_W * 0.58
    TOT_C2 = TOT_W * 0.42
    PECAS_COLS = [CONTENT_W * r for r in (0.12, 0.46, 0.10, 0.16, 0.16)]
    OBS_LABEL_W = CONTENT_W * 0.22
    OBS_VAL_W = CONTENT_W - OBS_LABEL_W

    def p_campo(label, valor, negrito=False):
        v = str(valor).strip() if valor else "—"
        fn = "Helvetica-Bold" if negrito else "Helvetica"
        return Paragraph(
            f'<font name="Helvetica-Bold" size="7" color="#5D6D7E">{label}</font><br/>'
            f'<font name="{fn}" size="9" color="#1B2631">{v}</font>',
            ParagraphStyle(f"pc_{label[:6]}", leading=12, spaceBefore=0, spaceAfter=0),
        )

    def estilo_quadro(extra=None):
        base = [
            ('GRID',          (0,0), (-1,-1), 0.4, BORDA),
            ('TOPPADDING',    (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING',   (0,0), (-1,-1), 8),
            ('RIGHTPADDING',  (0,0), (-1,-1), 8),
            ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ]
        if extra:
            base.extend(extra)
        return TableStyle(base)

    # ── Documento ──────────────────────────────────────────────────────────
    nome_pdf = f"Orcamento_{orcamento_id}_Placa_{placa.upper()}.pdf"
    doc = SimpleDocTemplate(
        nome_pdf, pagesize=A4,
        leftMargin=MARGEM, rightMargin=MARGEM,
        topMargin=MARGEM, bottomMargin=MARGEM,
    )
    story = []

    # ══════════════════════════════════════════════════════════════════════
    # 1. CABEÇALHO — banner escuro com empresa à esq. e número à dir.
    # ══════════════════════════════════════════════════════════════════════
    CAB_ESQ_W = CONTENT_W * 0.62
    CAB_DIR_W = CONTENT_W - CAB_ESQ_W

    tbl_cab = Table(
        [[
            Paragraph("MULTI ESCAPE<br/>Serviços Automotivos Especializados",
                      ParagraphStyle("cab_esq", parent=st_empresa, leading=22)),
            Paragraph(
                f"ORÇAMENTO Nº {orcamento_id:04d}<br/>"
                f'<font size="8" color="#AED6F1">Emitido em  {data_orc}</font>',
                ParagraphStyle("cab_dir", parent=st_orc_num, alignment=TA_RIGHT, leading=18),
            ),
        ]],
        colWidths=[CAB_ESQ_W, CAB_DIR_W],
    )
    tbl_cab.setStyle(estilo_quadro([
        ('BACKGROUND',  (0,0), (-1,-1), AZUL_ESC),
        ('TEXTCOLOR',   (0,0), (0,0),   BRANCO),
        ('TEXTCOLOR',   (1,0), (1,0),   BRANCO),
        ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN',       (1,0), (1,0),   'RIGHT'),
    ]))
    story.append(tbl_cab)
    story.append(Spacer(1, 6))

    # Faixa de status colorida
    cor_status = {
        "Aprovado":  colors.HexColor("#1E8449"),
        "Executado": colors.HexColor("#117864"),
        "Declinado": colors.HexColor("#C0392B"),
    }.get(status_orc, AZUL_MED)

    st_status = S("sts", fontSize=8, fontName="Helvetica-Bold",
                  textColor=BRANCO, alignment=TA_CENTER)
    tbl_status = Table(
        [[Paragraph(f"STATUS: {status_orc.upper()}", st_status)]],
        colWidths=[CONTENT_W],
    )
    tbl_status.setStyle(estilo_quadro([
        ('BACKGROUND',    (0,0), (-1,-1), cor_status),
        ('TOPPADDING',    (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('ALIGN',         (0,0), (-1,-1), 'CENTER'),
    ]))
    story.append(tbl_status)
    story.append(Spacer(1, 8))

    # ══════════════════════════════════════════════════════════════════════
    # 2. DADOS DO CLIENTE E VEÍCULO (quadro único alinhado)
    # ══════════════════════════════════════════════════════════════════════
    tbl_cliente = Table(
        [
            [
                p_campo("CLIENTE", nome),
                p_campo("TELEFONE/CONTATO", contato),
                p_campo("E-MAIL", email),
            ],
            [
                p_campo("VEÍCULO", f"{marca} {modelo}", negrito=True),
                p_campo("ANO / COR", f"{ano} / {cor}"),
                p_campo("PLACA", placa.upper(), negrito=True),
            ],
            [
                p_campo("SERVIÇO SOLICITADO", serv_sol),
                "",
                p_campo("PREVISÃO DE ENTREGA", prev_entrega),
            ],
        ],
        colWidths=[W3, W3, W3],
    )
    tbl_cliente.setStyle(estilo_quadro([
        ('BACKGROUND',     (0,0), (-1,1), CINZA_CLAR),
        ('BACKGROUND',     (0,2), (-1,2), AZUL_CLAR),
        ('ROWBACKGROUNDS', (0,0), (-1,1), [CINZA_CLAR, BRANCO]),
        ('SPAN',           (0,2), (1,2)),
    ]))
    story.append(tbl_cliente)
    story.append(Spacer(1, 8))

    # ══════════════════════════════════════════════════════════════════════
    # 3. TABELA DE PEÇAS
    # ══════════════════════════════════════════════════════════════════════
    cab_pecas = [
        Paragraph("CÓD.",        st_col_head),
        Paragraph("DESCRIÇÃO DA PEÇA / SERVIÇO", st_col_head),
        Paragraph("QTD",         st_col_head),
        Paragraph("UNIT. (R$)",  st_col_head),
        Paragraph("TOTAL (R$)",  st_col_head),
    ]
    linhas_pecas = [cab_pecas]
    total_pecas = 0.0

    for i, (cod, desc, qtd, v_uni) in enumerate(pecas):
        t_item = qtd * v_uni
        total_pecas += t_item
        bg = BRANCO if i % 2 == 0 else colors.HexColor("#EBF5FB")
        linhas_pecas.append([
            Paragraph(cod or "—",           st_cell),
            Paragraph(desc or "—",          st_cell),
            Paragraph(str(qtd),             st_cell_r),
            Paragraph(f"{v_uni:.2f}",       st_cell_r),
            Paragraph(f"{t_item:.2f}",      st_cell_r),
        ])

    tbl_pecas = Table(
        linhas_pecas,
        colWidths=PECAS_COLS,
        repeatRows=1
    )

    # Estilos zebrado dinâmico
    pecas_style = [
        # Cabeçalho
        ('BACKGROUND',    (0,0),  (-1,0),  AZUL_MED),
        ('TEXTCOLOR',     (0,0),  (-1,0),  BRANCO),
        ('TOPPADDING',    (0,0),  (-1,0),  7),
        ('BOTTOMPADDING', (0,0),  (-1,0),  7),
        ('ALIGN',         (0,0),  (-1,0),  'CENTER'),
        # Corpo
        ('GRID',          (0,0),  (-1,-1), 0.3, BORDA),
        ('TOPPADDING',    (0,1),  (-1,-1), 5),
        ('BOTTOMPADDING', (0,1),  (-1,-1), 5),
        ('LEFTPADDING',   (0,0),  (-1,-1), 6),
        ('RIGHTPADDING',  (0,0),  (-1,-1), 6),
        ('ALIGN',         (2,1),  (-1,-1), 'RIGHT'),
        ('VALIGN',        (0,0),  (-1,-1), 'MIDDLE'),
    ]
    # Zebrado
    for i in range(1, len(linhas_pecas)):
        if i % 2 == 0:
            pecas_style.append(('BACKGROUND', (0,i), (-1,i), colors.HexColor("#EBF5FB")))

    tbl_pecas.setStyle(TableStyle(pecas_style))
    story.append(KeepTogether([tbl_pecas]))
    story.append(Spacer(1, 6))

    # ══════════════════════════════════════════════════════════════════════
    # 4. BLOCO DE TOTAIS
    # ══════════════════════════════════════════════════════════════════════
    total_geral = total_pecas + v_mo
    total_final = total_geral
    if taxa_cartao and float(taxa_cartao) > 0:
        total_final = (
            float(valor_liquido_est)
            if valor_liquido_est
            else calcular_valor_com_juros(total_geral, float(taxa_cartao))
        )

    linhas_tot = [
        [Paragraph("Subtotal Peças:",  st_total_lbl),
         Paragraph(f"R$ {total_pecas:.2f}", st_total_val)],
        [Paragraph("Mão de Obra (M.O):", st_total_lbl),
         Paragraph(f"R$ {v_mo:.2f}",      st_total_val)],
    ]
    if taxa_cartao and float(taxa_cartao) > 0:
        juros_pdf = total_final - total_geral
        linhas_tot.append([
            Paragraph(f"Juros cartão ({float(taxa_cartao):.2f}%):", st_total_lbl),
            Paragraph(f"R$ {juros_pdf:.2f}", st_total_val),
        ])
    tbl_sub = Table(linhas_tot, colWidths=[TOT_C1, TOT_C2])
    tbl_sub.setStyle(estilo_quadro([
        ('BACKGROUND',    (0,0), (-1,-1), CINZA_CLAR),
        ('ALIGN',         (1,0), (1,-1), 'RIGHT'),
    ]))

    tbl_grand = Table(
        [[Paragraph("TOTAL GERAL", st_grand_lbl),
          Paragraph(f"R$ {total_final:.2f}", st_grand_val)]],
        colWidths=[TOT_C1, TOT_C2]
    )
    tbl_grand.setStyle(estilo_quadro([
        ('BACKGROUND',    (0,0), (-1,-1), AZUL_ESC),
        ('ALIGN',         (1,0), (1,0), 'RIGHT'),
    ]))

    # Parcelamento
    num_parc = int(qtd_parc) if qtd_parc and int(qtd_parc) > 0 else 1
    valor_parc = total_final / num_parc
    if num_parc > 1:
        parc_txt = f"{num_parc}x de R$ {valor_parc:.2f}"
    else:
        parc_txt = "À Vista"
    if taxa_cartao and float(taxa_cartao) > 0:
        juros_total = total_final - total_geral
        band_txt = bandeira_cartao or "Cartão"
        parc_txt += (
            f" (+ juros {float(taxa_cartao):.2f}% {band_txt} — "
            f"base R$ {total_geral:.2f} + R$ {juros_total:.2f} = R$ {total_final:.2f})"
        )
    st_parc = S("parc", fontSize=8, fontName="Helvetica-Bold",
                textColor=VERDE, alignment=TA_RIGHT)
    tbl_parc = Table(
        [[Paragraph(f"Pagamento: {parc_txt}", st_parc)]],
        colWidths=[TOT_W]
    )
    tbl_parc.setStyle(estilo_quadro([
        ('BACKGROUND',    (0,0), (-1,-1), colors.HexColor("#EAFAF1")),
        ('BOX',           (0,0), (-1,-1), 0.5, VERDE),
        ('ALIGN',         (0,0), (-1,-1), 'RIGHT'),
    ]))

    tbl_area_tot = Table(
        [[tbl_sub], [tbl_grand], [tbl_parc]],
        colWidths=[CONTENT_W],
    )
    tbl_area_tot.setStyle(TableStyle([
        ('ALIGN',         (0,0), (-1,-1), 'RIGHT'),
        ('TOPPADDING',    (0,0), (-1,-1), 1),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1),
        ('LEFTPADDING',   (0,0), (-1,-1), 0),
        ('RIGHTPADDING',  (0,0), (-1,-1), 0),
    ]))
    story.append(tbl_area_tot)
    story.append(Spacer(1, 8))

    # ══════════════════════════════════════════════════════════════════════
    # 5. OBSERVAÇÕES + PAGAMENTO
    # ══════════════════════════════════════════════════════════════════════
    linhas_info = []
    if obs and obs.strip():
        linhas_info.append([
            Paragraph("OBSERVAÇÕES", st_label),
            Paragraph(obs.strip(), st_obs),
        ])
    if pag_info and pag_info.strip():
        linhas_info.append([
            Paragraph("INFORMAÇÕES DE PAGAMENTO", st_label),
            Paragraph(pag_info.strip(), st_obs),
        ])

    if linhas_info:
        tbl_obs = Table(linhas_info, colWidths=[OBS_LABEL_W, OBS_VAL_W])
        tbl_obs.setStyle(estilo_quadro([
            ('BACKGROUND',    (0,0), (-1,-1), colors.HexColor("#FDFEFE")),
            ('VALIGN',        (0,0), (-1,-1), 'TOP'),
        ]))
        story.append(tbl_obs)
        story.append(Spacer(1, 8))

    # ══════════════════════════════════════════════════════════════════════
    # 6. ASSINATURA
    # ══════════════════════════════════════════════════════════════════════
    ASS_W = CONTENT_W / 2.0
    tbl_assin = Table(
        [[Paragraph("_" * 45, st_assin),
          Paragraph("_" * 45, st_assin)],
         [Paragraph("Responsável pela Oficina", st_assin),
          Paragraph("Assinatura do Cliente / Aprovação", st_assin)]],
        colWidths=[ASS_W, ASS_W],
    )
    tbl_assin.setStyle(estilo_quadro([
        ('TOPPADDING',    (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('ALIGN',         (0,0), (-1,-1), 'CENTER'),
    ]))
    story.append(Spacer(1, 8))
    story.append(tbl_assin)

    # ══════════════════════════════════════════════════════════════════════
    # 7. RODAPÉ
    # ══════════════════════════════════════════════════════════════════════
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width=CONTENT_W, thickness=0.5, color=BORDA))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Multi Escape — Serviços Automotivos Especializados  •  "
        f"Orçamento Nº {orcamento_id:04d}  •  Emitido em {data_orc}  •  "
        f"Documento gerado automaticamente pelo sistema ERP v1.2",
        st_rodape
    ))

    doc.build(story)
    return os.path.abspath(nome_pdf)


# ==========================================
# 2.5 WIDGETS DE DATA — CALENDÁRIO E MÊS/ANO
# ==========================================

class CalendarioPopup:
    """Popup de calendário completo para seleção de DD/MM/AAAA."""

    MESES = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho",
             "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]
    DIAS_SEMANA = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]

    def __init__(self, parent, entry_widget, titulo="Selecione a data"):
        self.entry = entry_widget

        # Tenta ler a data já digitada no campo; senão usa hoje
        try:
            data_atual = datetime.strptime(entry_widget.get(), "%d/%m/%Y")
        except ValueError:
            data_atual = datetime.now()

        self.ano  = data_atual.year
        self.mes  = data_atual.month   # 1–12

        # Janela popup
        self.top = tk.Toplevel(parent)
        self.top.title(titulo)
        self.top.resizable(False, False)
        self.top.grab_set()           # modal
        self.top.configure(bg="#2C3E50")

        self._construir()
        self._centralizar(parent)

    def _centralizar(self, parent):
        parent.update_idletasks()
        x = parent.winfo_rootx() + parent.winfo_width()  // 2 - 170
        y = parent.winfo_rooty() + parent.winfo_height() // 2 - 160
        self.top.geometry(f"+{x}+{y}")

    def _construir(self):
        # ── Cabeçalho navegação ──────────────────────────────────────────
        nav = tk.Frame(self.top, bg="#2C3E50")
        nav.pack(fill="x", padx=4, pady=4)

        tk.Button(nav, text="◀◀", font=("Arial",9,"bold"), bg="#1A252F", fg="white",
                  relief="flat", bd=0, padx=6,
                  command=lambda: self._mudar(anos=-1)).pack(side="left")
        tk.Button(nav, text="◀",  font=("Arial",9,"bold"), bg="#1A252F", fg="white",
                  relief="flat", bd=0, padx=6,
                  command=lambda: self._mudar(meses=-1)).pack(side="left")

        self.lbl_titulo = tk.Label(nav, font=("Arial",10,"bold"),
                                   bg="#2C3E50", fg="white", width=18)
        self.lbl_titulo.pack(side="left", expand=True)

        tk.Button(nav, text="▶",  font=("Arial",9,"bold"), bg="#1A252F", fg="white",
                  relief="flat", bd=0, padx=6,
                  command=lambda: self._mudar(meses=1)).pack(side="right")
        tk.Button(nav, text="▶▶", font=("Arial",9,"bold"), bg="#1A252F", fg="white",
                  relief="flat", bd=0, padx=6,
                  command=lambda: self._mudar(anos=1)).pack(side="right")

        # ── Cabeçalho dias da semana ────────────────────────────────────
        cab = tk.Frame(self.top, bg="#1A252F")
        cab.pack(fill="x", padx=4)
        for i, d in enumerate(self.DIAS_SEMANA):
            cor = "#E74C3C" if i >= 5 else "#BDC3C7"
            tk.Label(cab, text=d, font=("Arial",8,"bold"), bg="#1A252F",
                     fg=cor, width=4, pady=3).grid(row=0, column=i)

        # ── Grid de dias ────────────────────────────────────────────────
        self.frame_dias = tk.Frame(self.top, bg="#2C3E50")
        self.frame_dias.pack(padx=4, pady=4)

        # ── Rodapé ──────────────────────────────────────────────────────
        rod = tk.Frame(self.top, bg="#1A252F")
        rod.pack(fill="x", padx=4, pady=(0,4))
        tk.Button(rod, text="Hoje", font=("Arial",8), bg="#27AE60", fg="white",
                  relief="flat", bd=0, padx=10, pady=3,
                  command=self._selecionar_hoje).pack(side="left", padx=6, pady=4)
        tk.Button(rod, text="Cancelar", font=("Arial",8), bg="#C0392B", fg="white",
                  relief="flat", bd=0, padx=10, pady=3,
                  command=self.top.destroy).pack(side="right", padx=6, pady=4)

        self._renderizar_dias()

    def _renderizar_dias(self):
        import calendar
        for w in self.frame_dias.winfo_children():
            w.destroy()

        self.lbl_titulo.config(
            text=f"{self.MESES[self.mes-1]}  {self.ano}")

        cal = calendar.monthcalendar(self.ano, self.mes)
        hoje = datetime.now()

        for sem_idx, semana in enumerate(cal):
            for dia_idx, dia in enumerate(semana):
                if dia == 0:
                    tk.Label(self.frame_dias, text="", bg="#2C3E50",
                             width=4, height=1).grid(row=sem_idx, column=dia_idx)
                    continue

                eh_hoje    = (dia == hoje.day and self.mes == hoje.month and self.ano == hoje.year)
                fim_semana = dia_idx >= 5
                bg   = "#E74C3C" if eh_hoje else ("#4A6278" if fim_semana else "#3D566E")
                fg   = "white"
                font = ("Arial", 9, "bold") if eh_hoje else ("Arial", 9)

                btn = tk.Button(
                    self.frame_dias, text=str(dia),
                    font=font, bg=bg, fg=fg,
                    relief="flat", bd=0, width=4, height=1,
                    activebackground="#2980B9", activeforeground="white",
                    command=lambda d=dia: self._selecionar(d)
                )
                btn.grid(row=sem_idx, column=dia_idx, padx=1, pady=1)

    def _mudar(self, meses=0, anos=0):
        self.ano  += anos
        self.mes  += meses
        if self.mes > 12: self.mes = 1;  self.ano += 1
        if self.mes < 1:  self.mes = 12; self.ano -= 1
        self._renderizar_dias()

    def _selecionar(self, dia):
        self.entry.delete(0, "end")
        self.entry.insert(0, f"{dia:02d}/{self.mes:02d}/{self.ano}")
        self.top.destroy()

    def _selecionar_hoje(self):
        hoje = datetime.now()
        self.entry.delete(0, "end")
        self.entry.insert(0, hoje.strftime("%d/%m/%Y"))
        self.top.destroy()


class MesAnoPopup:
    """Popup seletor de Mês/Ano para campos no formato MM/AAAA."""

    MESES_ABREV = ["Jan","Fev","Mar","Abr","Mai","Jun",
                   "Jul","Ago","Set","Out","Nov","Dez"]

    def __init__(self, parent, entry_widget, titulo="Selecione Mês/Ano"):
        self.entry = entry_widget

        try:
            partes = entry_widget.get().split("/")
            self.mes = int(partes[0]); self.ano = int(partes[1])
        except Exception:
            self.mes = datetime.now().month; self.ano = datetime.now().year

        self.top = tk.Toplevel(parent)
        self.top.title(titulo)
        self.top.resizable(False, False)
        self.top.grab_set()
        self.top.configure(bg="#2C3E50")

        self._construir()
        self._centralizar(parent)

    def _centralizar(self, parent):
        parent.update_idletasks()
        x = parent.winfo_rootx() + parent.winfo_width()  // 2 - 130
        y = parent.winfo_rooty() + parent.winfo_height() // 2 - 110
        self.top.geometry(f"+{x}+{y}")

    def _construir(self):
        # ── Navegação de ano ────────────────────────────────────────────
        nav = tk.Frame(self.top, bg="#2C3E50"); nav.pack(fill="x", padx=6, pady=6)
        tk.Button(nav, text="◀", font=("Arial",9,"bold"), bg="#1A252F", fg="white",
                  relief="flat", bd=0, padx=8,
                  command=lambda: self._mudar_ano(-1)).pack(side="left")
        self.lbl_ano = tk.Label(nav, font=("Arial",11,"bold"),
                                bg="#2C3E50", fg="white", width=10)
        self.lbl_ano.pack(side="left", expand=True)
        tk.Button(nav, text="▶", font=("Arial",9,"bold"), bg="#1A252F", fg="white",
                  relief="flat", bd=0, padx=8,
                  command=lambda: self._mudar_ano(1)).pack(side="right")

        # ── Grid de meses ───────────────────────────────────────────────
        self.frame_meses = tk.Frame(self.top, bg="#2C3E50")
        self.frame_meses.pack(padx=8, pady=4)

        # ── Rodapé ──────────────────────────────────────────────────────
        rod = tk.Frame(self.top, bg="#1A252F"); rod.pack(fill="x", pady=(4,4))
        tk.Button(rod, text="Mês Atual", font=("Arial",8), bg="#27AE60", fg="white",
                  relief="flat", bd=0, padx=8, pady=3,
                  command=self._selecionar_atual).pack(side="left", padx=6, pady=4)
        tk.Button(rod, text="Cancelar", font=("Arial",8), bg="#C0392B", fg="white",
                  relief="flat", bd=0, padx=8, pady=3,
                  command=self.top.destroy).pack(side="right", padx=6, pady=4)

        self._renderizar()

    def _renderizar(self):
        for w in self.frame_meses.winfo_children():
            w.destroy()
        self.lbl_ano.config(text=str(self.ano))
        hoje = datetime.now()

        for i, abrev in enumerate(self.MESES_ABREV):
            linha, col = divmod(i, 3)
            num_mes = i + 1
            selecionado = (num_mes == self.mes and self.ano == self.ano)
            eh_atual    = (num_mes == hoje.month and self.ano == hoje.year)

            bg   = "#2980B9" if (num_mes == self.mes) else ("#27AE60" if eh_atual else "#3D566E")
            font = ("Arial", 9, "bold") if (num_mes == self.mes or eh_atual) else ("Arial", 9)

            tk.Button(
                self.frame_meses, text=abrev,
                font=font, bg=bg, fg="white",
                relief="flat", bd=0, width=6, height=2,
                activebackground="#1A6898", activeforeground="white",
                command=lambda m=num_mes: self._selecionar(m)
            ).grid(row=linha, column=col, padx=2, pady=2)

    def _mudar_ano(self, delta):
        self.ano += delta
        self._renderizar()

    def _selecionar(self, mes):
        self.entry.delete(0, "end")
        self.entry.insert(0, f"{mes:02d}/{self.ano}")
        self.top.destroy()

    def _selecionar_atual(self):
        hoje = datetime.now()
        self.entry.delete(0, "end")
        self.entry.insert(0, hoje.strftime("%m/%Y"))
        self.top.destroy()


# ==========================================
# 3. INTERFACE GRÁFICA PRINCIPAL
# ==========================================
class AplicacaoOficina:
    def __init__(self, root):
        self.root = root
        self.root.title("Multi Escape - Sistema de Gestão ERP v1.2")
        
        self.caminho_imagem_selecionada = ""
        self.lista_produtos_temporaria = []
        self._mapa_sugestoes_peca = {}
        self.id_fornecedor_selecionado = None
        self.id_peca_selecionada = None
        self.id_item_orcamento_selecionado_idx = None
        self.id_orcamento_editando = None
        self.ultimo_orcamento_salvo_id = None
        self.id_modelo_custom_selecionado = None
        
        self.flags_parcelas = [tk.BooleanVar(value=False) for _ in range(10)]
        self.labels_valores_parcelas = [None for _ in range(10)]
        self.labels_detalhe_parcelas = [None for _ in range(10)]

        # ── Cache de logos de marcas ──────────────────────────────────────
        self._logo_cache: dict = {}          # marca → PhotoImage
        self._logo_placeholder = None        # imagem padrão quando logo não disponível
        self._logos_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logos_marcas")
        os.makedirs(self._logos_dir, exist_ok=True)

        # Mapeamento marca → slug do repositório car-logos-dataset (MIT)
        # https://raw.githubusercontent.com/filippofilip95/car-logos-dataset/master/logos/thumb/{slug}.png
        self._LOGO_SLUGS = {
            "Fiat":           "fiat",
            "Volkswagen":     "volkswagen",
            "Chevrolet":      "chevrolet",
            "Hyundai":        "hyundai",
            "Nissan":         "nissan",
            "Renault":        "renault",
            "Jeep":           "jeep",
            "Toyota":         "toyota",
            "Honda":          "honda",
            "Ford":           "ford",
            "Peugeot":        "peugeot",
            "Citroën":        "citroen",
            "Mitsubishi":     "mitsubishi",
            "Caoa Chery":     "chery",
            "GWM":            "great-wall",
            "BYD":            "byd",
            "Mercedes-Benz":  "mercedes-benz",
            "BMW":            "bmw",
            "Land Rover":     "land-rover",
            "Volvo":          "volvo",
        }

        self.estilo = ttk.Style()
        self.estilo.theme_use(CONFIG.get("tema_ttk", "clam"))

        # ── Fonte adaptada pela detecção de compatibilidade ───────────────
        FUI  = CONFIG.get("fonte_ui",  "Arial")

        # ── Paleta de cores ───────────────────────────────────────────────
        COR_PRIMARIA   = "#1B2631"
        COR_ACENTO     = "#2E86C1"
        COR_FUNDO      = "#F0F3F4"
        COR_CARD       = "#FFFFFF"
        COR_BORDA      = "#D5D8DC"
        COR_TEXTO      = "#1C2833"
        COR_VERDE      = "#1E8449"
        COR_VERMELHO   = "#C0392B"
        COR_AMARELO    = "#D4AC0D"

        self.root.configure(bg=COR_FUNDO)

        # ── Notebook (abas) ───────────────────────────────────────────────
        self.estilo.configure("TNotebook",
                              background=COR_PRIMARIA, borderwidth=0, tabmargins=[0,0,0,0])
        self.estilo.configure("TNotebook.Tab",
                              padding=[14, 7], font=(FUI, 9, "bold"),
                              background="#2E4057", foreground="#BDC3C7",
                              borderwidth=0)
        self.estilo.map("TNotebook.Tab",
                        background=[("selected", COR_ACENTO), ("active", "#3D566E")],
                        foreground=[("selected", "white"),    ("active", "white")])

        # ── Frames e LabelFrames ──────────────────────────────────────────
        self.estilo.configure("TFrame",       background=COR_FUNDO)
        self.estilo.configure("TLabelframe",  background=COR_CARD,  relief="flat",
                              borderwidth=1,  bordercolor=COR_BORDA)
        self.estilo.configure("TLabelframe.Label",
                              font=(FUI, 9, "bold"),
                              foreground=COR_ACENTO, background=COR_CARD)

        # ── Labels e Entries ──────────────────────────────────────────────
        self.estilo.configure("TLabel",   background=COR_CARD,  foreground=COR_TEXTO,
                              font=(FUI, 9))
        self.estilo.configure("TEntry",   fieldbackground="#FDFEFE", foreground=COR_TEXTO,
                              font=(FUI, 9), padding=3)
        self.estilo.configure("TCombobox", fieldbackground="#FDFEFE", foreground=COR_TEXTO,
                              font=(FUI, 9))

        # ── Botões padrão ─────────────────────────────────────────────────
        self.estilo.configure("TButton",
                              font=(FUI, 9, "bold"),
                              background=COR_ACENTO, foreground="white",
                              padding=[8, 4], relief="flat", borderwidth=0)
        self.estilo.map("TButton",
                        background=[("active", "#1A5276"), ("pressed", "#154360")],
                        foreground=[("active", "white")])

        # ── Botões de ação especializados ─────────────────────────────────
        self.estilo.configure("Aprovar.TButton",
                              font=(FUI, 9, "bold"),
                              background=COR_VERDE, foreground="white",
                              padding=[8, 4], relief="flat")
        self.estilo.map("Aprovar.TButton",
                        background=[("active", "#145A32"), ("pressed", "#0E6655")])

        self.estilo.configure("Estorno.TButton",
                              font=(FUI, 9, "bold"),
                              background=COR_VERMELHO, foreground="white",
                              padding=[8, 4], relief="flat")
        self.estilo.map("Estorno.TButton",
                        background=[("active", "#922B21"), ("pressed", "#7B241C")])

        self.estilo.configure("Baixa.TButton",
                              font=(FUI, 9, "bold"),
                              background="#117A65", foreground="white",
                              padding=[8, 4], relief="flat")
        self.estilo.map("Baixa.TButton",
                        background=[("active", "#0E6655"), ("pressed", "#0B5345")])

        # ── Treeview ──────────────────────────────────────────────────────
        self.estilo.configure("Treeview",
                              background=COR_CARD, fieldbackground=COR_CARD,
                              foreground=COR_TEXTO, font=(FUI, 9),
                              rowheight=24, borderwidth=0)
        self.estilo.configure("Treeview.Heading",
                              font=(FUI, 9, "bold"),
                              background=COR_PRIMARIA, foreground="white",
                              relief="flat", padding=[4, 6])
        self.estilo.map("Treeview",
                        background=[("selected", "#AED6F1")],
                        foreground=[("selected", COR_PRIMARIA)])
        self.estilo.map("Treeview.Heading",
                        background=[("active", COR_ACENTO)])

        # ── Scrollbar fina ────────────────────────────────────────────────
        self.estilo.configure("TScrollbar",
                              background=COR_BORDA, troughcolor=COR_FUNDO,
                              width=8, arrowsize=8)
        
        self.criar_layouts()
        self.atualizar_todos_os_dados()
        configurar_janela_monitor(self.root)

    # ── Helpers de data ──────────────────────────────────────────────────
    def _abrir_calendario(self, entry_widget):
        CalendarioPopup(self.root, entry_widget)

    def _abrir_mes_ano(self, entry_widget):
        MesAnoPopup(self.root, entry_widget)

    def _btn_cal(self, parent, entry_widget, tipo="data"):
        """Cria e retorna um botão 📅 vinculado ao entry_widget."""
        icone = "📅" if tipo == "data" else "🗓️"
        cmd   = (lambda e=entry_widget: self._abrir_calendario(e)) if tipo == "data" \
                else (lambda e=entry_widget: self._abrir_mes_ano(e))
        return tk.Button(parent, text=icone, font=("Arial", 9), relief="flat",
                         bg="#D5D8DC", activebackground="#AEB6BF",
                         bd=0, padx=2, pady=1, cursor="hand2", command=cmd)

    def _criar_frame_rolagem(self, parent):
        """Retorna frame interno com barra de rolagem vertical."""
        outer = ttk.Frame(parent)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)

        def _atualizar_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _ajustar_largura(event):
            canvas.itemconfig(win_id, width=event.width)

        def _rolar_mouse(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        inner.bind("<Configure>", _atualizar_scrollregion)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.bind("<Configure>", _ajustar_largura)
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _rolar_mouse))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return inner

    # ── Helpers de logo de marca ─────────────────────────────────────────
    def _obter_logo(self, marca: str, tamanho=(90, 90)):
        """Retorna PhotoImage do logo da marca. Baixa e armazena em cache."""
        chave = f"{marca}_{tamanho[0]}"
        if chave in self._logo_cache:
            return self._logo_cache[chave]

        slug = self._LOGO_SLUGS.get(marca)
        if not slug:
            return self._logo_placeholder_img(tamanho)

        caminho = os.path.join(self._logos_dir, f"{slug}.png")

        # Tenta baixar se ainda não tiver no disco
        if not os.path.exists(caminho):
            try:
                import urllib.request
                url = f"https://raw.githubusercontent.com/filippofilip95/car-logos-dataset/master/logos/thumb/{slug}.png"
                urllib.request.urlretrieve(url, caminho)
            except Exception:
                return self._logo_placeholder_img(tamanho)

        # Carrega e redimensiona com PIL (se disponível) ou tkinter direto
        try:
            from PIL import Image, ImageTk
            img = Image.open(caminho).convert("RGBA")
            img.thumbnail(tamanho, Image.LANCZOS)
            # Fundo branco para marcas com alpha transparente
            fundo = Image.new("RGBA", img.size, (240, 243, 244, 255))
            fundo.paste(img, mask=img.split()[3])
            photo = ImageTk.PhotoImage(fundo.convert("RGB"))
        except Exception:
            try:
                photo = tk.PhotoImage(file=caminho)
            except Exception:
                return self._logo_placeholder_img(tamanho)

        self._logo_cache[chave] = photo
        return photo

    def _logo_placeholder_img(self, tamanho=(90, 90)):
        """Retorna um PhotoImage vazio/placeholder quando não há logo."""
        if self._logo_placeholder is None:
            try:
                from PIL import Image, ImageTk
                img = Image.new("RGB", tamanho, (208, 215, 220))
                self._logo_placeholder = ImageTk.PhotoImage(img)
            except Exception:
                self._logo_placeholder = tk.PhotoImage(width=tamanho[0], height=tamanho[1])
        return self._logo_placeholder

    def _atualizar_logo_marca(self, marca: str = ""):
        """Atualiza o painel de logo na aba clientes em background thread."""
        if not hasattr(self, 'lbl_logo_marca'):
            return
        if not marca:
            marca = self.txt_marca.get() if hasattr(self, 'txt_marca') else ""
        if not marca:
            self.lbl_logo_marca.config(image=self._logo_placeholder_img(), text="")
            self.lbl_nome_marca.config(text="Selecione a Marca")
            return

        def _carregar():
            photo = self._obter_logo(marca)
            self.root.after(0, lambda: self._aplicar_logo(marca, photo))

        import threading
        threading.Thread(target=_carregar, daemon=True).start()

    def _aplicar_logo(self, marca: str, photo):
        if hasattr(self, 'lbl_logo_marca'):
            self.lbl_logo_marca.config(image=photo, text="")
            self.lbl_logo_marca.image = photo   # evita garbage collection
            self.lbl_nome_marca.config(text=marca)

    def criar_layouts(self):
        self.abas = ttk.Notebook(self.root)
        self.abas.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.aba_clientes = ttk.Frame(self.abas)
        self.aba_orcamentos = ttk.Frame(self.abas)
        self.aba_consulta_orcamentos = ttk.Frame(self.abas)
        self.aba_fornecedores = ttk.Frame(self.abas)
        self.aba_modelos_config = ttk.Frame(self.abas)
        self.aba_taxas_cartao = ttk.Frame(self.abas)
        self.aba_contas_receber = ttk.Frame(self.abas)
        self.aba_contas_pagar = ttk.Frame(self.abas)
        self.aba_fluxo_acumulado = ttk.Frame(self.abas)
        self.aba_sql_server = ttk.Frame(self.abas)
        self.aba_manual = ttk.Frame(self.abas)
        
        self.abas.add(self.aba_clientes, text="👥 Clientes & Veículos")
        self.abas.add(self.aba_orcamentos, text="📝 Novo Orçamento")
        self.abas.add(self.aba_consulta_orcamentos, text="🔍 Consultar Orçamentos")
        self.abas.add(self.aba_fornecedores, text="🚚 Fornecedores & Peças")
        self.abas.add(self.aba_modelos_config, text="⚙️ Marcas & Motores")
        self.abas.add(self.aba_taxas_cartao, text="💳 Taxas Cartão")
        self.abas.add(self.aba_contas_receber, text="💰 Contas a Receber")
        self.abas.add(self.aba_contas_pagar, text="💸 Contas a Pagar")
        self.abas.add(self.aba_fluxo_acumulado, text="📊 Fluxo Acumulado")
        self.abas.add(self.aba_sql_server, text="SQL Server")
        self.abas.add(self.aba_manual, text="📖 Apoio & Manual")
        
        self.montar_aba_clientes()
        self.montar_aba_orcamentos()
        self.montar_aba_consulta_orcamentos()
        self.montar_aba_fornecedores()
        self.montar_aba_modelos_config()
        self.montar_aba_taxas_cartao()
        self.montar_aba_contas_receber()
        self.montar_aba_contas_pagar()
        self.montar_aba_fluxo_acumulado()
        self.montar_aba_sql_server()
        self.montar_aba_manual()

    def montar_aba_sql_server(self):
        frame_conn = ttk.LabelFrame(self.aba_sql_server, text="Conexão SQL Server")
        frame_conn.pack(fill="x", padx=10, pady=8)

        self.sql_server_host = tk.StringVar(value="localhost")
        self.sql_server_database = tk.StringVar()
        self.sql_server_driver = tk.StringVar(value="ODBC Driver 17 for SQL Server")
        self.sql_server_windows_auth = tk.BooleanVar(value=True)
        self.sql_server_user = tk.StringVar()
        self.sql_server_limit = tk.StringVar(value="10000")

        linha1 = ttk.Frame(frame_conn)
        linha1.pack(fill="x", padx=8, pady=4)
        ttk.Label(linha1, text="Servidor:").pack(side="left")
        ttk.Entry(linha1, textvariable=self.sql_server_host, width=28).pack(side="left", padx=5)
        ttk.Label(linha1, text="Banco:").pack(side="left", padx=(12, 0))
        ttk.Entry(linha1, textvariable=self.sql_server_database, width=24).pack(side="left", padx=5)
        ttk.Label(linha1, text="Driver:").pack(side="left", padx=(12, 0))
        ttk.Entry(linha1, textvariable=self.sql_server_driver, width=28).pack(side="left", padx=5)

        linha2 = ttk.Frame(frame_conn)
        linha2.pack(fill="x", padx=8, pady=4)
        ttk.Checkbutton(linha2, text="Autenticação Windows", variable=self.sql_server_windows_auth).pack(side="left")
        ttk.Label(linha2, text="Usuário:").pack(side="left", padx=(14, 0))
        ttk.Entry(linha2, textvariable=self.sql_server_user, width=22).pack(side="left", padx=5)
        ttk.Label(linha2, text="Senha:").pack(side="left", padx=(12, 0))
        self.sql_server_password = ttk.Entry(linha2, width=22, show="*")
        self.sql_server_password.pack(side="left", padx=5)
        ttk.Label(linha2, text="Limite leitura:").pack(side="left", padx=(12, 0))
        ttk.Entry(linha2, textvariable=self.sql_server_limit, width=8).pack(side="left", padx=5)

        frame_query = ttk.LabelFrame(self.aba_sql_server, text="Consulta de leitura")
        frame_query.pack(fill="x", padx=10, pady=6)
        self.txt_sql_server_query = tk.Text(frame_query, height=5, wrap="word")
        self.txt_sql_server_query.pack(fill="x", padx=8, pady=6)
        self.txt_sql_server_query.insert("1.0", "SELECT TOP 1000 * FROM dbo.SuaTabela")

        frame_acoes = ttk.Frame(self.aba_sql_server)
        frame_acoes.pack(fill="x", padx=10, pady=4)
        ttk.Button(frame_acoes, text="Testar conexão", command=self.testar_sql_server).pack(side="left", padx=4)
        ttk.Button(frame_acoes, text="Executar leitura", command=self.executar_consulta_sql_server).pack(side="left", padx=4)
        self.lbl_sql_server_status = ttk.Label(frame_acoes, text="Pronto para conectar.", foreground="#1A5276")
        self.lbl_sql_server_status.pack(side="left", padx=14)

        frame_result = ttk.LabelFrame(self.aba_sql_server, text="Resultado")
        frame_result.pack(fill="both", expand=True, padx=10, pady=8)
        self.tree_sql_server = ttk.Treeview(frame_result, show="headings", height=16)
        sb_y = ttk.Scrollbar(frame_result, orient="vertical", command=self.tree_sql_server.yview)
        sb_x = ttk.Scrollbar(frame_result, orient="horizontal", command=self.tree_sql_server.xview)
        self.tree_sql_server.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        self.tree_sql_server.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")
        sb_x.grid(row=1, column=0, sticky="ew")
        frame_result.rowconfigure(0, weight=1)
        frame_result.columnconfigure(0, weight=1)

    def _sql_server_conn_str(self):
        driver = self.sql_server_driver.get().strip() or "ODBC Driver 17 for SQL Server"
        server = self.sql_server_host.get().strip()
        database = self.sql_server_database.get().strip()
        if not server or not database:
            raise ValueError("Informe servidor e banco de dados.")

        partes = [
            f"DRIVER={{{driver}}}",
            f"SERVER={server}",
            f"DATABASE={database}",
        ]
        if self.sql_server_windows_auth.get():
            partes.append("Trusted_Connection=yes")
        else:
            usuario = self.sql_server_user.get().strip()
            senha = self.sql_server_password.get()
            if not usuario:
                raise ValueError("Informe o usuário ou use autenticação Windows.")
            partes.extend([f"UID={usuario}", f"PWD={senha}"])
        return ";".join(partes) + ";"

    def _set_sql_server_status(self, texto, cor="#1A5276"):
        self.lbl_sql_server_status.config(text=texto, foreground=cor)

    def testar_sql_server(self):
        def _run():
            try:
                import time
                import pyodbc
                inicio = time.perf_counter()
                conn = pyodbc.connect(self._sql_server_conn_str(), timeout=5)
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                conn.close()
                tempo = (time.perf_counter() - inicio) * 1000
                self.root.after(0, lambda: self._set_sql_server_status(f"Conexão OK em {tempo:.0f} ms", "#1E8449"))
            except ImportError:
                self.root.after(0, lambda: self._set_sql_server_status("Instale o pacote pyodbc para conectar ao SQL Server.", "#C0392B"))
            except Exception as e:
                logging.exception("Falha ao testar conexão SQL Server")
                erro = str(e)
                self.root.after(0, lambda: self._set_sql_server_status(f"Falha: {erro}", "#C0392B"))

        self._set_sql_server_status("Testando conexão...")
        threading.Thread(target=_run, daemon=True).start()

    def executar_consulta_sql_server(self):
        query = self.txt_sql_server_query.get("1.0", "end-1c").strip()
        if not query:
            messagebox.showwarning("Aviso", "Informe uma consulta SELECT.")
            return
        if not query.lower().lstrip().startswith(("select", "with")):
            messagebox.showwarning("Aviso", "Esta tela aceita apenas consultas de leitura.")
            return
        try:
            limite = max(1, int(self.sql_server_limit.get() or "10000"))
        except ValueError:
            messagebox.showwarning("Aviso", "Limite de leitura inválido.")
            return

        def _run():
            try:
                import time
                import pyodbc
                inicio = time.perf_counter()
                conn = pyodbc.connect(self._sql_server_conn_str(), timeout=10)
                cursor = conn.cursor()
                cursor.execute(query)
                colunas = [col[0] for col in cursor.description] if cursor.description else []
                linhas = []
                while len(linhas) < limite:
                    lote = cursor.fetchmany(min(1000, limite - len(linhas)))
                    if not lote:
                        break
                    linhas.extend(lote)
                conn.close()
                tempo = time.perf_counter() - inicio
                self.root.after(0, lambda: self._popular_sql_server_resultado(colunas, linhas, tempo))
            except ImportError:
                self.root.after(0, lambda: self._set_sql_server_status("Instale o pacote pyodbc para conectar ao SQL Server.", "#C0392B"))
            except Exception as e:
                logging.exception("Falha ao executar consulta SQL Server")
                erro = str(e)
                self.root.after(0, lambda: self._set_sql_server_status(f"Falha: {erro}", "#C0392B"))

        self._set_sql_server_status("Executando leitura...")
        threading.Thread(target=_run, daemon=True).start()

    def _popular_sql_server_resultado(self, colunas, linhas, tempo):
        self.tree_sql_server.delete(*self.tree_sql_server.get_children())
        self.tree_sql_server["columns"] = colunas

        for col in colunas:
            self.tree_sql_server.heading(col, text=col)
            self.tree_sql_server.column(col, width=140, anchor="w")

        for linha in linhas[:1000]:
            self.tree_sql_server.insert("", "end", values=[str(v) if v is not None else "" for v in linha])

        lps = (len(linhas) / tempo) if tempo > 0 else 0
        texto = f"{len(linhas)} linhas lidas em {tempo:.3f}s ({lps:,.0f} linhas/s). Exibindo até 1000 linhas."
        self._set_sql_server_status(texto, "#1E8449")

    def montar_aba_clientes(self):
        # ── Layout principal: formulário à esquerda + logo à direita ─────
        frame_principal = ttk.Frame(self.aba_clientes)
        frame_principal.pack(fill="x", padx=10, pady=5)

        frame_form = ttk.LabelFrame(frame_principal, text="Dados do Cliente e Motorização")
        frame_form.pack(side="left", fill="both", expand=True)

        # ── Painel de logo da marca ───────────────────────────────────────
        frame_logo_card = tk.Frame(frame_principal, bg="#FFFFFF",
                                   relief="flat", bd=1,
                                   highlightbackground="#D5D8DC", highlightthickness=1)
        frame_logo_card.pack(side="left", padx=(8, 0), pady=0, fill="y")

        self.lbl_logo_marca = tk.Label(frame_logo_card, bg="#FFFFFF",
                                        width=11, height=6, cursor="arrow")
        self.lbl_logo_marca.pack(padx=10, pady=(12, 4))

        self.lbl_nome_marca = tk.Label(frame_logo_card, text="Selecione a Marca",
                                        font=(CONFIG.get("fonte_ui","Arial"), 8, "bold"),
                                        bg="#FFFFFF", fg="#2E86C1", wraplength=100)
        self.lbl_nome_marca.pack(padx=8, pady=(0, 8))

        lbl_hint = tk.Label(frame_logo_card, text="Logo carregado\nautomaticamente",
                            font=(CONFIG.get("fonte_ui","Arial"), 7), bg="#FFFFFF", fg="#AAB7B8")
        lbl_hint.pack(padx=8, pady=(0, 6))

        # Inicializa placeholder
        self._logo_placeholder_img()
        self.lbl_logo_marca.config(image=self._logo_placeholder_img())
        self.lbl_logo_marca.image = self._logo_placeholder_img()

        # ── Campos do formulário ──────────────────────────────────────────
        ttk.Label(frame_form, text="Nome do Cliente * :").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.txt_nome = ttk.Combobox(frame_form, width=28); self.txt_nome.grid(row=0, column=1, padx=5, pady=5)
        self.txt_nome.bind("<<ComboboxSelected>>", self.ao_selecionar_nome)
        
        ttk.Label(frame_form, text="Placa * :").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.txt_placa = ttk.Combobox(frame_form, width=15); self.txt_placa.grid(row=0, column=3, padx=5, pady=5)
        self.txt_placa.bind("<<ComboboxSelected>>", self.ao_selecionar_placa)
        
        ttk.Label(frame_form, text="Marca:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.txt_marca = ttk.Combobox(frame_form, width=28); self.txt_marca.grid(row=1, column=1, padx=5, pady=5)
        self.txt_marca.bind("<<ComboboxSelected>>", self.filtrar_modelos_por_marca)
        
        ttk.Label(frame_form, text="Modelo/Motor:").grid(row=1, column=2, padx=5, pady=5, sticky="w")
        self.txt_veiculo = ttk.Combobox(frame_form, width=20); self.txt_veiculo.grid(row=1, column=3, padx=5, pady=5)
        
        ttk.Label(frame_form, text="Ano:").grid(row=1, column=4, padx=5, pady=5, sticky="w")
        self.txt_ano = ttk.Combobox(frame_form, width=10); self.txt_ano.grid(row=1, column=5, padx=5, pady=5)
        ano_atual = datetime.now().year
        self.txt_ano['values'] = [str(ano) for ano in range(ano_atual, ano_atual - 51, -1)]
        self.txt_ano.set(str(ano_atual))
        
        ttk.Label(frame_form, text="Contato:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.txt_contato = ttk.Entry(frame_form, width=30); self.txt_contato.grid(row=2, column=1, padx=5, pady=5)
        ttk.Label(frame_form, text="E-mail:").grid(row=2, column=2, padx=5, pady=5, sticky="w")
        self.txt_email = ttk.Entry(frame_form, width=20); self.txt_email.grid(row=2, column=3, padx=5, pady=5)
        ttk.Label(frame_form, text="Cor:").grid(row=2, column=4, padx=5, pady=5, sticky="w")
        self.txt_cor = ttk.Entry(frame_form, width=10); self.txt_cor.grid(row=2, column=5, padx=5, pady=5)
        
        frame_crm = ttk.LabelFrame(self.aba_clientes, text="Painel Histórico do Cliente (CRM)")
        frame_crm.pack(fill="x", padx=10, pady=5)
        self.lbl_crm_efetuados = ttk.Label(frame_crm, text="Orçamentos Efetuados: 0", font=("Arial", 10, "bold"), foreground="dimgray")
        self.lbl_crm_efetuados.grid(row=0, column=0, padx=20, pady=8, sticky="w")
        self.lbl_crm_executados = ttk.Label(frame_crm, text="Orçamentos Executados: 0", font=("Arial", 10, "bold"), foreground="green")
        self.lbl_crm_executados.grid(row=0, column=1, padx=20, pady=8, sticky="w")
        self.lbl_crm_ultimo = ttk.Label(frame_crm, text="Último Serviço Executado: Nenhum registro", font=("Arial", 10, "italic"), foreground="blue")
        self.lbl_crm_ultimo.grid(row=0, column=2, padx=20, pady=8, sticky="w")
        
        frame_botoes = ttk.Frame(self.aba_clientes); frame_botoes.pack(fill="x", padx=10, pady=5)
        ttk.Button(frame_botoes, text="Salvar Cliente", command=self.salvar_cliente).pack(side="left", padx=5)
        ttk.Button(frame_botoes, text="Modificar Dados", command=self.editar_cliente).pack(side="left", padx=5)
        ttk.Button(frame_botoes, text="Excluir Registro", command=self.excluir_cliente).pack(side="left", padx=5)
        ttk.Button(frame_botoes, text="Limpar", command=self.limpar_campos_cliente).pack(side="left", padx=5)
        
        self.tree_clientes = ttk.Treeview(self.aba_clientes, columns=("ID", "Nome", "Placa", "Marca", "Modelo", "Ano"), show="headings")
        self.tree_clientes.heading("ID", text="ID"); self.tree_clientes.heading("Nome", text="Nome"); self.tree_clientes.heading("Placa", text="Placa")
        self.tree_clientes.heading("Marca", text="Marca"); self.tree_clientes.heading("Modelo", text="Modelo / Motor"); self.tree_clientes.heading("Ano", text="Ano")
        self.tree_clientes.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree_clientes.bind("<<TreeviewSelect>>", self.ao_selecionar_grid_clientes)
        self.tree_clientes.tag_configure("par",   background="#EBF5FB")
        self.tree_clientes.tag_configure("impar", background="#FFFFFF")

    def montar_aba_orcamentos(self):
        cont = self._criar_frame_rolagem(self.aba_orcamentos)

        frame_topo_orc = ttk.Frame(cont)
        frame_topo_orc.pack(fill="x", padx=10, pady=(5, 0))
        self.lbl_orc_modo = ttk.Label(
            frame_topo_orc, text="Modo: Novo Orçamento",
            font=("Arial", 10, "bold"), foreground="#1A5276",
        )
        self.lbl_orc_modo.pack(side="left", padx=5)
        frame_btn_topo_orc = ttk.Frame(frame_topo_orc)
        frame_btn_topo_orc.pack(side="right")
        self.btn_ultimo_orc = ttk.Button(
            frame_btn_topo_orc, text="📂 Abrir Último Orçamento",
            command=self.abrir_ultimo_orcamento_salvo, state="disabled",
        )
        self.btn_ultimo_orc.pack(side="left", padx=5)
        ttk.Button(frame_btn_topo_orc, text="📄 Novo Orçamento em Branco",
                   command=self.limpar_formulario_orcamento).pack(side="left", padx=5)

        frame_dados_orc = ttk.LabelFrame(cont, text="Dados Gerais do Orçamento")
        frame_dados_orc.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(frame_dados_orc, text="ID Cliente * :").grid(row=0, column=0, padx=(5, 2), pady=5, sticky="w")
        self.txt_orc_cliente_id = ttk.Entry(frame_dados_orc, width=6)
        self.txt_orc_cliente_id.grid(row=0, column=1, padx=(0, 5), pady=5, sticky="w")
        self.txt_orc_cliente_id.bind("<FocusOut>", self._preencher_nome_por_id_orc)

        ttk.Label(frame_dados_orc, text="Nome:").grid(row=0, column=2, padx=(5, 2), pady=5, sticky="w")
        self.txt_orc_cliente_nome = ttk.Combobox(frame_dados_orc, width=18)
        self.txt_orc_cliente_nome.grid(row=0, column=3, padx=(0, 5), pady=5, sticky="w")
        self.txt_orc_cliente_nome.bind("<KeyRelease>", self.autocomplete_nome_cliente_orc)
        self.txt_orc_cliente_nome.bind("<<ComboboxSelected>>", self.ao_selecionar_nome_orc)
        self.txt_orc_cliente_nome.bind("<FocusOut>", self.ao_selecionar_nome_orc)

        ttk.Label(frame_dados_orc, text="Serviço:").grid(row=0, column=4, padx=(5, 2), pady=5, sticky="w")
        self.txt_servico_sol = ttk.Entry(frame_dados_orc, width=16)
        self.txt_servico_sol.grid(row=0, column=5, padx=(0, 5), pady=5, sticky="w")

        ttk.Label(frame_dados_orc, text="Data:").grid(row=0, column=6, padx=(5, 2), pady=5, sticky="w")
        frame_data_orc = ttk.Frame(frame_dados_orc)
        frame_data_orc.grid(row=0, column=7, padx=(0, 5), pady=5, sticky="w")
        self.txt_orc_data_atual = ttk.Entry(frame_data_orc, width=10)
        self.txt_orc_data_atual.insert(0, datetime.now().strftime("%d/%m/%Y"))
        self.txt_orc_data_atual.pack(side="left")
        self._btn_cal(frame_data_orc, self.txt_orc_data_atual, "data").pack(side="left", padx=1)

        ttk.Label(frame_dados_orc, text="Status:").grid(row=0, column=8, padx=(5, 2), pady=5, sticky="w")
        self.txt_status_orc = ttk.Combobox(
            frame_dados_orc,
            values=["Aguardando Retorno", "Aprovado", "Declinado"],
            width=14,
            state="readonly",
        )
        self.txt_status_orc.set("Aguardando Retorno")
        self.txt_status_orc.grid(row=0, column=9, padx=(0, 5), pady=5, sticky="w")
        
        frame_itens = ttk.LabelFrame(cont, text="Adicionar Peças no Orçamento")
        frame_itens.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(frame_itens, text="Cód:").grid(row=0, column=0, padx=2, pady=2)
        self.txt_item_cod = ttk.Entry(frame_itens, width=8); self.txt_item_cod.grid(row=0, column=1, padx=2, pady=2)
        self.txt_item_cod.bind("<FocusOut>", self.auto_buscar_peca_por_codigo)
        self.txt_item_cod.bind("<Return>", self.auto_buscar_peca_por_codigo)
        
        ttk.Label(frame_itens, text="Descrição:").grid(row=0, column=2, padx=5, pady=2)
        self.txt_item_desc = ttk.Combobox(frame_itens, width=36)
        self.txt_item_desc.grid(row=0, column=3, columnspan=2, padx=2, pady=2, sticky="ew")
        self.txt_item_desc.bind("<KeyRelease>", self.autocomplete_peca_orc)
        self.txt_item_desc.bind("<<ComboboxSelected>>", self.ao_selecionar_peca_orc)
        self.txt_item_desc.bind("<FocusOut>", self.ao_selecionar_peca_orc)
        ttk.Label(frame_itens, text="Qtd:").grid(row=0, column=5, padx=5, pady=2)
        self.txt_item_qtd = ttk.Entry(frame_itens, width=4); self.txt_item_qtd.grid(row=0, column=6, padx=2, pady=2)
        ttk.Label(frame_itens, text="Preço Venda:").grid(row=0, column=7, padx=5, pady=2)
        self.txt_item_valor = ttk.Entry(frame_itens, width=10); self.txt_item_valor.grid(row=0, column=8, padx=2, pady=2)
        frame_itens.columnconfigure(3, weight=1)
        
        ttk.Label(frame_itens, text="Fornecedor:").grid(row=1, column=0, padx=2, pady=2, sticky="w")
        self.txt_item_fornecedor_combo = ttk.Combobox(frame_itens, width=15); self.txt_item_fornecedor_combo.grid(row=1, column=1, padx=2, pady=2)
        ttk.Label(frame_itens, text="Custo Compra:").grid(row=1, column=2, padx=5, pady=2)
        self.txt_item_custo_compra = ttk.Entry(frame_itens, width=10); self.txt_item_custo_compra.grid(row=1, column=3, padx=2, pady=2)
        ttk.Label(frame_itens, text="Prazo Pgto:").grid(row=1, column=4, padx=5, pady=2)
        self.txt_item_prazo_forn = ttk.Combobox(frame_itens, values=["À Vista", "30 Dias", "60 Dias"], width=12)
        self.txt_item_prazo_forn.set("À Vista"); self.txt_item_prazo_forn.grid(row=1, column=5, columnspan=2, padx=2, pady=2)
        
        ttk.Button(frame_itens, text="+ Inserir Peça", command=self.adicionar_item_lista).grid(row=1, column=7, padx=5, pady=2)
        ttk.Button(frame_itens, text="✏️ Atualizar Peça", command=self.atualizar_item_lista).grid(row=1, column=8, padx=2, pady=2)
        ttk.Button(frame_itens, text="Excluir Peça", command=self.excluir_item_lista).grid(row=1, column=9, padx=2, pady=2)
        
        self.tree_itens = ttk.Treeview(cont, columns=("Cod", "Desc", "Qtd", "Unit", "Total", "Forn", "Custo", "Data"), show="headings", height=6)
        self.tree_itens.heading("Cod", text="Código"); self.tree_itens.heading("Desc", text="Descrição"); self.tree_itens.heading("Qtd", text="Qtd")
        self.tree_itens.heading("Unit", text="Preço Venda"); self.tree_itens.heading("Total", text="Total Venda")
        self.tree_itens.heading("Forn", text="Fornecedor"); self.tree_itens.heading("Custo", text="Custo Compra"); self.tree_itens.heading("Data", text="Data Inserção")
        self.tree_itens.pack(fill="x", padx=10, pady=5)
        self.tree_itens.bind("<<TreeviewSelect>>", self.ao_selecionar_item_carrinho)
        self.tree_itens.bind("<Double-1>", self._preencher_form_item_carrinho)

        frame_totais_orc = ttk.Frame(cont)
        frame_totais_orc.pack(fill="x", padx=10, pady=2)
        self.lbl_total_pecas_orc = ttk.Label(frame_totais_orc, text="Peças: R$ 0,00", font=("Arial", 10, "bold"))
        self.lbl_total_pecas_orc.pack(side="left", padx=10)
        self.lbl_total_mo_orc = ttk.Label(frame_totais_orc, text="M.O.: R$ 0,00", font=("Arial", 10, "bold"))
        self.lbl_total_mo_orc.pack(side="left", padx=10)
        self.lbl_total_geral_orc = ttk.Label(
            frame_totais_orc, text="TOTAL GERAL: R$ 0,00",
            font=("Arial", 11, "bold"), foreground="#1A5276",
        )
        self.lbl_total_geral_orc.pack(side="left", padx=15)
        
        frame_fechamento = ttk.Frame(cont); frame_fechamento.pack(fill="x", padx=10, pady=5)
        ttk.Label(frame_fechamento, text="Mão de Obra (M.O):").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.txt_valor_mo = ttk.Entry(frame_fechamento, width=15); self.txt_valor_mo.insert(0, "0.00"); self.txt_valor_mo.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.txt_valor_mo.bind("<KeyRelease>", lambda e: self.recalcular_parcelas_dinamicas())
        ttk.Label(frame_fechamento, text="Pagamento Info:").grid(row=0, column=2, padx=20, pady=5, sticky="w")
        self.txt_pagamento = ttk.Entry(frame_fechamento, width=35); self.txt_pagamento.grid(row=0, column=3, padx=5, pady=5, sticky="w")

        ttk.Label(frame_fechamento, text="Previsão de Entrega (Data/Prazo):").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        frame_prev = ttk.Frame(frame_fechamento); frame_prev.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky="w")
        self.txt_previsao_entrega = ttk.Entry(frame_prev, width=20)
        self.txt_previsao_entrega.pack(side="left")
        self._btn_cal(frame_prev, self.txt_previsao_entrega, "data").pack(side="left", padx=1)
        
        ttk.Label(frame_fechamento, text="Observação Livre:").grid(row=2, column=0, padx=5, pady=5, sticky="nw")
        self.txt_observacao = tk.Text(frame_fechamento, width=50, height=2); self.txt_observacao.grid(row=2, column=1, columnspan=3, padx=5, pady=5, sticky="w")
        
        frame_midias = ttk.Frame(frame_fechamento); frame_midias.grid(row=3, column=1, columnspan=3, sticky="w", pady=5)
        ttk.Button(frame_midias, text="Anexar Imagem OCR", command=self.fazer_ocr_imagem).pack(side="left", padx=2)
        self.lbl_status_img = ttk.Label(frame_midias, text="Nenhuma imagem vinculada.")

        frame_pag_cartao = ttk.LabelFrame(cont, text="Forma de Pagamento e Taxa do Cartão (juros somados ao total)")
        frame_pag_cartao.pack(fill="x", padx=10, pady=2)
        fp1 = ttk.Frame(frame_pag_cartao); fp1.pack(fill="x", padx=5, pady=3)
        ttk.Label(fp1, text="Forma:").pack(side="left", padx=5)
        self.cmb_forma_pagamento = ttk.Combobox(fp1, values=FORMAS_PAGAMENTO, width=18, state="readonly")
        self.cmb_forma_pagamento.set("À Vista / PIX")
        self.cmb_forma_pagamento.pack(side="left", padx=5)
        self.cmb_forma_pagamento.bind("<<ComboboxSelected>>", self._ao_mudar_forma_pagamento)
        ttk.Label(fp1, text="Bandeira:").pack(side="left", padx=(15, 5))
        self.cmb_bandeira_cartao = ttk.Combobox(fp1, values=BANDEIRAS_CARTAO, width=14, state="disabled")
        self.cmb_bandeira_cartao.set("Visa")
        self.cmb_bandeira_cartao.pack(side="left", padx=5)
        self.cmb_bandeira_cartao.bind("<<ComboboxSelected>>", lambda e: self.recalcular_parcelas_dinamicas())
        self.lbl_taxa_aplicada = ttk.Label(fp1, text="Taxa: —", font=("Arial", 9, "bold"), foreground="#117A65")
        self.lbl_taxa_aplicada.pack(side="left", padx=15)
        
        frame_parc = ttk.LabelFrame(cont, text="Condições de Parcelamento Estimadas (selecione a opção desejada)")
        frame_parc.pack(fill="x", padx=10, pady=2)
        frame_grid_p = ttk.Frame(frame_parc)
        frame_grid_p.pack(fill="x", padx=5, pady=4)
        frame_grid_p.columnconfigure(0, weight=1)
        frame_grid_p.columnconfigure(1, weight=1)

        FUI = CONFIG.get("fonte_ui", "Arial")
        for idx in range(1, 11):
            col_idx = (idx - 1) % 2
            row_idx = (idx - 1) // 2
            f_bloco = ttk.Frame(frame_grid_p, padding=(4, 2))
            f_bloco.grid(row=row_idx, column=col_idx, padx=6, pady=3, sticky="ew")

            linha_top = ttk.Frame(f_bloco)
            linha_top.pack(fill="x", anchor="w")
            ttk.Checkbutton(
                linha_top, text=f"{idx}X", variable=self.flags_parcelas[idx - 1],
                command=lambda i=idx - 1: self.ao_selecionar_parcela(i),
            ).pack(side="left")
            lbl_val = ttk.Label(
                linha_top, text=" R$ 0,00",
                font=(FUI, 9, "bold"), foreground="#1A5276",
            )
            lbl_val.pack(side="left", padx=(6, 0))

            lbl_det = ttk.Label(
                f_bloco, text="",
                font=(FUI, 8), foreground="#566573",
                wraplength=420, justify="left",
            )
            lbl_det.pack(fill="x", anchor="w", padx=(28, 0), pady=(1, 0))

            self.labels_valores_parcelas[idx - 1] = lbl_val
            self.labels_detalhe_parcelas[idx - 1] = lbl_det

        self.recalcular_parcelas_dinamicas()

        frame_catalogo_busca_base = ttk.LabelFrame(cont, text="Pesquisa Rápida de Peças Cadastradas")
        frame_catalogo_busca_base.pack(fill="x", padx=10, pady=5)
        self.txt_busca_peca_orc = ttk.Entry(frame_catalogo_busca_base, width=25); self.txt_busca_peca_orc.pack(side="top", anchor="w", padx=5, pady=2)
        self.txt_busca_peca_orc.bind("<KeyRelease>", self.carregar_catalogo_pecas)
        
        self.tree_catalogo_orc = ttk.Treeview(frame_catalogo_busca_base, columns=("ID", "Peça", "Valor", "Fornecedor"), show="headings", height=3)
        self.tree_catalogo_orc.heading("ID", text="ID"); self.tree_catalogo_orc.heading("Peça", text="Descrição Peça"); self.tree_catalogo_orc.heading("Valor", text="Preço"); self.tree_catalogo_orc.heading("Fornecedor", text="Fornecedor")
        self.tree_catalogo_orc.pack(fill="x", padx=5, pady=2)
        self.tree_catalogo_orc.bind("<Double-1>", self.ao_dar_duplo_clique_peca_catalogo)

        self.btn_salvar_orcamento = ttk.Button(
            cont,
            text="SALVAR PROPOSTA DE ORÇAMENTO (GERAR PDF)",
            command=self.finalizar_orcamento,
        )
        self.btn_salvar_orcamento.pack(pady=8, padx=10, fill="x")

    # ==========================================
    # CONSULTA DE ORÇAMENTOS — REFORMULADA
    # ==========================================
    def montar_aba_consulta_orcamentos(self):
        # ── Painel de KPIs coloridos ─────────────────────────────────────
        frame_kpi = tk.Frame(self.aba_consulta_orcamentos, bg="#1B2631")
        frame_kpi.pack(fill="x", padx=0, pady=0)

        def _kpi_card(parent, titulo, valor_attr, bg, col):
            f = tk.Frame(parent, bg=bg, padx=15, pady=8)
            f.grid(row=0, column=col, sticky="nsew", padx=1, pady=1)
            parent.columnconfigure(col, weight=1)
            tk.Label(f, text=titulo, font=(CONFIG.get("fonte_ui","Arial"), 8), bg=bg, fg="#ECF0F1").pack()
            lbl = tk.Label(f, text="0", font=(CONFIG.get("fonte_ui","Arial"), 14, "bold"), bg=bg, fg="white")
            lbl.pack()
            setattr(self, valor_attr, lbl)

        _kpi_card(frame_kpi, "⏳ Aguardando",  "_kpi_aguardando", "#2E4057", 0)
        _kpi_card(frame_kpi, "👍 Aprovados",   "_kpi_aprovados",  "#1A5276", 1)
        _kpi_card(frame_kpi, "🔧 Executados",  "_kpi_executados", "#1E8449", 2)
        _kpi_card(frame_kpi, "❌ Declinados",  "_kpi_declinados", "#922B21", 3)
        _kpi_card(frame_kpi, "💰 Total Faturado", "_kpi_faturado", "#6C3483", 4)

        frame_busca = ttk.LabelFrame(self.aba_consulta_orcamentos, text="Filtrar e Gerenciar Propostas por Período")
        frame_busca.pack(fill="x", padx=10, pady=5)
        
        frame_filtros_linha = ttk.Frame(frame_busca)
        frame_filtros_linha.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(frame_filtros_linha, text="Data Início (DD/MM/AAAA):").pack(side="left", padx=5)
        frame_di = ttk.Frame(frame_filtros_linha); frame_di.pack(side="left", padx=2)
        self.txt_filtro_orc_data_ini = ttk.Entry(frame_di, width=10)
        self.txt_filtro_orc_data_ini.pack(side="left")
        self._btn_cal(frame_di, self.txt_filtro_orc_data_ini, "data").pack(side="left", padx=1)
        
        ttk.Label(frame_filtros_linha, text="Data Fim (DD/MM/AAAA):").pack(side="left", padx=5)
        frame_df = ttk.Frame(frame_filtros_linha); frame_df.pack(side="left", padx=2)
        self.txt_filtro_orc_data_fim = ttk.Entry(frame_df, width=10)
        self.txt_filtro_orc_data_fim.pack(side="left")
        self._btn_cal(frame_df, self.txt_filtro_orc_data_fim, "data").pack(side="left", padx=1)
        
        ttk.Button(frame_filtros_linha, text="🔍 Pesquisar por Período", command=self.carregar_todos_orcamentos_consulta).pack(side="left", padx=10)
        ttk.Button(frame_filtros_linha, text="Limpar Filtros", command=self.limpar_filtros_busca_orcamento).pack(side="left", padx=5)
        
        frame_acoes_linha = ttk.Frame(frame_busca)
        frame_acoes_linha.pack(fill="x", padx=5, pady=5)

        # Ações de status do orçamento (operam sobre o orçamento inteiro)
        ttk.Button(frame_acoes_linha, text="↩️ Estornar para Aguardando",
                   command=self.estornar_execucao_orcamento, style="Estorno.TButton").pack(side="right", padx=5)
        ttk.Button(frame_acoes_linha, text="❌ Excluir Orçamento",
                   command=self.excluir_orcamento_sistema, style="Estorno.TButton").pack(side="right", padx=5)
        ttk.Button(frame_acoes_linha, text="🔧 Marcar como Executado",
                   command=self.mudar_orcamento_para_executado, style="Aprovar.TButton").pack(side="right", padx=5)
        ttk.Button(frame_acoes_linha, text="👍 Cliente Aprovou",
                   command=self.mudar_orcamento_para_aprovado, style="Aprovar.TButton").pack(side="right", padx=5)
        ttk.Button(frame_acoes_linha, text="✏️ Editar Orçamento",
                   command=self.carregar_orcamento_selecionado_para_edicao).pack(side="right", padx=5)

        # Ações de baixa por parcela (operam sobre a linha/parcela selecionada)
        frame_baixa_linha = ttk.Frame(frame_busca)
        frame_baixa_linha.pack(fill="x", padx=5, pady=2)
        ttk.Label(frame_baixa_linha, text="Ações na Parcela Selecionada →", font=("Arial", 9, "bold")).pack(side="left", padx=5)
        ttk.Button(frame_baixa_linha, text="✅ Dar Baixa na Parcela (Recebido)",
                   command=self.baixar_parcela_consulta, style="Baixa.TButton").pack(side="left", padx=5)
        ttk.Button(frame_baixa_linha, text="↩️ Estornar Baixa da Parcela",
                   command=self.estornar_parcela_consulta, style="Estorno.TButton").pack(side="left", padx=5)

        # Grid principal — agora com colunas de parcela e status de recebimento
        colunas = ("OrcID", "Cliente", "Serviço", "Parcela", "ValorParcela", "TotalGeral", "StatusOrc", "StatusParcela", "Vencimento", "Data", "CR_ID")
        self.tree_consulta_orc = ttk.Treeview(self.aba_consulta_orcamentos, columns=colunas, show="headings", height=18)

        self.tree_consulta_orc.heading("OrcID",        text="Nº Orç")
        self.tree_consulta_orc.heading("Cliente",      text="Cliente")
        self.tree_consulta_orc.heading("Serviço",      text="Serviço Solicitado")
        self.tree_consulta_orc.heading("Parcela",      text="Parcela")
        self.tree_consulta_orc.heading("ValorParcela", text="Valor Parcela")
        self.tree_consulta_orc.heading("TotalGeral",   text="Total Orçamento")
        self.tree_consulta_orc.heading("StatusOrc",    text="Status Orçamento")
        self.tree_consulta_orc.heading("StatusParcela",text="Status Pagamento")
        self.tree_consulta_orc.heading("Vencimento",   text="Vencimento")
        self.tree_consulta_orc.heading("Data",         text="Data Emissão")
        self.tree_consulta_orc.heading("CR_ID",        text="ID Parcela")

        # Larguras das colunas
        self.tree_consulta_orc.column("OrcID",         width=55,  anchor="center")
        self.tree_consulta_orc.column("Cliente",       width=130)
        self.tree_consulta_orc.column("Serviço",       width=160)
        self.tree_consulta_orc.column("Parcela",       width=60,  anchor="center")
        self.tree_consulta_orc.column("ValorParcela",  width=90,  anchor="e")
        self.tree_consulta_orc.column("TotalGeral",    width=100, anchor="e")
        self.tree_consulta_orc.column("StatusOrc",     width=120, anchor="center")
        self.tree_consulta_orc.column("StatusParcela", width=110, anchor="center")
        self.tree_consulta_orc.column("Vencimento",    width=85,  anchor="center")
        self.tree_consulta_orc.column("Data",          width=85,  anchor="center")
        self.tree_consulta_orc.column("CR_ID",         width=65,  anchor="center")

        # Scrollbar
        sb = ttk.Scrollbar(self.aba_consulta_orcamentos, orient="vertical", command=self.tree_consulta_orc.yview)
        self.tree_consulta_orc.configure(yscrollcommand=sb.set)
        self.tree_consulta_orc.pack(fill="both", expand=True, padx=10, pady=5, side="left")
        sb.pack(side="right", fill="y", pady=5)

        # Tags de cor por status
        self.tree_consulta_orc.tag_configure("aprovado",  background="#CCE5FF", foreground="#004085")
        self.tree_consulta_orc.tag_configure("executado", background="#D4EDDA", foreground="#155724")
        self.tree_consulta_orc.tag_configure("declinado", background="#F8D7DA", foreground="#721C24")
        self.tree_consulta_orc.tag_configure("pago",      background="#C8F7C5", foreground="#145214")
        self.tree_consulta_orc.tag_configure("atrasado",  background="#FDECEA", foreground="#7B0000")

    # ==========================================
    # CARREGAR CONSULTA — LÓGICA DE PARCELAS
    # ==========================================
    def carregar_todos_orcamentos_consulta(self):
        for item in self.tree_consulta_orc.get_children():
            self.tree_consulta_orc.delete(item)

        data_ini = self.txt_filtro_orc_data_ini.get().strip()
        data_fim = self.txt_filtro_orc_data_fim.get().strip()
        data_ini_iso = _data_br_para_iso(data_ini) if data_ini else None
        data_fim_iso = _data_br_para_iso(data_fim) if data_fim else None

        if (data_ini and not data_ini_iso) or (data_fim and not data_fim_iso):
            messagebox.showwarning("Aviso", "Informe as datas no formato DD/MM/AAAA.")
            return

        conn = conectar_banco()
        cursor = conn.cursor()

        query = '''
            SELECT o.id, c.nome, o.servico_solicitado, o.valor_mao_de_obra,
                   COALESCE((SELECT SUM(p.quantidade * p.valor_unitario)
                             FROM produtos_orcamento p WHERE p.orcamento_id = o.id), 0.0) AS total_pecas,
                   o.status, o.data_orcamento, o.valor_liquido_estimado
            FROM orcamentos o
            JOIN clientes c ON o.cliente_id = c.id
        '''
        filtros = []
        filtros_sql = []
        data_sql = "substr(o.data_orcamento, 7, 4) || '-' || substr(o.data_orcamento, 4, 2) || '-' || substr(o.data_orcamento, 1, 2)"
        if data_ini_iso:
            filtros_sql.append(f"{data_sql} >= ?")
            filtros.append(data_ini_iso)
        if data_fim_iso:
            filtros_sql.append(f"{data_sql} <= ?")
            filtros.append(data_fim_iso)
        if filtros_sql:
            query += " WHERE " + " AND ".join(filtros_sql)
        query += " ORDER BY o.id DESC"

        cursor.execute(query, filtros)
        orcamentos = cursor.fetchall()

        hoje = datetime.now().date()

        totais_por_orcamento = {}

        for orc_id, cliente, servico, v_mo, total_pecas, status, data_orc, valor_salvo in orcamentos:
            total_base = (v_mo or 0.0) + (total_pecas or 0.0)
            total_geral = max(total_base, float(valor_salvo or 0.0))
            totais_por_orcamento[orc_id] = total_geral
            status_lower = status.lower() if status else ""

            if status in ("Aprovado", "Executado"):
                # Buscar parcelas do contas_receber para este orçamento
                cursor.execute('''
                    SELECT id, num_parcela, valor_parcela, data_vencimento, status_pago
                    FROM contas_receber
                    WHERE orcamento_id = ?
                    ORDER BY id ASC
                ''', (orc_id,))
                parcelas = cursor.fetchall()

                if parcelas:
                    total_parcelas = sum((p[2] or 0.0) for p in parcelas)
                    if total_parcelas > 0:
                        total_geral = total_parcelas
                        totais_por_orcamento[orc_id] = total_geral
                    for cr_id, num_parcela, valor_parcela, data_venc, status_pago in parcelas:
                        # Define tag de cor da linha
                        if status_pago == "Pago":
                            tag = "pago"
                        else:
                            try:
                                dt_venc = datetime.strptime(data_venc, "%d/%m/%Y").date()
                                tag = "atrasado" if dt_venc < hoje else status_lower
                            except ValueError:
                                tag = status_lower

                        self.tree_consulta_orc.insert("", "end", values=(
                            orc_id,
                            cliente,
                            servico,
                            num_parcela,
                            f"R$ {valor_parcela:.2f}",
                            f"R$ {total_geral:.2f}",
                            status,
                            status_pago,
                            data_venc,
                            data_orc,
                            cr_id
                        ), tags=(tag,))
                else:
                    # Aprovado mas sem parcelas geradas ainda (segurança)
                    self.tree_consulta_orc.insert("", "end", values=(
                        orc_id, cliente, servico, "—",
                        "—", f"R$ {total_geral:.2f}",
                        status, "—", "—", data_orc, "—"
                    ), tags=(status_lower,))
            else:
                # Aguardando Retorno, Declinado — 1 linha simples, sem parcelas
                self.tree_consulta_orc.insert("", "end", values=(
                    orc_id, cliente, servico, "—",
                    "—", f"R$ {total_geral:.2f}",
                    status, "—", "—", data_orc, "—"
                ), tags=(status_lower,))

        conn.close()

        # ── Atualizar KPIs ────────────────────────────────────────────────
        contadores = {"aguardando retorno": 0, "aprovado": 0, "executado": 0, "declinado": 0}
        total_fat = 0.0
        for orc in orcamentos:
            orc_id = orc[0]
            status = str(orc[5]).lower() if orc[5] else ""
            for chave in contadores:
                if chave in status:
                    contadores[chave] += 1
                    break
            if "executado" in status:
                total_fat += totais_por_orcamento.get(orc_id, 0.0)

        self._kpi_aguardando.config(text=str(contadores["aguardando retorno"]))
        self._kpi_aprovados.config( text=str(contadores["aprovado"]))
        self._kpi_executados.config(text=str(contadores["executado"]))
        self._kpi_declinados.config(text=str(contadores["declinado"]))
        self._kpi_faturado.config(  text=f"R$ {total_fat:,.2f}")
    # ==========================================
    def baixar_parcela_consulta(self):
        sel = self.tree_consulta_orc.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione uma linha de parcela para dar baixa.")
            return
        valores = self.tree_consulta_orc.item(sel[0], "values")
        cr_id = valores[10]  # coluna CR_ID
        if not cr_id or cr_id == "—":
            messagebox.showwarning("Aviso", "Esta linha não possui parcela vinculada.\nApenas orçamentos Aprovados ou Executados têm parcelas.")
            return
        conn = conectar_banco(); cursor = conn.cursor()
        cursor.execute("UPDATE contas_receber SET status_pago = 'Pago' WHERE id = ?", (cr_id,))
        conn.commit(); conn.close()
        self.carregar_todos_orcamentos_consulta()
        self.carregar_contas_receber()
        self.carregar_painel_fluxo_acumulado()

    def estornar_parcela_consulta(self):
        sel = self.tree_consulta_orc.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione uma linha de parcela para estornar.")
            return
        valores = self.tree_consulta_orc.item(sel[0], "values")
        cr_id = valores[10]
        if not cr_id or cr_id == "—":
            messagebox.showwarning("Aviso", "Esta linha não possui parcela vinculada.")
            return
        conn = conectar_banco(); cursor = conn.cursor()
        cursor.execute("UPDATE contas_receber SET status_pago = 'A Receber' WHERE id = ?", (cr_id,))
        conn.commit(); conn.close()
        self.carregar_todos_orcamentos_consulta()
        self.carregar_contas_receber()
        self.carregar_painel_fluxo_acumulado()

    # ==========================================
    # SELEÇÃO EXCLUSIVA DE PARCELA (checkbutton)
    # ==========================================
    def ao_selecionar_parcela(self, idx_selecionado):
        """Garante que apenas uma opção de parcelamento fica marcada por vez."""
        for i, flag in enumerate(self.flags_parcelas):
            if i != idx_selecionado:
                flag.set(False)
        self._atualizar_label_taxa_aplicada()

    def montar_aba_fornecedores(self):
        frame_filtros_top = ttk.LabelFrame(self.aba_fornecedores, text="Painel de Busca Rápida Integrado")
        frame_filtros_top.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(frame_filtros_top, text="🔍 Filtrar Fornecedor (Lado Esquerdo):").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.txt_busca_fornecedor_live = ttk.Entry(frame_filtros_top, width=35)
        self.txt_busca_fornecedor_live.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.txt_busca_fornecedor_live.bind("<KeyRelease>", self.carregar_fornecedores)
        
        ttk.Label(frame_filtros_top, text="🔍 Filtrar Catálogo (Lado Direito):").grid(row=0, column=2, padx=40, pady=5, sticky="w")
        self.txt_busca_catalogo_live = ttk.Entry(frame_filtros_top, width=35)
        self.txt_busca_catalogo_live.grid(row=0, column=3, padx=5, pady=5, sticky="w")
        self.txt_busca_catalogo_live.bind("<KeyRelease>", self.carregar_catalogo_pecas)

        paned = ttk.PanedWindow(self.aba_fornecedores, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)
        frame_esq = ttk.Frame(paned); frame_dir = ttk.Frame(paned)
        paned.add(frame_esq, weight=1); paned.add(frame_dir, weight=1)
        
        lbl_f = ttk.LabelFrame(frame_esq, text="Cadastro de Fornecedores")
        lbl_f.pack(fill="both", expand=True, padx=5, pady=5)
        
        ttk.Label(lbl_f, text="Empresa:").pack(anchor="w", padx=5)
        self.txt_f_empresa = ttk.Entry(lbl_f); self.txt_f_empresa.pack(fill="x", padx=5, pady=2)
        ttk.Label(lbl_f, text="Contato:").pack(anchor="w", padx=5)
        self.txt_f_pessoa = ttk.Entry(lbl_f); self.txt_f_pessoa.pack(fill="x", padx=5, pady=2)
        ttk.Label(lbl_f, text="Telefone:").pack(anchor="w", padx=5)
        self.txt_f_telefone = ttk.Entry(lbl_f); self.txt_f_telefone.pack(fill="x", padx=5, pady=2)
        ttk.Label(lbl_f, text="E-mail:").pack(anchor="w", padx=5)
        self.txt_f_email = ttk.Entry(lbl_f); self.txt_f_email.pack(fill="x", padx=5, pady=2)
        ttk.Label(lbl_f, text="Endereço:").pack(anchor="w", padx=5)
        self.txt_f_endereco = ttk.Entry(lbl_f); self.txt_f_endereco.pack(fill="x", padx=5, pady=2)
        ttk.Label(lbl_f, text="Dias Atendimento:").pack(anchor="w", padx=5)
        self.txt_f_dias = ttk.Entry(lbl_f); self.txt_f_dias.insert(0, "Segunda a Sábado"); self.txt_f_dias.pack(fill="x", padx=5, pady=2)
        ttk.Label(lbl_f, text="Horário Funcionamento:").pack(anchor="w", padx=5)
        self.txt_f_horario = ttk.Entry(lbl_f); self.txt_f_horario.insert(0, "08:00 às 18:00"); self.txt_f_horario.pack(fill="x", padx=5, pady=2)
        ttk.Label(lbl_f, text="Previsão Entrega:").pack(anchor="w", padx=5)
        self.txt_f_previsao = ttk.Entry(lbl_f); self.txt_f_previsao.insert(0, "Até 2 horas"); self.txt_f_previsao.pack(fill="x", padx=5, pady=2)
        
        frame_btns_forn = ttk.Frame(lbl_f); frame_btns_forn.pack(fill="x", pady=5)
        ttk.Button(frame_btns_forn, text="Salvar Fornecedor", command=self.salvar_fornecedor).pack(side="left", padx=5)
        ttk.Button(frame_btns_forn, text="❌ Excluir Fornecedor", command=self.excluir_fornecedor).pack(side="left", padx=5)
        
        self.tree_fornecedores = ttk.Treeview(lbl_f, columns=("ID", "Empresa", "Fone"), show="headings", height=6)
        self.tree_fornecedores.heading("ID", text="ID"); self.tree_fornecedores.heading("Empresa", text="Fornecedor"); self.tree_fornecedores.heading("Fone", text="Telefone")
        self.tree_fornecedores.pack(fill="both", expand=True, padx=5, pady=5)
        self.tree_fornecedores.bind("<<TreeviewSelect>>", self.ao_selecionar_grid_fornecedores)
        
        lbl_p = ttk.LabelFrame(frame_dir, text="Catálogo Geral de Peças Cadastradas")
        lbl_p.pack(fill="both", expand=True, padx=5, pady=5)
        ttk.Label(lbl_p, text="Código de Fábrica/ID:").pack(anchor="w", padx=5)
        self.txt_cat_codigo_fabrica = ttk.Entry(lbl_p); self.txt_cat_codigo_fabrica.pack(fill="x", padx=5, pady=2)
        ttk.Label(lbl_p, text="Nome da Peça:").pack(anchor="w", padx=5)
        self.txt_cat_nome = ttk.Entry(lbl_p); self.txt_cat_nome.pack(fill="x", padx=5, pady=2)
        ttk.Label(lbl_p, text="Preço do Catálogo:").pack(anchor="w", padx=5)
        self.txt_cat_valor = ttk.Entry(lbl_p); self.txt_cat_valor.pack(fill="x", padx=5, pady=2)
        
        frame_btns_peca = ttk.Frame(lbl_p); frame_btns_peca.pack(fill="x", pady=5)
        ttk.Button(frame_btns_peca, text="Salvar no Catálogo com Fornecedor", command=self.salvar_peca_catalogo).pack(side="left", padx=5)
        ttk.Button(frame_btns_peca, text="🗑️ Excluir Peça Selecionada", command=self.excluir_peca_catalogo).pack(side="left", padx=5)
        
        self.tree_catalogo = ttk.Treeview(lbl_p, columns=("ID", "CodFabrica", "Peça", "Valor", "Fornecedor"), show="headings")
        self.tree_catalogo.heading("ID", text="ID"); self.tree_catalogo.heading("CodFabrica", text="Cód Fábrica"); self.tree_catalogo.heading("Peça", text="Peça")
        self.tree_catalogo.heading("Valor", text="Preço"); self.tree_catalogo.heading("Fornecedor", text="Fornecedor")
        self.tree_catalogo.pack(fill="both", expand=True, padx=5, pady=5)
        self.tree_catalogo.bind("<<TreeviewSelect>>", self.ao_selecionar_grid_catalogo)

    def montar_aba_taxas_cartao(self):
        frame_top = ttk.LabelFrame(self.aba_taxas_cartao, text="Configuração de Taxas MDR por Bandeira (1X a 10X)")
        frame_top.pack(fill="x", padx=10, pady=10)

        linha = ttk.Frame(frame_top); linha.pack(fill="x", padx=5, pady=5)
        ttk.Label(linha, text="Bandeira:").pack(side="left", padx=5)
        self.cmb_taxa_bandeira = ttk.Combobox(linha, values=BANDEIRAS_CARTAO, width=16, state="readonly")
        self.cmb_taxa_bandeira.set("Visa")
        self.cmb_taxa_bandeira.pack(side="left", padx=5)
        self.cmb_taxa_bandeira.bind("<<ComboboxSelected>>", lambda e: self.carregar_taxas_config_ui())
        ttk.Button(linha, text="Carregar", command=self.carregar_taxas_config_ui).pack(side="left", padx=5)
        ttk.Button(linha, text="🌐 Buscar taxas na web", command=self.buscar_taxas_web_ui).pack(side="left", padx=5)
        ttk.Button(linha, text="💾 Salvar taxas", command=self.salvar_taxas_config_ui).pack(side="left", padx=5)
        self.lbl_status_busca_taxa = ttk.Label(linha, text="", foreground="#7F8C8D")
        self.lbl_status_busca_taxa.pack(side="left", padx=10)

        ttk.Label(
            frame_top,
            text="Valores em % (MDR). Confirme sempre com sua operadora (Cielo, Stone, PagSeguro, etc.).",
            foreground="#566573",
        ).pack(anchor="w", padx=10, pady=(0, 5))

        grid = ttk.Frame(frame_top); grid.pack(fill="x", padx=5, pady=5)
        self.entries_taxas_config = {}
        for idx in range(1, 11):
            col_idx = (idx - 1) % 5; row_idx = (idx - 1) // 5
            bloco = ttk.Frame(grid); bloco.grid(row=row_idx, column=col_idx, padx=12, pady=4, sticky="w")
            ttk.Label(bloco, text=f"{idx}X:").pack(side="left")
            ent = ttk.Entry(bloco, width=7); ent.pack(side="left", padx=3)
            ttk.Label(bloco, text="%").pack(side="left")
            self.entries_taxas_config[idx] = ent

        self.carregar_taxas_config_ui()

    def carregar_taxas_config_ui(self):
        bandeira = self.cmb_taxa_bandeira.get() or "Visa"
        taxas = obter_taxas_bandeira(bandeira)
        for n, ent in self.entries_taxas_config.items():
            ent.delete(0, "end")
            ent.insert(0, f"{taxas.get(n, 0):.2f}")

    def salvar_taxas_config_ui(self):
        bandeira = self.cmb_taxa_bandeira.get() or "Visa"
        taxas = {}
        try:
            for n, ent in self.entries_taxas_config.items():
                taxas[n] = float(ent.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Erro", "Informe taxas numéricas válidas (ex.: 3.49).")
            return
        salvar_taxas_bandeira(bandeira, taxas, fonte="manual")
        messagebox.showinfo("Sucesso", f"Taxas de {bandeira} salvas com sucesso.")
        self.lbl_status_busca_taxa.config(text=f"Salvo em {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    def buscar_taxas_web_ui(self):
        bandeira = self.cmb_taxa_bandeira.get() or "Visa"
        self.lbl_status_busca_taxa.config(text="Buscando na web...")
        def _run():
            taxas = buscar_taxas_web(bandeira)
            self.root.after(0, lambda: self._on_taxas_web_retorno(bandeira, taxas))
        threading.Thread(target=_run, daemon=True).start()

    def _on_taxas_web_retorno(self, bandeira, taxas):
        if not taxas:
            self.lbl_status_busca_taxa.config(text="Falha na busca — use taxas manuais.")
            messagebox.showwarning(
                "Busca na web",
                "Não foi possível obter taxas automaticamente.\nVerifique a conexão ou informe manualmente.",
            )
            return
        self.lbl_status_busca_taxa.config(text="Sugestões recebidas — confirme abaixo.")
        resultado = self._dialog_sugestao_taxas(bandeira, taxas)
        if resultado.get("ok"):
            for n, val in resultado["taxas"].items():
                if n in self.entries_taxas_config:
                    self.entries_taxas_config[n].delete(0, "end")
                    self.entries_taxas_config[n].insert(0, f"{val:.2f}")
            salvar_taxas_bandeira(bandeira, resultado["taxas"], fonte=f"web:{datetime.now().strftime('%Y-%m-%d')}")
            messagebox.showinfo("Sucesso", f"Taxas sugeridas aplicadas e salvas para {bandeira}.")
            self.lbl_status_busca_taxa.config(text=f"Web aplicada em {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    def _dialog_sugestao_taxas(self, bandeira, taxas_sugeridas):
        top = tk.Toplevel(self.root)
        top.title(f"Taxas sugeridas — {bandeira}")
        top.resizable(False, False)
        top.grab_set()
        top.transient(self.root)
        ttk.Label(
            top,
            text="Revise as taxas sugeridas pela busca web.\nConfirme com sua operadora antes de aplicar.",
            padding=10,
        ).pack()
        entries = {}
        grid = ttk.Frame(top); grid.pack(padx=10, pady=5)
        for idx in range(1, 11):
            col_idx = (idx - 1) % 5; row_idx = (idx - 1) // 5
            bloco = ttk.Frame(grid); bloco.grid(row=row_idx, column=col_idx, padx=8, pady=3, sticky="w")
            ttk.Label(bloco, text=f"{idx}X:").pack(side="left")
            ent = ttk.Entry(bloco, width=7); ent.pack(side="left", padx=2)
            ent.insert(0, f"{taxas_sugeridas.get(idx, 0):.2f}")
            entries[idx] = ent
        resultado = {"ok": False, "taxas": {}}

        def aplicar():
            try:
                for n, ent in entries.items():
                    resultado["taxas"][n] = float(ent.get().replace(",", "."))
            except ValueError:
                messagebox.showerror("Erro", "Taxas inválidas.", parent=top)
                return
            resultado["ok"] = True
            top.destroy()

        def cancelar():
            top.destroy()

        btns = ttk.Frame(top); btns.pack(pady=10)
        ttk.Button(btns, text="Aplicar", command=aplicar).pack(side="left", padx=5)
        ttk.Button(btns, text="Cancelar", command=cancelar).pack(side="left", padx=5)
        top.wait_window()
        return resultado

    def _ao_mudar_forma_pagamento(self, event=None):
        cartao = self.cmb_forma_pagamento.get() == "Cartão de Crédito"
        self.cmb_bandeira_cartao.config(state="readonly" if cartao else "disabled")
        self.recalcular_parcelas_dinamicas()

    def _parcela_selecionada_idx(self):
        for i in range(10):
            if self.flags_parcelas[i].get():
                return i + 1
        return 1

    def _obter_taxa_parcela(self, num_parcelas):
        if self.cmb_forma_pagamento.get() != "Cartão de Crédito":
            return 0.0
        bandeira = self.cmb_bandeira_cartao.get() or "Visa"
        taxas = obter_taxas_bandeira(bandeira)
        return taxas.get(num_parcelas, 0.0)

    def _atualizar_label_taxa_aplicada(self):
        if self.cmb_forma_pagamento.get() != "Cartão de Crédito":
            self.lbl_taxa_aplicada.config(text="Taxa: —")
            return
        n = self._parcela_selecionada_idx()
        taxa = self._obter_taxa_parcela(n)
        self.lbl_taxa_aplicada.config(text=f"Taxa {n}X: {taxa:.2f}% ({self.cmb_bandeira_cartao.get()})")

    def montar_aba_modelos_config(self):
        frame_m = ttk.LabelFrame(self.aba_modelos_config, text="Configuração de Marcas e Modelos")
        frame_m.pack(fill="both", expand=True, padx=10, pady=10)
        ttk.Label(frame_m, text="Nome da Marca:").pack(anchor="w", padx=5)
        self.txt_custom_marca = ttk.Entry(frame_m); self.txt_custom_marca.pack(fill="x", padx=5, pady=2)
        ttk.Label(frame_m, text="Modelo e Versão Motor:").pack(anchor="w", padx=5)
        self.txt_custom_modelo = ttk.Entry(frame_m); self.txt_custom_modelo.pack(fill="x", padx=5, pady=2)
        ttk.Button(frame_m, text="Adicionar Carro", command=self.salvar_modelo_custom).pack(pady=5)
        self.tree_modelos_custom = ttk.Treeview(frame_m, columns=("ID", "Marca", "ModeloMotor"), show="headings")
        self.tree_modelos_custom.heading("ID", text="ID"); self.tree_modelos_custom.heading("Marca", text="Marca"); self.tree_modelos_custom.heading("ModeloMotor", text="Modelo")
        self.tree_modelos_custom.pack(fill="both", expand=True, padx=5, pady=5)

    def montar_aba_contas_receber(self):
        frame_filtro = ttk.LabelFrame(self.aba_contas_receber, text="Relatório por Período e Filtros (ENTRADAS)")
        frame_filtro.pack(fill="x", padx=10, pady=5)
        ttk.Label(frame_filtro, text="Mês/Ano Vencimento (MM/AAAA):").grid(row=0, column=0, padx=5, pady=5)
        frame_rec_mes = ttk.Frame(frame_filtro); frame_rec_mes.grid(row=0, column=1, padx=5, pady=5)
        self.txt_rec_filtro_data = ttk.Entry(frame_rec_mes, width=10)
        self.txt_rec_filtro_data.insert(0, datetime.now().strftime("%m/%Y"))
        self.txt_rec_filtro_data.pack(side="left")
        self._btn_cal(frame_rec_mes, self.txt_rec_filtro_data, "mes").pack(side="left", padx=1)
        ttk.Button(frame_filtro, text="Pesquisar e Filtrar", command=self.carregar_contas_receber).grid(row=0, column=2, padx=10, pady=5)
        ttk.Button(frame_filtro, text="Confirmar Baixa (Recebido)", command=self.baixar_contas_receber).grid(row=0, column=3, padx=10, pady=5)
        ttk.Button(frame_filtro, text="↩️ Estornar Baixa (Voltar a Receber)", command=self.estornar_contas_receber).grid(row=0, column=4, padx=10, pady=5)
        
        self.tree_receber = ttk.Treeview(self.aba_contas_receber, columns=("ID", "OrcID", "Cliente", "Parcela", "Valor", "Vencimento", "Status"), show="headings", height=15)
        self.tree_receber.heading("ID", text="ID"); self.tree_receber.heading("OrcID", text="Nº Orç"); self.tree_receber.heading("Cliente", text="Cliente")
        self.tree_receber.heading("Parcela", text="Parcela"); self.tree_receber.heading("Valor", text="Valor"); self.tree_receber.heading("Vencimento", text="Vencimento"); self.tree_receber.heading("Status", text="Status")
        self.tree_receber.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree_receber.tag_configure("pago", background="#D4EDDA", foreground="#155724")
        self.tree_receber.tag_configure("atrasado", background="#F8D7DA", foreground="#721C24")
        
        self.frame_balanco_rec = ttk.Frame(self.aba_contas_receber); self.frame_balanco_rec.pack(fill="x", padx=10, pady=5)
        self.lbl_total_futuro_rec = ttk.Label(self.frame_balanco_rec, text="Valores a Receber Futuros: R$ 0,00", font=("Arial", 11, "bold"), foreground="blue")
        self.lbl_total_futuro_rec.pack(side="left", padx=10)

    def montar_aba_contas_pagar(self):
        frame_filtro = ttk.LabelFrame(self.aba_contas_pagar, text="Relatório de Faturas de Fornecedores (SAÍDAS)")
        frame_filtro.pack(fill="x", padx=10, pady=5)
        ttk.Label(frame_filtro, text="Fornecedor:").grid(row=0, column=0, padx=5, pady=5)
        self.txt_pag_filtro_forn = ttk.Combobox(frame_filtro, width=20); self.txt_pag_filtro_forn.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(frame_filtro, text="Mês/Ano Vencimento (MM/AAAA):").grid(row=0, column=2, padx=5, pady=5)
        frame_pag_mes = ttk.Frame(frame_filtro); frame_pag_mes.grid(row=0, column=3, padx=5, pady=5)
        self.txt_pag_filtro_data = ttk.Entry(frame_pag_mes, width=10)
        self.txt_pag_filtro_data.insert(0, datetime.now().strftime("%m/%Y"))
        self.txt_pag_filtro_data.pack(side="left")
        self._btn_cal(frame_pag_mes, self.txt_pag_filtro_data, "mes").pack(side="left", padx=1)
        ttk.Button(frame_filtro, text="Pesquisar Custos", command=self.carregar_contas_pagar).grid(row=0, column=4, padx=10, pady=5)
        ttk.Button(frame_filtro, text="Dar Baixa (Pago ao Fornecedor)", command=self.baixar_contas_pagar).grid(row=0, column=5, padx=10, pady=5)
        
        self.tree_pagar = ttk.Treeview(self.aba_contas_pagar, columns=("ID", "OrcID", "Fornecedor", "Parcela", "Peca", "Valor", "Vencimento", "Status"), show="headings", height=15)
        self.tree_pagar.heading("ID", text="ID"); self.tree_pagar.heading("OrcID", text="Nº Orç"); self.tree_pagar.heading("Fornecedor", text="Fornecedor")
        self.tree_pagar.heading("Parcela", text="Parcela"); self.tree_pagar.heading("Peca", text="Item/Peça"); self.tree_pagar.heading("Valor", text="Custo")
        self.tree_pagar.heading("Vencimento", text="Vencimento"); self.tree_pagar.heading("Status", text="Status")
        self.tree_pagar.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree_pagar.tag_configure("pago", background="#D4EDDA", foreground="#155724")
        
        self.frame_balanco_pag = ttk.Frame(self.aba_contas_pagar); self.frame_balanco_pag.pack(fill="x", padx=10, pady=5)
        self.lbl_total_comprometido_pag = ttk.Label(self.frame_balanco_pag, text="Total Comprometido: R$ 0,00", font=("Arial", 11, "bold"), foreground="red")
        self.lbl_total_comprometido_pag.pack(side="left", padx=10)

    def montar_aba_fluxo_acumulado(self):
        frame_top_acumulado = ttk.LabelFrame(self.aba_fluxo_acumulado, text="Seleção de Período Mensal")
        frame_top_acumulado.pack(fill="x", padx=10, pady=5)
        ttk.Label(frame_top_acumulado, text="Escolha o Mês/Ano Competência:").pack(side="left", padx=10, pady=5)
        self.txt_fluxo_mes_ano = ttk.Combobox(frame_top_acumulado, width=12)
        ano_c = datetime.now().year
        meses_lista = []
        for a in [ano_c, ano_c - 1]:
            for m in range(12, 0, -1):
                meses_lista.append(f"{m:02d}/{a}")
        self.txt_fluxo_mes_ano['values'] = meses_lista
        self.txt_fluxo_mes_ano.set(datetime.now().strftime("%m/%Y"))
        self.txt_fluxo_mes_ano.pack(side="left", padx=2, pady=5)
        self._btn_cal(frame_top_acumulado, self.txt_fluxo_mes_ano, "mes").pack(side="left", padx=1, pady=5)
        ttk.Button(frame_top_acumulado, text="📊 Atualizar Painel", command=self.carregar_painel_fluxo_acumulado).pack(side="left", padx=15, pady=5)

        paned_fluxo = ttk.PanedWindow(self.aba_fluxo_acumulado, orient="horizontal")
        paned_fluxo.pack(fill="both", expand=True, padx=10, pady=5)
        frame_esq_pagar = ttk.Frame(paned_fluxo); frame_dir_receber = ttk.Frame(paned_fluxo)
        paned_fluxo.add(frame_esq_pagar, weight=1); paned_fluxo.add(frame_dir_receber, weight=1)
        
        lbl_f_pagar = ttk.LabelFrame(frame_esq_pagar, text="🔴 CONTAS A PAGAR (Saídas Operacionais Acumuladas)")
        lbl_f_pagar.pack(fill="both", expand=True, padx=5, pady=2)
        self.tree_acumulado_pagar = ttk.Treeview(lbl_f_pagar, columns=("Descricao", "Valor"), show="tree headings")
        self.tree_acumulado_pagar.heading("#0", text="Dia / Detalhes")
        self.tree_acumulado_pagar.heading("Descricao", text="Fornecedor / Item")
        self.tree_acumulado_pagar.heading("Valor", text="Custo Real")
        self.tree_acumulado_pagar.pack(fill="both", expand=True, padx=5, pady=5)
        self.lbl_somatoria_pagar_acum = ttk.Label(lbl_f_pagar, text="TOTAL GERAL A PAGAR NO MÊS: R$ 0,00", font=("Arial", 10, "bold"), foreground="red")
        self.lbl_somatoria_pagar_acum.pack(anchor="w", padx=10, pady=5)
        
        lbl_f_receber = ttk.LabelFrame(frame_dir_receber, text="🔵 CONTAS A RECEBER (Entradas Comerciais Acumuladas)")
        lbl_f_receber.pack(fill="both", expand=True, padx=5, pady=2)
        self.tree_acumulado_receber = ttk.Treeview(lbl_f_receber, columns=("Descricao", "Valor"), show="tree headings")
        self.tree_acumulado_receber.heading("#0", text="Dia / Detalhes")
        self.tree_acumulado_receber.heading("Descricao", text="Cliente / Parcela")
        self.tree_acumulado_receber.heading("Valor", text="Preço Faturado")
        self.tree_acumulado_receber.pack(fill="both", expand=True, padx=5, pady=5)
        self.lbl_somatoria_receber_acum = ttk.Label(lbl_f_receber, text="TOTAL GERAL A RECEBER NO MÊS: R$ 0,00", font=("Arial", 10, "bold"), foreground="blue")
        self.lbl_somatoria_receber_acum.pack(anchor="w", padx=10, pady=5)

    def montar_aba_manual(self):
        # ── Cabeçalho da aba ──────────────────────────────────────────────
        frame_cabecalho = tk.Frame(self.aba_manual, bg="#2C3E50", height=48)
        frame_cabecalho.pack(fill="x", padx=0, pady=0)
        frame_cabecalho.pack_propagate(False)
        tk.Label(frame_cabecalho,
                 text="📖  MULTI ESCAPE — Central de Apoio & Manual do Usuário  v1.2",
                 font=("Arial", 13, "bold"), bg="#2C3E50", fg="white").pack(side="left", padx=15, pady=10)

        # ── Barra de busca rápida ─────────────────────────────────────────
        frame_busca_man = tk.Frame(self.aba_manual, bg="#ECF0F1")
        frame_busca_man.pack(fill="x", padx=0, pady=0)
        tk.Label(frame_busca_man, text="🔍  Buscar no manual:", font=("Arial", 9),
                 bg="#ECF0F1", fg="#555").pack(side="left", padx=10, pady=5)
        self.txt_busca_manual = ttk.Entry(frame_busca_man, width=35)
        self.txt_busca_manual.pack(side="left", padx=5, pady=5)
        ttk.Button(frame_busca_man, text="Buscar",
                   command=self._manual_buscar).pack(side="left", padx=4)
        ttk.Button(frame_busca_man, text="Limpar",
                   command=self._manual_limpar_busca).pack(side="left", padx=2)
        self.lbl_busca_resultado = tk.Label(frame_busca_man, text="", font=("Arial", 9),
                                            bg="#ECF0F1", fg="#888")
        self.lbl_busca_resultado.pack(side="left", padx=10)

        # ── Layout principal: nav esquerda + conteúdo direita ─────────────
        paned_manual = ttk.PanedWindow(self.aba_manual, orient="horizontal")
        paned_manual.pack(fill="both", expand=True, padx=0, pady=0)

        # --- Painel de navegação (esquerda) --------------------------------
        frame_nav = tk.Frame(paned_manual, bg="#2C3E50", width=210)
        paned_manual.add(frame_nav, weight=0)

        tk.Label(frame_nav, text="ÍNDICE DE MÓDULOS", font=("Arial", 9, "bold"),
                 bg="#1A252F", fg="#BDC3C7", pady=8).pack(fill="x")

        self._secoes_manual = {
            "🏠  Início & Visão Geral":       "inicio",
            "👥  Clientes & Veículos":         "clientes",
            "📝  Novo Orçamento":              "orcamento",
            "🔍  Consultar Orçamentos":        "consulta",
            "🚚  Fornecedores & Peças":        "fornecedores",
            "⚙️  Marcas & Motores":            "modelos",
            "💰  Contas a Receber":            "receber",
            "💸  Contas a Pagar":              "pagar",
            "📊  Fluxo Acumulado":             "fluxo",
            "🔄  Fluxo do Sistema (Passo a Passo)": "fluxo_completo",
            "⚠️  Dicas & Erros Comuns":        "dicas",
        }

        self._botoes_nav = {}
        for label, chave in self._secoes_manual.items():
            btn = tk.Button(frame_nav, text=label, font=("Arial", 9), anchor="w",
                            bg="#2C3E50", fg="#ECF0F1", relief="flat",
                            activebackground="#3D5166", activeforeground="white",
                            bd=0, padx=12, pady=6,
                            command=lambda c=chave: self._manual_ir_para(c))
            btn.pack(fill="x")
            self._botoes_nav[chave] = btn

        tk.Frame(frame_nav, bg="#1A252F", height=1).pack(fill="x", pady=8)
        tk.Label(frame_nav, text="Clique em um módulo\npara navegar direto", 
                 font=("Arial", 8, "italic"), bg="#2C3E50", fg="#7F8C8D",
                 justify="center").pack(padx=10, pady=5)

        # --- Painel de conteúdo (direita) ----------------------------------
        frame_conteudo = tk.Frame(paned_manual, bg="#FAFAFA")
        paned_manual.add(frame_conteudo, weight=1)

        scroll_y_man = ttk.Scrollbar(frame_conteudo, orient="vertical")
        scroll_y_man.pack(side="right", fill="y")
        scroll_x_man = ttk.Scrollbar(frame_conteudo, orient="horizontal")
        scroll_x_man.pack(side="bottom", fill="x")

        self.txt_manual_area = tk.Text(
            frame_conteudo, wrap="word",
            yscrollcommand=scroll_y_man.set,
            xscrollcommand=scroll_x_man.set,
            font=("Consolas", 10), bg="#FAFAFA", fg="#2C3E50",
            padx=20, pady=15, cursor="arrow", spacing1=2, spacing3=4
        )
        self.txt_manual_area.pack(fill="both", expand=True)
        scroll_y_man.config(command=self.txt_manual_area.yview)
        scroll_x_man.config(command=self.txt_manual_area.xview)

        # ── Definição de tags visuais ─────────────────────────────────────
        self.txt_manual_area.tag_config("banner",     font=("Consolas", 11, "bold"), foreground="white",      background="#2C3E50",  spacing1=6, spacing3=6)
        self.txt_manual_area.tag_config("h1",         font=("Arial",   14, "bold"), foreground="#2C3E50",     spacing1=14, spacing3=4)
        self.txt_manual_area.tag_config("h2",         font=("Arial",   11, "bold"), foreground="#FFFFFF",     background="#2980B9",  spacing1=8, spacing3=4)
        self.txt_manual_area.tag_config("h3",         font=("Arial",   10, "bold"), foreground="#2471A3",     spacing1=8, spacing3=2)
        self.txt_manual_area.tag_config("corpo",      font=("Consolas", 10),        foreground="#2C3E50")
        self.txt_manual_area.tag_config("passo",      font=("Consolas", 10, "bold"),foreground="#1A5276")
        self.txt_manual_area.tag_config("dica",       font=("Consolas",  9),        foreground="#1E8449",     background="#EAFAF1",  spacing1=3, spacing3=3)
        self.txt_manual_area.tag_config("aviso",      font=("Consolas",  9, "bold"),foreground="#784212",     background="#FDEBD0",  spacing1=3, spacing3=3)
        self.txt_manual_area.tag_config("erro",       font=("Consolas",  9, "bold"),foreground="#922B21",     background="#FADBD8",  spacing1=3, spacing3=3)
        self.txt_manual_area.tag_config("tela",       font=("Consolas",  9),        foreground="#1B2631",     background="#D5D8DC",  spacing1=4, spacing3=4)
        self.txt_manual_area.tag_config("separador",  font=("Consolas",  8),        foreground="#ABB2B9")
        self.txt_manual_area.tag_config("destaque",   font=("Consolas", 10, "bold"),foreground="#6C3483")
        self.txt_manual_area.tag_config("ancora",     font=("Consolas",  1),        foreground="#FAFAFA")    # marcadores invisíveis de âncora

        self._manual_popular_conteudo()
        self.txt_manual_area.config(state="disabled")

    # ── Conteúdo completo do manual ───────────────────────────────────────
    def _manual_popular_conteudo(self):
        T = self.txt_manual_area
        def w(texto, tag="corpo"): T.insert("end", texto, tag)
        def nl(n=1): T.insert("end", "\n" * n)
        def sep(): w("  " + "─" * 72 + "\n", "separador")
        def ancora(chave): T.insert("end", f"\u200b", ("ancora", f"ancora_{chave}"))  # zero-width space como marcador
        def h1(txt): nl(); w(f"  {txt}\n", "h1")
        def h2(txt): nl(); w(f"  {txt}  \n", "h2")
        def h3(txt): nl(); w(f"  {txt}\n", "h3")
        def passo(n, txt): w(f"  [{n}] {txt}\n", "passo")
        def item(txt): w(f"   •  {txt}\n", "corpo")
        def dica(txt): w(f"   💡 DICA: {txt}\n", "dica")
        def aviso(txt): w(f"   ⚠️  ATENÇÃO: {txt}\n", "aviso")
        def erro(txt): w(f"   ❌ CUIDADO: {txt}\n", "erro")
        def tela(linhas): w("\n", "corpo"); [w(f"    {l}\n", "tela") for l in linhas]; w("\n", "corpo")

        # ═══════════════════════════════════════════════════════════════════
        # BANNER
        # ═══════════════════════════════════════════════════════════════════
        ancora("inicio")
        w("\n", "corpo")
        w("  ╔══════════════════════════════════════════════════════════════════╗\n", "banner")
        w("  ║       MULTI ESCAPE — SISTEMA DE GESTÃO ERP v1.2                ║\n", "banner")
        w("  ║       Central de Apoio & Manual Operacional Completo            ║\n", "banner")
        w("  ╚══════════════════════════════════════════════════════════════════╝\n", "banner")

        # ── Visão geral ────────────────────────────────────────────────────
        h1("🏠  VISÃO GERAL DO SISTEMA")
        sep()
        w("  O Multi Escape ERP organiza todo o fluxo de uma oficina automotiva:\n  desde o cadastro do cliente até o controle financeiro completo.\n", "corpo")
        nl()
        w("  O sistema é dividido em 9 abas (módulos), acessíveis pelo topo da janela:\n", "corpo")
        nl()
        tela([
            "┌─────────────────────────────────────────────────────────────────┐",
            "│ 👥Clientes │ 📝Orçamento │ 🔍Consulta │ 🚚Fornec. │ ⚙️Modelos │",
            "│            💰Receber    │  💸Pagar   │ 📊Fluxo   │ 📖Manual  │",
            "└─────────────────────────────────────────────────────────────────┘",
        ])
        w("  FLUXO RESUMIDO DO SISTEMA:\n", "h3")
        w("  Cadastrar Cliente → Criar Orçamento → Aprovar → Executar\n", "corpo")
        w("       ↓                                    ↓           ↓\n", "destaque")
        w("  (Veículo e dados)              (Contas a Receber) (Contas a Pagar)\n", "corpo")
        nl()
        dica("Sempre cadastre o cliente antes de criar um orçamento.")

        # ═══════════════════════════════════════════════════════════════════
        # CLIENTES
        # ═══════════════════════════════════════════════════════════════════
        ancora("clientes")
        h2("  👥  MÓDULO 1 — CLIENTES & VEÍCULOS (CRM)")
        sep()
        w("  Este módulo concentra o cadastro de clientes, seus veículos e\n  o histórico de serviços realizados.\n", "corpo")
        nl()
        h3("  LAYOUT DA TELA")
        tela([
            "┌── Dados do Cliente e Motorização ──────────────────────────────┐",
            "│ Nome do Cliente*  [___________]  Placa* [_______]             │",
            "│ Marca             [___________]  Modelo [_______]  Ano [____] │",
            "│ Contato           [___________]  Email  [_______]  Cor [____] │",
            "├── Painel CRM ───────────────────────────────────────────────────┤",
            "│ Orçamentos Efetuados: 0  │ Executados: 0  │ Último serviço...  │",
            "├── Botões ───────────────────────────────────────────────────────┤",
            "│ [Salvar]  [Modificar]  [Excluir]  [Limpar]                     │",
            "├── Grade de Clientes Cadastrados ────────────────────────────────┤",
            "│ ID │ Nome │ Placa │ Marca │ Modelo/Motor │ Ano                 │",
            "└────────────────────────────────────────────────────────────────┘",
        ])
        h3("  COMO CADASTRAR UM NOVO CLIENTE")
        passo(1, "Preencha os campos: Nome, Placa (obrigatórios), Marca, Modelo, Ano.")
        passo(2, "Selecione a Marca para filtrar os modelos disponíveis automaticamente.")
        passo(3, "Clique em  [Salvar Cliente].")
        passo(4, "O ID do cliente aparece na grade e é preenchido automaticamente ao criar orçamentos.")
        nl()
        h3("  COMO BUSCAR UM CLIENTE EXISTENTE")
        passo(1, "Clique no campo 'Nome do Cliente' — aparece lista de todos cadastrados.")
        passo(2, "Selecione o nome ou a placa. Os dados preenchem automaticamente.")
        passo(3, "O painel CRM mostra na mesma hora: quantos orçamentos foram feitos,\n      quantos executados e qual foi o último serviço.")
        nl()
        h3("  COMO EDITAR OU EXCLUIR")
        item("Clique na linha do cliente na grade — os campos são preenchidos.")
        item("Altere o que precisar e clique em [Modificar Dados].")
        item("Para excluir: selecione na grade e clique em [Excluir Registro].")
        nl()
        aviso("Excluir um cliente apaga TODOS os orçamentos, parcelas e contas vinculadas a ele.")
        dica("O campo Placa é único — dois clientes não podem ter a mesma placa.")

        # ═══════════════════════════════════════════════════════════════════
        # ORÇAMENTO
        # ═══════════════════════════════════════════════════════════════════
        ancora("orcamento")
        h2("  📝  MÓDULO 2 — NOVO ORÇAMENTO")
        sep()
        w("  Aqui você monta a proposta comercial: define peças, mão de obra,\n  prazo de entrega e condição de pagamento.\n", "corpo")
        nl()
        h3("  LAYOUT DA TELA")
        tela([
            "┌── Dados Gerais ──────────────────────────────────────────────────┐",
            "│ ID Cliente* [__]  Serviço [________________]  Data [__/__/____] │",
            "│ Status Inicial [ Aguardando Retorno ▼ ]                         │",
            "├── Adicionar Peças ───────────────────────────────────────────────┤",
            "│ Cód [___] Descrição [__________] Qtd [_] Preço Venda [________] │",
            "│ Fornecedor [_______] Custo Compra [______] Prazo Pgto [______]  │",
            "│                                   [+ Inserir Peça] [Excluir]    │",
            "├── Carrinho ─────────────────────────────────────────────────────┤",
            "│ Cód │ Descrição │ Qtd │ Venda │ Total │ Fornec. │ Custo        │",
            "├── Fechamento ────────────────────────────────────────────────────┤",
            "│ Mão de Obra [_____]  Pagamento Info [_________________]         │",
            "│ Previsão Entrega [___________]  Observação [_______________]    │",
            "├── Parcelamento ──────────────────────────────────────────────────┤",
            "│ ☐1X R$0,00  ☐2X R$0,00  ☐3X R$0,00  ☐4X  ☐5X  ☐6X...        │",
            "├── Pesquisa Rápida de Peças ──────────────────────────────────────┤",
            "│ [buscar...] → ID │ Descrição │ Preço │ Fornecedor (duplo clique)│",
            "└─────────────────────────────────────────────────────────────────┘",
        ])
        h3("  PASSO A PASSO PARA CRIAR UM ORÇAMENTO")
        passo(1, "Informe o  ID Cliente  (aparece automaticamente ao selecionar pela aba Clientes).")
        passo(2, "Preencha o campo  'Serviço Solicitado'  (ex: Troca de correia dentada).")
        passo(3, "Para cada peça: informe Código, Descrição, Qtd e Preço de Venda.")
        passo(4, "Informe o Fornecedor, Custo de Compra e o Prazo de Pagamento ao fornecedor.")
        passo(5, "Clique em  [+ Inserir Peça]  — a peça vai para o carrinho.")
        passo(6, "Informe o valor da  Mão de Obra.")
        passo(7, "Selecione a condição de parcelamento (apenas UMA opção, de 1X a 10X).")
        passo(8, "Defina o Status Inicial e clique em  [SALVAR PROPOSTA DE ORÇAMENTO].")
        nl()
        h3("  BUSCA RÁPIDA DE PEÇAS (CATÁLOGO)")
        item("Digite parte do nome na barra de pesquisa — a lista filtra em tempo real.")
        item("Dê duplo clique em uma peça para puxar código, descrição e preço automaticamente.")
        item("Também funciona digitando o Código da Peça no campo Cód + pressionar Enter.")
        nl()
        h3("  STATUS INICIAL DO ORÇAMENTO")
        tela([
            "  Aguardando Retorno → cliente ainda não confirmou",
            "  Aprovado           → cliente aprovou, gera parcelas a receber E a pagar",
            "  Declinado          → proposta recusada pelo cliente",
        ])
        dica("Salvar como 'Aprovado' já gera automaticamente as parcelas no Contas a Receber e as obrigações no Contas a Pagar.")
        aviso("O campo ID Cliente é obrigatório. Sem ele o sistema não salva o orçamento.")

        # ═══════════════════════════════════════════════════════════════════
        # CONSULTA
        # ═══════════════════════════════════════════════════════════════════
        ancora("consulta")
        h2("  🔍  MÓDULO 3 — CONSULTAR ORÇAMENTOS")
        sep()
        w("  Central de controle de todos os orçamentos. Aqui você aprova,\n  executa, dá baixa em parcelas e acompanha o status de cada proposta.\n", "corpo")
        nl()
        h3("  LAYOUT DA TELA")
        tela([
            "┌── Filtros ───────────────────────────────────────────────────────┐",
            "│ Data Início [__/__/____]  Data Fim [__/__/____]  [🔍 Pesquisar] │",
            "├── Ações do Orçamento ────────────────────────────────────────────┤",
            "│ [👍 Cliente Aprovou]  [🔧 Executado]  [❌ Excluir]  [↩️ Estornar]│",
            "├── Ações na Parcela Selecionada ──────────────────────────────────┤",
            "│ [✅ Dar Baixa na Parcela]              [↩️ Estornar Baixa]       │",
            "├── Grid ─────────────────────────────────────────────────────────┤",
            "│ NºOrç │ Cliente │ Serviço │ Parcela │ Vl.Parc │ Total │ Status │",
            "│  ...  │  ...    │  ...    │   1/3   │R$250,00 │ ...   │Aprovado│",
            "│  ...  │  ...    │  ...    │   2/3   │R$250,00 │ ...   │A Receber│",
            "│  ...  │  ...    │  ...    │   3/3   │R$250,00 │ ...   │A Receber│",
            "└─────────────────────────────────────────────────────────────────┘",
        ])
        h3("  ENTENDENDO AS LINHAS DE PARCELAS")
        item("Orçamento Aguardando/Declinado → aparece como 1 única linha.")
        item("Orçamento Aprovado/Executado → aparece N linhas, uma por parcela.")
        item("  Ex: parcelado em 3x → linhas 1/3, 2/3 e 3/3, cada uma com seu vencimento.")
        nl()
        h3("  DAR BAIXA EM UMA PARCELA")
        passo(1, "Clique na linha da parcela que foi paga (ex: linha '2/3').")
        passo(2, "Clique em  [✅ Dar Baixa na Parcela].")
        passo(3, "A linha fica verde e o status muda para 'Pago'.")
        passo(4, "O Contas a Receber e o Fluxo Acumulado são atualizados automaticamente.")
        nl()
        h3("  MUDANÇA DE STATUS DO ORÇAMENTO INTEIRO")
        tela([
            "  [👍 Cliente Aprovou]  → muda para 'Aprovado'",
            "                          gera parcelas no Contas a Receber",
            "                          gera obrigações no Contas a Pagar",
            "",
            "  [🔧 Orc Realizado]   → muda para 'Executado'",
            "                          confirma os lançamentos financeiros",
            "",
            "  [↩️ Estornar]        → volta para 'Aguardando Retorno'",
            "                          APAGA todas as parcelas vinculadas",
        ])
        h3("  CORES DO GRID")
        item("🔵 Azul claro   = Aprovado (aguardando pagamento)")
        item("🟢 Verde claro  = Executado / Parcela Paga")
        item("🔴 Rosa/Vermelho = Declinado / Parcela Atrasada")
        nl()
        aviso("Estornar apaga TODAS as parcelas do orçamento. Ação irreversível.")
        dica("Filtre por período para encontrar orçamentos de datas específicas.")

        # ═══════════════════════════════════════════════════════════════════
        # FORNECEDORES
        # ═══════════════════════════════════════════════════════════════════
        ancora("fornecedores")
        h2("  🚚  MÓDULO 4 — FORNECEDORES & CATÁLOGO DE PEÇAS")
        sep()
        w("  Gerencie seus fornecedores e mantenha um catálogo de peças\n  com preço e vínculo com o fornecedor correto.\n", "corpo")
        nl()
        h3("  LAYOUT DA TELA (DOIS PAINÉIS)")
        tela([
            "┌── Esquerda: Fornecedores ──────┬── Direita: Catálogo de Peças ──┐",
            "│ Empresa    [______________]    │ Cód Fábrica [_______________]  │",
            "│ Contato    [______________]    │ Nome da Peça [______________]  │",
            "│ Telefone   [______________]    │ Preço        [______________]  │",
            "│ E-mail     [______________]    │                                │",
            "│ Endereço   [______________]    │ [Salvar com Fornecedor]        │",
            "│ Dias Aterm.[______________]    │ [🗑️ Excluir Peça]              │",
            "│ Horário    [______________]    │                                │",
            "│ Prev.Entrega[_____________]    │ ┌──────────────────────────┐   │",
            "│ [Salvar] [❌Excluir]           │ │ Grade do Catálogo        │   │",
            "│ ┌────────────────────────┐    │ └──────────────────────────┘   │",
            "│ │ Grade de Fornecedores  │    │                                │",
            "│ └────────────────────────┘    │                                │",
            "└───────────────────────────────┴────────────────────────────────┘",
        ])
        h3("  CADASTRAR FORNECEDOR")
        passo(1, "Preencha os dados do fornecedor (Empresa é obrigatório).")
        passo(2, "Clique em  [Salvar Fornecedor].")
        passo(3, "O fornecedor aparece na grade e fica disponível no Orçamento.")
        nl()
        h3("  CADASTRAR PEÇA NO CATÁLOGO")
        passo(1, "Selecione o fornecedor clicando nele na grade da esquerda.")
        passo(2, "Preencha Código de Fábrica, Nome da Peça e Preço.")
        passo(3, "Clique em  [Salvar no Catálogo com Fornecedor].")
        nl()
        dica("Com fornecedor selecionado, ao cadastrar peças elas já ficam vinculadas a ele. Isso faz com que o Contas a Pagar seja preenchido corretamente ao aprovar um orçamento.")
        aviso("Excluir um fornecedor remove TODAS as peças vinculadas a ele do catálogo.")

        # ═══════════════════════════════════════════════════════════════════
        # MODELOS
        # ═══════════════════════════════════════════════════════════════════
        ancora("modelos")
        h2("  ⚙️  MÓDULO 5 — MARCAS & MOTORES")
        sep()
        w("  Configure as marcas e versões de motores que aparecem\n  no cadastro de clientes e veículos.\n", "corpo")
        nl()
        passo(1, "Informe o Nome da Marca (ex: Honda).")
        passo(2, "Informe o Modelo e Versão do Motor (ex: Civic 2.0 i-VTEC).")
        passo(3, "Clique em  [Adicionar Carro].")
        nl()
        dica("O sistema já vem pré-carregado com modelos populares. Adicione apenas os que usa com frequência.")

        # ═══════════════════════════════════════════════════════════════════
        # RECEBER
        # ═══════════════════════════════════════════════════════════════════
        ancora("receber")
        h2("  💰  MÓDULO 6 — CONTAS A RECEBER")
        sep()
        w("  Lista todas as parcelas de recebimento geradas pelos orçamentos\n  aprovados ou executados.\n", "corpo")
        nl()
        h3("  LAYOUT DA TELA")
        tela([
            "┌── Filtros ───────────────────────────────────────────────────────┐",
            "│ Mês/Ano [__/____]  [Pesquisar]  [Confirmar Baixa]  [↩️Estornar] │",
            "├── Grade ────────────────────────────────────────────────────────┤",
            "│ ID │ Nº Orç │ Cliente │ Parcela │ Valor │ Vencimento │ Status   │",
            "│    │        │         │   1/3   │R$250  │ 07/06/2026 │A Receber │",
            "│    │        │         │   2/3   │R$250  │ 07/07/2026 │A Receber │",
            "├── Totalizador ──────────────────────────────────────────────────┤",
            "│  💙 Valores a Receber Futuros: R$ 0,00                          │",
            "└─────────────────────────────────────────────────────────────────┘",
        ])
        h3("  COMO DAR BAIXA (RECEBIMENTO)")
        passo(1, "Filtre pelo Mês/Ano desejado e clique em  [Pesquisar e Filtrar].")
        passo(2, "Clique na linha da parcela recebida.")
        passo(3, "Clique em  [Confirmar Baixa (Recebido)].")
        nl()
        item("🟢 Linha verde = parcela paga.")
        item("🔴 Linha vermelha = parcela em atraso (vencimento já passou).")
        dica("O totalizador mostra apenas os valores que ainda vão entrar (não vencidos).")

        # ═══════════════════════════════════════════════════════════════════
        # PAGAR
        # ═══════════════════════════════════════════════════════════════════
        ancora("pagar")
        h2("  💸  MÓDULO 7 — CONTAS A PAGAR")
        sep()
        w("  Lista os custos de compra de peças por fornecedor, gerados\n  automaticamente ao  APROVAR  um orçamento que contém peças\n  com fornecedor e prazo de pagamento informados.\n", "corpo")
        nl()
        h3("  LAYOUT DA TELA")
        tela([
            "┌── Filtros ───────────────────────────────────────────────────────┐",
            "│ Fornecedor [_________▼] Mês/Ano [__/____] [Pesquisar] [Baixa]  │",
            "├── Grade ────────────────────────────────────────────────────────┤",
            "│ ID │ Nº Orç │ Fornecedor │ Parcela │ Item/Peça │ Custo │ Status │",
            "├── Totalizador ──────────────────────────────────────────────────┤",
            "│  🔴 Total Comprometido: R$ 0,00                                 │",
            "└─────────────────────────────────────────────────────────────────┘",
        ])
        h3("  COMO O CONTAS A PAGAR É GERADO")
        tela([
            "  Orçamento APROVADO com peças vinculadas a fornecedores",
            "        ↓",
            "  Sistema consolida os custos por Fornecedor + Prazo",
            "        ↓",
            "  Prazo 'À Vista'  → 1 lançamento com vencimento hoje",
            "  Prazo '30 Dias'  → 1 lançamento com vencimento em 30 dias",
            "  Prazo '60 Dias'  → 2 lançamentos: 30 e 60 dias (valor dividido em 2)",
        ])
        aviso("Para que o Contas a Pagar seja preenchido, cada peça DEVE ter um fornecedor vinculado no orçamento. Peças sem fornecedor são ignoradas.")
        dica("Use o filtro de Fornecedor para ver apenas os lançamentos de um fornecedor específico.")

        # ═══════════════════════════════════════════════════════════════════
        # FLUXO
        # ═══════════════════════════════════════════════════════════════════
        ancora("fluxo")
        h2("  📊  MÓDULO 8 — FLUXO ACUMULADO")
        sep()
        w("  Visão consolidada mensal em árvore expansível, mostrando\n  dia a dia todas as entradas e saídas financeiras.\n", "corpo")
        nl()
        h3("  LAYOUT DA TELA")
        tela([
            "┌── Seleção de Período ────────────────────────────────────────────┐",
            "│ Mês/Ano [06/2026 ▼]   [📊 Atualizar Painel]                    │",
            "├── Saídas (Contas a Pagar) ────┬── Entradas (Contas a Receber) ──┤",
            "│ ▶ Dia 07/06/2026 R$300,00     │ ▶ Dia 07/06/2026  R$500,00     │",
            "│   ↳ AutoPeças (1/1)  R$300,00 │   ↳ João Silva (1/3) R$250,00  │",
            "│ ▶ Dia 08/06/2026 R$0,00       │   ↳ Maria (2/2)      R$250,00  │",
            "│ ...                           │ ▶ Dia 08/06/2026  R$0,00       │",
            "├───────────────────────────────┼────────────────────────────────┤",
            "│ TOTAL A PAGAR: R$ 300,00      │ TOTAL A RECEBER: R$ 500,00     │",
            "└─────────────────────────────────────────────────────────────────┘",
        ])
        passo(1, "Selecione o Mês/Ano no seletor.")
        passo(2, "Clique em  [📊 Atualizar Painel].")
        passo(3, "Clique na seta (▶) de um dia para expandir e ver os lançamentos.")
        nl()
        dica("Dias sem movimento mostram R$ 0,00 mas ficam na lista para referência. Apenas dias com lançamentos têm itens filhos.")

        # ═══════════════════════════════════════════════════════════════════
        # FLUXO COMPLETO
        # ═══════════════════════════════════════════════════════════════════
        ancora("fluxo_completo")
        h2("  🔄  FLUXO COMPLETO DO SISTEMA (PASSO A PASSO)")
        sep()
        w("  Este é o caminho ideal para um atendimento completo na oficina:\n", "corpo")
        nl()
        tela([
            "  ┌─────────────────────────────────────────────────────────┐",
            "  │              FLUXO OPERACIONAL COMPLETO                 │",
            "  ├─────────────────────────────────────────────────────────┤",
            "  │                                                         │",
            "  │  1. Aba CLIENTES → cadastrar ou localizar o cliente     │",
            "  │                ↓                                        │",
            "  │  2. Aba NOVO ORÇAMENTO → montar proposta com peças,     │",
            "  │     M.O., parcelamento e prazo de pgto ao fornecedor   │",
            "  │                ↓                                        │",
            "  │  3. Salvar como 'Aguardando Retorno'                    │",
            "  │     → aguarda confirmação do cliente                    │",
            "  │                ↓                                        │",
            "  │  4. Aba CONSULTAR → localizar o orçamento               │",
            "  │     → clicar [👍 Cliente Aprovou]                       │",
            "  │     → sistema gera parcelas em Contas a Receber         │",
            "  │     → sistema gera lançamentos em Contas a Pagar        │",
            "  │                ↓                                        │",
            "  │  5. Serviço realizado → clicar [🔧 Orc Executado]       │",
            "  │                ↓                                        │",
            "  │  6. Aba CONTAS A RECEBER → dar baixa parcela a parcela  │",
            "  │     à medida que o cliente paga                         │",
            "  │                ↓                                        │",
            "  │  7. Aba CONTAS A PAGAR → dar baixa ao pagar fornecedor  │",
            "  │                ↓                                        │",
            "  │  8. Aba FLUXO ACUMULADO → visão consolidada do mês      │",
            "  │                                                         │",
            "  └─────────────────────────────────────────────────────────┘",
        ])

        # ═══════════════════════════════════════════════════════════════════
        # DICAS E ERROS COMUNS
        # ═══════════════════════════════════════════════════════════════════
        ancora("dicas")
        h2("  ⚠️  DICAS GERAIS & ERROS COMUNS")
        sep()
        nl()
        h3("  ✅ BOAS PRÁTICAS")
        dica("Sempre vincule um fornecedor às peças no orçamento para que o Contas a Pagar seja gerado corretamente.")
        dica("Selecione apenas UMA opção de parcelamento no Novo Orçamento. Marcando mais de uma, o sistema usa a menor selecionada.")
        dica("Use a Pesquisa Rápida de Peças para agilizar o preenchimento — duplo clique preenche tudo automaticamente.")
        dica("Filtre o Contas a Receber e o Fluxo Acumulado pelo mês atual para ter visão imediata do caixa.")
        nl()
        h3("  ❌ ERROS COMUNS E COMO RESOLVER")
        erro("Contas a Pagar não aparece → verifique se as peças têm fornecedor vinculado E se o orçamento foi aprovado.")
        erro("Parcelas não aparecem na Consulta → verifique se o status do orçamento é 'Aprovado' ou 'Executado'.")
        erro("ID do Cliente em branco no Orçamento → clique na linha do cliente na aba Clientes antes de criar o orçamento.")
        erro("Peça não buscada pelo código → verifique se o código foi cadastrado no campo 'Cód Fábrica' no Catálogo.")
        nl()
        h3("  🔒 ESTORNO — QUANDO USAR")
        item("Use Estornar apenas se precisar corrigir um orçamento lançado incorretamente.")
        item("O estorno apaga TODAS as parcelas a receber e a pagar do orçamento.")
        item("Após estornar, corrija e aprove novamente.")
        nl()
        aviso("Nunca exclua um fornecedor que já tem peças em orçamentos ativos — isso pode quebrar os vínculos no Contas a Pagar.")
        nl()
        w("  " + "─" * 72 + "\n", "separador")
        w("  Sistema Multi Escape ERP v1.2  •  Todos os direitos reservados.\n", "separador")
        w("  " + "─" * 72 + "\n", "separador")

    def _manual_ir_para(self, chave):
        """Navega o painel de texto até a âncora da seção e destaca o botão ativo."""
        # Destaque visual no botão selecionado
        for k, btn in self._botoes_nav.items():
            btn.config(bg="#2C3E50", fg="#ECF0F1")
        if chave in self._botoes_nav:
            self._botoes_nav[chave].config(bg="#2980B9", fg="white")

        # Busca a tag âncora no texto e rola até ela
        self.txt_manual_area.config(state="normal")
        tag_name = f"ancora_{chave}"
        idx = self.txt_manual_area.tag_nextrange(tag_name, "1.0")
        if idx:
            self.txt_manual_area.see(idx[0])
            self.txt_manual_area.mark_set("insert", idx[0])
        self.txt_manual_area.config(state="disabled")

    def _manual_buscar(self):
        """Destaca todas as ocorrências do termo buscado no manual."""
        self.txt_manual_area.config(state="normal")
        self.txt_manual_area.tag_remove("busca_match", "1.0", "end")
        termo = self.txt_busca_manual.get().strip()
        if not termo:
            self.lbl_busca_resultado.config(text="")
            self.txt_manual_area.config(state="disabled")
            return

        self.txt_manual_area.tag_config("busca_match", background="#F9E547", foreground="#000")
        start = "1.0"; count = 0; primeira = None
        while True:
            pos = self.txt_manual_area.search(termo, start, nocase=True, stopindex="end")
            if not pos: break
            end_pos = f"{pos}+{len(termo)}c"
            self.txt_manual_area.tag_add("busca_match", pos, end_pos)
            if count == 0:
                primeira = pos
            count += 1
            start = end_pos

        if primeira:
            self.txt_manual_area.see(primeira)
        self.lbl_busca_resultado.config(
            text=f"{count} ocorrência(s) encontrada(s)" if count else "Nenhum resultado."
        )
        self.txt_manual_area.config(state="disabled")

    def _manual_limpar_busca(self):
        self.txt_busca_manual.delete(0, "end")
        self.txt_manual_area.config(state="normal")
        self.txt_manual_area.tag_remove("busca_match", "1.0", "end")
        self.lbl_busca_resultado.config(text="")
        self.txt_manual_area.config(state="disabled")

    # ==========================================
    # 4. MÉTODOS CORE (sem alterações de lógica)
    # ==========================================
    def atualizar_todos_os_dados(self):
        self.carregar_marcas_e_clientes()
        self.carregar_fornecedores()
        self.carregar_catalogo_pecas()
        self.carregar_modelos_custom_grid()
        self.carregar_contas_receber()
        self.carregar_contas_pagar()
        self.carregar_todos_orcamentos_consulta()
        self.carregar_painel_fluxo_acumulado()

    def auto_buscar_peca_por_codigo(self, event=None):
        codigo_digitado = self.txt_item_cod.get().strip()
        if not codigo_digitado:
            return
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT cp.id, cp.codigo_fabrica, cp.nome_peca, cp.valor_compra, f.nome_empresa
            FROM catalogo_pecas cp LEFT JOIN fornecedores f ON cp.fornecedor_id = f.id
            WHERE cp.id = ? OR cp.codigo_fabrica = ?
        ''', (codigo_digitado, codigo_digitado))
        res = cursor.fetchone()
        conn.close()
        if res:
            id_, cod_fab, nome_peca, valor, nome_fornecedor = res
            valor = float(valor or 0)
            self._aplicar_dados_peca_form({
                "id": id_,
                "codigo": cod_fab or str(id_),
                "nome": nome_peca,
                "valor": valor,
                "custo": valor,
                "fornecedor": nome_fornecedor or "",
            })

    def _formatar_opcao_peca_catalogo(self, id_, cod, nome, valor, forn):
        cod_txt = cod or str(id_)
        forn_txt = forn or "Sem fornecedor"
        return f"{nome} | R$ {valor:.2f} | {forn_txt} [{cod_txt}]"

    def autocomplete_peca_orc(self, event=None):
        if event and event.keysym in ("Up", "Down", "Return", "Tab"):
            return
        termo = self.txt_item_desc.get().strip()
        if " | R$" in termo:
            termo = termo.split(" | R$")[0].strip()
        conn = conectar_banco()
        cursor = conn.cursor()
        if termo:
            cursor.execute(
                """SELECT cp.id, cp.codigo_fabrica, cp.nome_peca, cp.valor_compra, f.nome_empresa
                   FROM catalogo_pecas cp LEFT JOIN fornecedores f ON cp.fornecedor_id = f.id
                   WHERE cp.nome_peca LIKE ? OR cp.codigo_fabrica LIKE ?
                   ORDER BY cp.nome_peca, f.nome_empresa LIMIT 40""",
                (f"%{termo}%", f"%{termo}%"),
            )
        else:
            cursor.execute(
                """SELECT cp.id, cp.codigo_fabrica, cp.nome_peca, cp.valor_compra, f.nome_empresa
                   FROM catalogo_pecas cp LEFT JOIN fornecedores f ON cp.fornecedor_id = f.id
                   ORDER BY cp.nome_peca LIMIT 25"""
            )
        self._mapa_sugestoes_peca = {}
        opcoes = []
        for id_, cod, nome, valor, forn in cursor.fetchall():
            valor = float(valor or 0)
            display = self._formatar_opcao_peca_catalogo(id_, cod, nome, valor, forn)
            opcoes.append(display)
            self._mapa_sugestoes_peca[display] = {
                "id": id_,
                "codigo": cod or str(id_),
                "nome": nome,
                "valor": valor,
                "custo": valor,
                "fornecedor": forn or "",
            }
        conn.close()
        self.txt_item_desc["values"] = opcoes

    def ao_selecionar_peca_orc(self, event=None):
        selecionado = self.txt_item_desc.get().strip()
        if not selecionado:
            return
        dados = self._mapa_sugestoes_peca.get(selecionado)
        if not dados:
            for display, info in self._mapa_sugestoes_peca.items():
                if info["nome"].lower() == selecionado.lower():
                    dados = info
                    break
                if display.lower().startswith(selecionado.lower()):
                    dados = info
                    break
        if dados:
            self._aplicar_dados_peca_form(dados)

    def _aplicar_dados_peca_form(self, dados):
        self.txt_item_cod.delete(0, "end")
        self.txt_item_cod.insert(0, dados["codigo"])
        self.txt_item_desc.set(dados["nome"])
        self.txt_item_valor.delete(0, "end")
        self.txt_item_valor.insert(0, f"{dados['valor']:.2f}")
        self.txt_item_custo_compra.delete(0, "end")
        self.txt_item_custo_compra.insert(0, f"{dados['custo']:.2f}")
        self.txt_item_fornecedor_combo.set(dados["fornecedor"])
        if not self.txt_item_qtd.get().strip():
            self.txt_item_qtd.delete(0, "end")
            self.txt_item_qtd.insert(0, "1")

    def carregar_painel_fluxo_acumulado(self):
        mes_ano = _normalizar_mes_ano(self.txt_fluxo_mes_ano.get())
        if not mes_ano:
            return
        for item in self.tree_acumulado_pagar.get_children():
            self.tree_acumulado_pagar.delete(item)
        for item in self.tree_acumulado_receber.get_children():
            self.tree_acumulado_receber.delete(item)

        try:
            mes_int, ano_int = int(mes_ano.split("/")[0]), int(mes_ano.split("/")[1])
            ultimo_dia = monthrange(ano_int, mes_int)[1]
        except (ValueError, IndexError):
            ultimo_dia = 31

        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT cp.data_vencimento, f.nome_empresa, cp.peca_descricao, cp.valor_custo, cp.num_parcela
            FROM contas_pagar cp JOIN fornecedores f ON cp.fornecedor_id = f.id
            WHERE cp.data_vencimento LIKE ?
        ''', (f"%{mes_ano}",))
        dados_pagar = []
        for row in cursor.fetchall():
            data_norm = _normalizar_data_br(row[0])
            if data_norm and _mes_ano_da_data(data_norm) == mes_ano:
                dados_pagar.append((data_norm, row[1], row[2], float(row[3] or 0), row[4]))

        total_geral_pagar = sum(r[3] for r in dados_pagar)
        for dia in range(1, ultimo_dia + 1):
            data_chave = f"{dia:02d}/{mes_ano}"
            lancamentos_dia = [l for l in dados_pagar if l[0] == data_chave]
            if not lancamentos_dia:
                continue
            subtotal_dia = sum(l[3] for l in lancamentos_dia)
            node_mae = self.tree_acumulado_pagar.insert(
                "", "end", text=f"Dia {data_chave}",
                values=("Subtotal do Dia", f"R$ {subtotal_dia:.2f}"),
            )
            for _, f_nome, p_desc, v_custo, n_parc in lancamentos_dia:
                self.tree_acumulado_pagar.insert(
                    node_mae, "end", text="   ↳ Item:",
                    values=(f"{f_nome} ({n_parc}) - {p_desc}", f"R$ {v_custo:.2f}"),
                )
        self.lbl_somatoria_pagar_acum.config(
            text=f"TOTAL GERAL A PAGAR NO MÊS: R$ {total_geral_pagar:.2f}"
        )

        cursor.execute('''
            SELECT cr.data_vencimento, c.nome, cr.num_parcela, cr.valor_parcela
            FROM contas_receber cr JOIN clientes c ON cr.cliente_id = c.id
            WHERE cr.data_vencimento LIKE ?
        ''', (f"%{mes_ano}",))
        dados_receber = []
        for row in cursor.fetchall():
            data_norm = _normalizar_data_br(row[0])
            if data_norm and _mes_ano_da_data(data_norm) == mes_ano:
                dados_receber.append((data_norm, row[1], row[2], float(row[3] or 0)))

        total_geral_receber = sum(r[3] for r in dados_receber)
        for dia in range(1, ultimo_dia + 1):
            data_chave = f"{dia:02d}/{mes_ano}"
            lancamentos_dia_rec = [l for l in dados_receber if l[0] == data_chave]
            if not lancamentos_dia_rec:
                continue
            subtotal_dia_rec = sum(l[3] for l in lancamentos_dia_rec)
            node_mae_rec = self.tree_acumulado_receber.insert(
                "", "end", text=f"Dia {data_chave}",
                values=("Subtotal do Dia", f"R$ {subtotal_dia_rec:.2f}"),
            )
            for _, c_nome, n_parc, v_parc in lancamentos_dia_rec:
                self.tree_acumulado_receber.insert(
                    node_mae_rec, "end", text="   ↳ Item:",
                    values=(f"{c_nome} (Parc. {n_parc})", f"R$ {v_parc:.2f}"),
                )
        self.lbl_somatoria_receber_acum.config(
            text=f"TOTAL GERAL A RECEBER NO MÊS: R$ {total_geral_receber:.2f}"
        )
        conn.close()

    def carregar_marcas_e_clientes(self):
        conn = conectar_banco(); cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT marca_nome FROM marcas_modelos_veiculos ORDER BY marca_nome ASC")
        self.txt_marca['values'] = [r[0] for r in cursor.fetchall()]
        for item in self.tree_clientes.get_children(): self.tree_clientes.delete(item)
        cursor.execute("SELECT id, nome, placa, marca, modelo, ano FROM clientes ORDER BY id DESC")
        linhas = cursor.fetchall(); nomes, placas = [], []
        for i, r in enumerate(linhas):
            tag = "par" if i % 2 == 0 else "impar"
            self.tree_clientes.insert("", "end", values=r, tags=(tag,))
            nomes.append(r[1]); placas.append(r[2])
        conn.close()
        self.txt_nome['values'] = sorted(list(set(nomes)))
        self.txt_placa['values'] = sorted(list(set(placas)))
        if hasattr(self, "txt_orc_cliente_nome"):
            self.txt_orc_cliente_nome["values"] = sorted(list(set(nomes)))

    def _atualizar_btn_ultimo_orcamento(self):
        if hasattr(self, "btn_ultimo_orc"):
            state = "normal" if self.ultimo_orcamento_salvo_id else "disabled"
            self.btn_ultimo_orc.config(state=state)

    def abrir_ultimo_orcamento_salvo(self):
        if not self.ultimo_orcamento_salvo_id:
            messagebox.showinfo("Aviso", "Nenhum orçamento foi salvo nesta sessão ainda.")
            return
        self.carregar_orcamento_para_edicao(self.ultimo_orcamento_salvo_id)

    def _imprimir_orcamento_pdf(self, orc_id, pdf_path=None):
        if not pdf_path or not os.path.isfile(pdf_path):
            pdf_path = gerar_pdf_orcamento(orc_id)
        if not pdf_path or not os.path.isfile(pdf_path):
            messagebox.showerror(
                "Impressão",
                "Não foi possível gerar o PDF do orçamento.\n"
                "Verifique se o ReportLab está instalado.",
            )
            return
        caminho = os.path.abspath(pdf_path)
        try:
            if sys.platform == "win32":
                os.startfile(caminho, "print")
            else:
                os.startfile(caminho)
        except OSError:
            try:
                os.startfile(caminho)
            except OSError as e:
                messagebox.showerror("Impressão", f"Não foi possível abrir o PDF:\n{e}")

    def limpar_formulario_orcamento(self):
        self.id_orcamento_editando = None
        self.id_item_orcamento_selecionado_idx = None
        self.lista_produtos_temporaria.clear()
        self.lbl_orc_modo.config(text="Modo: Novo Orçamento")
        self.btn_salvar_orcamento.config(text="SALVAR PROPOSTA DE ORÇAMENTO (GERAR PDF)")
        self.txt_orc_cliente_id.delete(0, "end")
        if hasattr(self, "txt_orc_cliente_nome"):
            self.txt_orc_cliente_nome.set("")
        self.txt_servico_sol.delete(0, "end")
        self.txt_orc_data_atual.delete(0, "end")
        self.txt_orc_data_atual.insert(0, datetime.now().strftime("%d/%m/%Y"))
        self.txt_status_orc.set("Aguardando Retorno")
        self.txt_valor_mo.delete(0, "end")
        self.txt_valor_mo.insert(0, "0.00")
        self.txt_pagamento.delete(0, "end")
        self.txt_previsao_entrega.delete(0, "end")
        self.txt_observacao.delete("1.0", "end")
        self.cmb_forma_pagamento.set("À Vista / PIX")
        self.cmb_bandeira_cartao.set("Visa")
        self._ao_mudar_forma_pagamento()
        for v in self.flags_parcelas:
            v.set(False)
        self._limpar_campos_item_orcamento()
        self.atualizar_treeview_carrinho_e_valores()

    def _limpar_campos_item_orcamento(self):
        self.txt_item_cod.delete(0, "end")
        self.txt_item_desc.set("")
        self._mapa_sugestoes_peca = {}
        self.txt_item_qtd.delete(0, "end")
        self.txt_item_valor.delete(0, "end")
        self.txt_item_custo_compra.delete(0, "end")
        self.txt_item_fornecedor_combo.set("")
        self.txt_item_prazo_forn.set("À Vista")

    def carregar_orcamento_selecionado_para_edicao(self):
        sel = self.tree_consulta_orc.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione um orçamento na lista para editar.")
            return
        orc_id = self.tree_consulta_orc.item(sel[0], "values")[0]
        self.carregar_orcamento_para_edicao(orc_id)

    def carregar_orcamento_para_edicao(self, orc_id):
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT cliente_id, servico_solicitado, valor_mao_de_obra, observacao,
                      pagamento_info, status, data_orcamento, previsao_entrega,
                      qtd_parcelas_v11, bandeira_cartao
               FROM orcamentos WHERE id = ?""",
            (orc_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            messagebox.showerror("Erro", f"Orçamento Nº {orc_id} não encontrado.")
            return

        (c_id, servico, v_mo, obs, pag_info, status, data_orc, prev_ent,
         qtd_parc, bandeira) = row

        if status in ("Aprovado", "Executado"):
            conn.close()
            messagebox.showwarning(
                "Edição bloqueada",
                f"Orçamento Nº {orc_id} está '{status}'.\n"
                "Estorne para 'Aguardando Retorno' antes de editar peças e valores.",
            )
            return

        cursor.execute(
            """SELECT p.codigo, p.descricao, p.quantidade, p.valor_unitario,
                      f.nome_empresa, p.valor_compra_custo, p.forma_pagamento_fornecedor
               FROM produtos_orcamento p
               LEFT JOIN fornecedores f ON p.fornecedor_id = f.id
               WHERE p.orcamento_id = ?""",
            (orc_id,),
        )
        produtos = cursor.fetchall()
        cursor.execute("SELECT nome FROM clientes WHERE id = ?", (c_id,))
        nome_cliente = cursor.fetchone()
        nome_cliente = nome_cliente[0] if nome_cliente else ""
        conn.close()

        self.limpar_formulario_orcamento()
        self.id_orcamento_editando = int(orc_id)
        self.lbl_orc_modo.config(text=f"Modo: Editando Orçamento Nº {orc_id}")
        self.btn_salvar_orcamento.config(text=f"ATUALIZAR ORÇAMENTO Nº {orc_id} (GERAR PDF)")

        self.txt_orc_cliente_id.insert(0, str(c_id))
        if hasattr(self, "txt_orc_cliente_nome") and nome_cliente:
            self.txt_orc_cliente_nome.set(nome_cliente)
        self.txt_servico_sol.insert(0, servico or "")
        self.txt_orc_data_atual.delete(0, "end")
        self.txt_orc_data_atual.insert(0, data_orc or datetime.now().strftime("%d/%m/%Y"))
        self.txt_status_orc.set(status or "Aguardando Retorno")
        self.txt_valor_mo.delete(0, "end")
        self.txt_valor_mo.insert(0, f"{float(v_mo or 0):.2f}")
        self.txt_previsao_entrega.insert(0, prev_ent or "")
        if obs:
            self.txt_observacao.insert("1.0", obs)

        pag_txt = pag_info or ""
        if pag_txt.startswith("Cartão de Crédito"):
            self.cmb_forma_pagamento.set("Cartão de Crédito")
            self.cmb_bandeira_cartao.config(state="readonly")
            if bandeira:
                self.cmb_bandeira_cartao.set(bandeira)
            if "—" in pag_txt:
                self.txt_pagamento.insert(0, pag_txt.split("—", 1)[1].strip())
        elif pag_txt.startswith("À Vista / PIX"):
            self.cmb_forma_pagamento.set("À Vista / PIX")
            if "—" in pag_txt:
                self.txt_pagamento.insert(0, pag_txt.split("—", 1)[1].strip())
        elif pag_txt.startswith("Cartão de Débito"):
            self.cmb_forma_pagamento.set("Cartão de Débito")
            if "—" in pag_txt:
                self.txt_pagamento.insert(0, pag_txt.split("—", 1)[1].strip())
        else:
            self.txt_pagamento.insert(0, pag_txt)

        for i, flag in enumerate(self.flags_parcelas):
            flag.set(i + 1 == int(qtd_parc or 1))

        data_ins = data_orc or datetime.now().strftime("%d/%m/%Y")
        for cod, desc, qtd, unit, forn, custo, prazo in produtos:
            self.lista_produtos_temporaria.append({
                "codigo": cod or "",
                "descricao": desc or "",
                "quantidade": int(qtd or 1),
                "valor_unitario": float(unit or 0),
                "fornecedor": forn or "",
                "custo_compra": float(custo or 0),
                "prazo_fornecedor": prazo or "À Vista",
                "data": data_ins,
            })

        self.atualizar_treeview_carrinho_e_valores()
        self.abas.select(self.aba_orcamentos)
        messagebox.showinfo(
            "Orçamento carregado",
            f"Orçamento Nº {orc_id} pronto para edição.\n"
            "Remova peças recusadas, inclua novas linhas e salve para gerar PDF atualizado.",
        )

    def _preencher_form_item_carrinho(self, event=None):
        sel = self.tree_itens.selection()
        if not sel:
            return
        idx = self.tree_itens.index(sel[0])
        if idx >= len(self.lista_produtos_temporaria):
            return
        item = self.lista_produtos_temporaria[idx]
        self.id_item_orcamento_selecionado_idx = idx
        self.txt_item_cod.delete(0, "end")
        self.txt_item_cod.insert(0, item.get("codigo", ""))
        self.txt_item_desc.set(item.get("descricao", ""))
        self.txt_item_qtd.delete(0, "end")
        self.txt_item_qtd.insert(0, str(item.get("quantidade", 1)))
        self.txt_item_valor.delete(0, "end")
        self.txt_item_valor.insert(0, f"{item.get('valor_unitario', 0):.2f}")
        self.txt_item_custo_compra.delete(0, "end")
        self.txt_item_custo_compra.insert(0, f"{item.get('custo_compra', 0):.2f}")
        self.txt_item_fornecedor_combo.set(item.get("fornecedor", ""))
        self.txt_item_prazo_forn.set(item.get("prazo_fornecedor", "À Vista"))

    def atualizar_item_lista(self):
        if self.id_item_orcamento_selecionado_idx is None:
            messagebox.showwarning("Aviso", "Selecione uma peça na lista (clique ou duplo clique).")
            return
        if not self.txt_item_desc.get() or not self.txt_item_qtd.get() or not self.txt_item_valor.get():
            messagebox.showwarning("Aviso", "Preencha descrição, quantidade e preço de venda.")
            return
        try:
            idx = self.id_item_orcamento_selecionado_idx
            self.lista_produtos_temporaria[idx] = {
                "codigo": self.txt_item_cod.get(),
                "descricao": self.txt_item_desc.get(),
                "quantidade": int(self.txt_item_qtd.get()),
                "valor_unitario": float(str(self.txt_item_valor.get()).replace(",", ".")),
                "fornecedor": self.txt_item_fornecedor_combo.get(),
                "custo_compra": float(str(self.txt_item_custo_compra.get() or 0).replace(",", ".")),
                "prazo_fornecedor": self.txt_item_prazo_forn.get(),
                "data": self.lista_produtos_temporaria[idx].get(
                    "data", self.txt_orc_data_atual.get() or datetime.now().strftime("%d/%m/%Y")
                ),
            }
            self._limpar_campos_item_orcamento()
            self.id_item_orcamento_selecionado_idx = None
            self.atualizar_treeview_carrinho_e_valores()
        except ValueError:
            messagebox.showerror("Erro", "Quantidade e valores devem ser numéricos.")

    def _atualizar_totais_orcamento_display(self):
        total_pecas = sum(i["quantidade"] * i["valor_unitario"] for i in self.lista_produtos_temporaria)
        try:
            mo = float(str(self.txt_valor_mo.get() or 0).replace(",", "."))
        except ValueError:
            mo = 0.0
        total_geral = total_pecas + mo
        if hasattr(self, "lbl_total_pecas_orc"):
            self.lbl_total_pecas_orc.config(text=f"Peças: R$ {total_pecas:.2f}")
            self.lbl_total_mo_orc.config(text=f"M.O.: R$ {mo:.2f}")
            self.lbl_total_geral_orc.config(text=f"TOTAL GERAL: R$ {total_geral:.2f}")

    def adicionar_item_lista(self):
        if not self.txt_item_desc.get() or not self.txt_item_qtd.get() or not self.txt_item_valor.get(): return
        data_insercao = self.txt_orc_data_atual.get() if self.txt_orc_data_atual.get() else datetime.now().strftime("%d/%m/%Y")
        try:
            self.lista_produtos_temporaria.append({
                'codigo': self.txt_item_cod.get(), 'descricao': self.txt_item_desc.get(),
                'quantidade': int(self.txt_item_qtd.get()),
                'valor_unitario': float(str(self.txt_item_valor.get()).replace(",", ".")),
                'fornecedor': self.txt_item_fornecedor_combo.get(),
                'custo_compra': float(str(self.txt_item_custo_compra.get() or 0).replace(",", ".")),
                'prazo_fornecedor': self.txt_item_prazo_forn.get(), 'data': data_insercao
            })
            self._limpar_campos_item_orcamento()
            self.id_item_orcamento_selecionado_idx = None
            self.atualizar_treeview_carrinho_e_valores()
        except ValueError:
            messagebox.showerror("Erro", "Quantidade e valores devem ser numéricos.")

    def atualizar_treeview_carrinho_e_valores(self):
        for item in self.tree_itens.get_children():
            self.tree_itens.delete(item)
        for item in self.lista_produtos_temporaria:
            tot = item['quantidade'] * item['valor_unitario']
            self.tree_itens.insert("", "end", values=(
                item['codigo'], item['descricao'], str(item['quantidade']),
                f"{item['valor_unitario']:.2f}", f"{tot:.2f}",
                item['fornecedor'], f"{item['custo_compra']:.2f}", item['data'],
            ))
        self._atualizar_totais_orcamento_display()
        self.recalcular_parcelas_dinamicas()

    def finalizar_orcamento(self):
        c_id = self.txt_orc_cliente_id.get()
        if not c_id:
            messagebox.showwarning("Aviso", "O campo ID Cliente * é obrigatório.")
            return

        total_geral = self.calcular_total_atual_memoria()
        status_atual = self.txt_status_orc.get()
        data_final_orc = self.txt_orc_data_atual.get() if self.txt_orc_data_atual.get() else datetime.now().strftime("%d/%m/%Y")

        # Descobre quantas parcelas foram marcadas
        num_vezes_parcelas = 1
        for i in range(1, 11):
            if self.flags_parcelas[i-1].get():
                num_vezes_parcelas = i
                break

        parcelas_filtradas = [f"{num_vezes_parcelas}X de R$ {total_geral / num_vezes_parcelas:.2f}"]

        bandeira_cartao = ""
        taxa_cartao = 0.0
        total_com_juros = total_geral
        if self.cmb_forma_pagamento.get() == "Cartão de Crédito":
            bandeira_cartao = self.cmb_bandeira_cartao.get() or "Visa"
            taxa_cartao = self._obter_taxa_parcela(num_vezes_parcelas)
            total_com_juros = calcular_valor_com_juros(total_geral, taxa_cartao)
            juros_valor = total_com_juros - total_geral
            parc_com_juros = total_com_juros / num_vezes_parcelas
            parcelas_filtradas = [
                f"{num_vezes_parcelas}X de R$ {parc_com_juros:.2f} "
                f"(c/ juros {taxa_cartao:.2f}% {bandeira_cartao} — "
                f"base R$ {total_geral:.2f} + juros R$ {juros_valor:.2f} = R$ {total_com_juros:.2f})"
            ]

        pag_info = self.txt_pagamento.get()
        forma_pg = self.cmb_forma_pagamento.get()
        if forma_pg:
            prefixo = forma_pg
            if bandeira_cartao:
                prefixo += f" ({bandeira_cartao})"
            pag_info = f"{prefixo} — {pag_info}" if pag_info else prefixo

        conn = conectar_banco()
        cursor = conn.cursor()
        editando = self.id_orcamento_editando is not None

        if editando:
            orc_id = self.id_orcamento_editando
            cursor.execute("SELECT status FROM orcamentos WHERE id = ?", (orc_id,))
            st_row = cursor.fetchone()
            if not st_row:
                conn.close()
                messagebox.showerror("Erro", "Orçamento não encontrado.")
                return
            if st_row[0] in ("Aprovado", "Executado"):
                conn.close()
                messagebox.showwarning(
                    "Edição bloqueada",
                    "Estorne o orçamento antes de salvar alterações.",
                )
                return
            cursor.execute('''
                UPDATE orcamentos SET
                    cliente_id=?, servico_solicitado=?, valor_mao_de_obra=?, observacao=?,
                    pagamento_info=?, parcelas_impressao=?, status=?, data_orcamento=?,
                    previsao_entrega=?, qtd_parcelas_v11=?, bandeira_cartao=?,
                    taxa_cartao_percentual=?, valor_liquido_estimado=?
                WHERE id=?
            ''', (c_id, self.txt_servico_sol.get(), float(str(self.txt_valor_mo.get() or 0).replace(",", ".")),
                  self.txt_observacao.get("1.0", "end-1c"), pag_info,
                  " | ".join(parcelas_filtradas), status_atual, data_final_orc,
                  self.txt_previsao_entrega.get(), num_vezes_parcelas,
                  bandeira_cartao or None, taxa_cartao, total_com_juros, orc_id))
            cursor.execute("DELETE FROM produtos_orcamento WHERE orcamento_id = ?", (orc_id,))
        else:
            cursor.execute('''
                INSERT INTO orcamentos (cliente_id, servico_solicitado, valor_mao_de_obra, observacao, pagamento_info, parcelas_impressao, status, data_orcamento, previsao_entrega, qtd_parcelas_v11, bandeira_cartao, taxa_cartao_percentual, valor_liquido_estimado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (c_id, self.txt_servico_sol.get(), float(str(self.txt_valor_mo.get() or 0).replace(",", ".")),
                  self.txt_observacao.get("1.0", "end-1c"), pag_info,
                  " | ".join(parcelas_filtradas), status_atual, data_final_orc,
                  self.txt_previsao_entrega.get(), num_vezes_parcelas,
                  bandeira_cartao or None, taxa_cartao, total_com_juros))
            orc_id = cursor.lastrowid

        for item in self.lista_produtos_temporaria:
            cursor.execute("SELECT id FROM fornecedores WHERE nome_empresa = ?", (item['fornecedor'],))
            res_f = cursor.fetchone(); f_id = res_f[0] if res_f else None
            cursor.execute('INSERT INTO produtos_orcamento (orcamento_id, codigo, descricao, quantidade, valor_unitario, fornecedor_id, valor_compra_custo, forma_pagamento_fornecedor) VALUES (?,?,?,?,?,?,?,?)',
                           (orc_id, item['codigo'], item['descricao'], item['quantidade'], item['valor_unitario'], f_id, item['custo_compra'], item['prazo_fornecedor']))

        if status_atual in ("Aprovado", "Executado"):
            valor_por_parcela = total_com_juros / num_vezes_parcelas
            cursor.execute("DELETE FROM contas_receber WHERE orcamento_id = ?", (orc_id,))
            for p in range(1, num_vezes_parcelas + 1):
                cursor.execute('INSERT INTO contas_receber (orcamento_id, cliente_id, num_parcela, valor_parcela, data_vencimento) VALUES (?,?,?,?,?)',
                               (orc_id, c_id, f"{p}/{num_vezes_parcelas}", valor_por_parcela,
                                (datetime.now() + timedelta(days=30 * (p - 1))).strftime("%d/%m/%Y")))
            # Gera contas_pagar já na aprovação
            self._gerar_contas_pagar(orc_id, cursor)

        conn.commit(); conn.close()
        pdf_path = gerar_pdf_orcamento(orc_id)

        if status_atual == "Executado":
            self.mudar_orcamento_para_executado(forced_id=orc_id)

        self.ultimo_orcamento_salvo_id = orc_id
        self._atualizar_btn_ultimo_orcamento()

        msg_extra = ""
        if taxa_cartao > 0:
            msg_extra = (
                f"\nBase: R$ {total_geral:.2f} + juros {taxa_cartao:.2f}% "
                f"= Total: R$ {total_com_juros:.2f}"
            )
        acao = "atualizado" if editando else "salvo"
        valor_parcela_msg = total_com_juros / num_vezes_parcelas
        messagebox.showinfo(
            "Sucesso",
            f"Orçamento Nº {orc_id} {acao}!\n"
            f"Parcelas: {num_vezes_parcelas}x de R$ {valor_parcela_msg:.2f}{msg_extra}",
        )
        if messagebox.askyesno("Impressão", "Deseja imprimir o orçamento?"):
            self._imprimir_orcamento_pdf(orc_id, pdf_path)
        self.limpar_formulario_orcamento()
        self.atualizar_todos_os_dados()

    def limpar_filtros_busca_orcamento(self):
        self.txt_filtro_orc_data_ini.delete(0, "end")
        self.txt_filtro_orc_data_fim.delete(0, "end")
        self.carregar_todos_orcamentos_consulta()

    def excluir_orcamento_sistema(self):
        sel = self.tree_consulta_orc.selection()
        if not sel: return
        orc_id = self.tree_consulta_orc.item(sel[0], "values")[0]
        if messagebox.askyesno("Confirmar Exclusão", f"Deseja apagar o Orçamento Nº {orc_id} e todas as suas parcelas?"):
            conn = conectar_banco(); cursor = conn.cursor()
            cursor.execute("DELETE FROM orcamentos WHERE id = ?", (orc_id,))
            cursor.execute("DELETE FROM contas_receber WHERE orcamento_id = ?", (orc_id,))
            cursor.execute("DELETE FROM contas_pagar WHERE orcamento_id = ?", (orc_id,))
            conn.commit(); conn.close(); self.atualizar_todos_os_dados()

    # ==========================================
    # AUXILIAR: geração de contas a pagar
    # Chamado tanto na Aprovação quanto na Execução,
    # consolidando os custos por fornecedor + prazo.
    # ==========================================
    def _gerar_contas_pagar(self, orc_id, cursor):
        """Apaga e recria os lançamentos de contas_pagar para o orçamento informado.
        Recebe o cursor já aberto (dentro de uma transação ativa)."""
        cursor.execute("DELETE FROM contas_pagar WHERE orcamento_id = ?", (orc_id,))

        cursor.execute(
            "SELECT quantidade, valor_compra_custo, fornecedor_id, "
            "forma_pagamento_fornecedor, descricao "
            "FROM produtos_orcamento WHERE orcamento_id = ?",
            (orc_id,)
        )
        itens = cursor.fetchall()

        # Agrupa por (fornecedor, prazo) para consolidar num único lançamento
        mapa = {}
        for qtd, v_custo, f_id, prazo, desc in itens:
            if not f_id:
                continue  # peça sem fornecedor vinculado: ignora
            chave = (f_id, prazo or "À Vista")
            if chave not in mapa:
                mapa[chave] = {"total": 0.0, "descricoes": []}
            mapa[chave]["total"] += (v_custo or 0.0) * (qtd or 1)
            mapa[chave]["descricoes"].append(desc or "")

        hoje = datetime.now()
        for (f_id, prazo), dados in mapa.items():
            custo_total = dados["total"]
            desc_lote = ", ".join(list(set(dados["descricoes"])))[:90]

            if prazo == "À Vista":
                cursor.execute(
                    'INSERT INTO contas_pagar '
                    '(orcamento_id, fornecedor_id, num_parcela, peca_descricao, valor_custo, data_vencimento) '
                    'VALUES (?,?,?,?,?,?)',
                    (orc_id, f_id, "1/1", f"Lote: {desc_lote}", custo_total,
                     hoje.strftime("%d/%m/%Y"))
                )
            elif prazo == "30 Dias":
                cursor.execute(
                    'INSERT INTO contas_pagar '
                    '(orcamento_id, fornecedor_id, num_parcela, peca_descricao, valor_custo, data_vencimento) '
                    'VALUES (?,?,?,?,?,?)',
                    (orc_id, f_id, "1/1", f"Lote: {desc_lote}", custo_total,
                     (hoje + timedelta(days=30)).strftime("%d/%m/%Y"))
                )
            elif prazo == "60 Dias":
                valor_rateado = custo_total / 2
                cursor.execute(
                    'INSERT INTO contas_pagar '
                    '(orcamento_id, fornecedor_id, num_parcela, peca_descricao, valor_custo, data_vencimento) '
                    'VALUES (?,?,?,?,?,?)',
                    (orc_id, f_id, "1/2", f"Lote: {desc_lote}", valor_rateado,
                     (hoje + timedelta(days=30)).strftime("%d/%m/%Y"))
                )
                cursor.execute(
                    'INSERT INTO contas_pagar '
                    '(orcamento_id, fornecedor_id, num_parcela, peca_descricao, valor_custo, data_vencimento) '
                    'VALUES (?,?,?,?,?,?)',
                    (orc_id, f_id, "2/2", f"Lote: {desc_lote}", valor_rateado,
                     (hoje + timedelta(days=60)).strftime("%d/%m/%Y"))
                )

    def mudar_orcamento_para_aprovado(self, forced_id=None):
        orc_id = forced_id
        if not orc_id:
            sel = self.tree_consulta_orc.selection()
            if not sel: messagebox.showwarning("Aviso", "Selecione uma proposta."); return
            orc_id = self.tree_consulta_orc.item(sel[0], "values")[0]

        conn = conectar_banco(); cursor = conn.cursor()
        cursor.execute("SELECT status, cliente_id, valor_mao_de_obra, parcelas_impressao, qtd_parcelas_v11, taxa_cartao_percentual, pagamento_info FROM orcamentos WHERE id = ?", (orc_id,))
        row = cursor.fetchone()
        if not row: conn.close(); return
        status_atual, c_id, v_mo, txt_parc, num_parc_banco, taxa_banco, pag_info = row

        if status_atual in ["Aprovado", "Executado"] and not forced_id:
            messagebox.showinfo("Informação", "Este orçamento já foi aprovado/executado."); conn.close(); return

        cursor.execute("UPDATE orcamentos SET status = 'Aprovado' WHERE id = ?", (orc_id,))
        cursor.execute("SELECT quantidade, valor_unitario FROM produtos_orcamento WHERE orcamento_id = ?", (orc_id,))
        total_pecas = sum(i[0] * i[1] for i in cursor.fetchall())
        total_geral = total_pecas + v_mo

        num_vezes_parcelas = 1
        if num_parc_banco and num_parc_banco > 1:
            num_vezes_parcelas = num_parc_banco
        elif txt_parc and "X" in txt_parc:
            try: num_vezes_parcelas = int(txt_parc.split("X")[0].strip())
            except ValueError: num_vezes_parcelas = 1
        if num_vezes_parcelas < 1: num_vezes_parcelas = 1

        taxa_aplicar = float(taxa_banco or 0)
        if taxa_aplicar > 0 and pag_info and "Cartão de Crédito" in pag_info:
            total_final = calcular_valor_com_juros(total_geral, taxa_aplicar)
        else:
            total_final = total_geral
        valor_por_parcela = total_final / num_vezes_parcelas

        # --- Contas a Receber (parcelas do cliente) ---
        cursor.execute("DELETE FROM contas_receber WHERE orcamento_id = ?", (orc_id,))
        for p in range(1, num_vezes_parcelas + 1):
            cursor.execute(
                'INSERT INTO contas_receber '
                '(orcamento_id, cliente_id, num_parcela, valor_parcela, data_vencimento) '
                'VALUES (?,?,?,?,?)',
                (orc_id, c_id, f"{p}/{num_vezes_parcelas}", valor_por_parcela,
                 (datetime.now() + timedelta(days=30 * (p - 1))).strftime("%d/%m/%Y"))
            )

        # --- Contas a Pagar (custo das peças por fornecedor) ---
        # Gerado já na aprovação: o orçamento foi aprovado, as peças precisam ser compradas.
        self._gerar_contas_pagar(orc_id, cursor)

        cursor.execute("UPDATE orcamentos SET qtd_parcelas_v11 = ? WHERE id = ?", (num_vezes_parcelas, orc_id))
        conn.commit(); conn.close()
        if not forced_id: self.atualizar_todos_os_dados()

    def mudar_orcamento_para_executado(self, forced_id=None):
        orc_id = forced_id
        if not orc_id:
            sel = self.tree_consulta_orc.selection()
            if not sel: messagebox.showwarning("Aviso", "Selecione uma proposta."); return
            orc_id = self.tree_consulta_orc.item(sel[0], "values")[0]

        conn = conectar_banco(); cursor = conn.cursor()
        cursor.execute("SELECT status FROM orcamentos WHERE id = ?", (orc_id,))
        row = cursor.fetchone()
        if not row: conn.close(); return
        status_atual = row[0]

        if status_atual == "Executado" and not forced_id:
            messagebox.showinfo("Informação", "Já está finalizado operativamente."); conn.close(); return

        # Se ainda não estava aprovado, aprova primeiro (gera contas_receber + contas_pagar)
        if status_atual != "Aprovado":
            conn.close()
            self.mudar_orcamento_para_aprovado(forced_id=orc_id)
            conn = conectar_banco(); cursor = conn.cursor()

        # Atualiza status para Executado e regera contas_pagar (garante consistência)
        cursor.execute("UPDATE orcamentos SET status = 'Executado' WHERE id = ?", (orc_id,))
        self._gerar_contas_pagar(orc_id, cursor)

        conn.commit(); conn.close()
        if not forced_id: self.atualizar_todos_os_dados()

    def estornar_execucao_orcamento(self):
        sel = self.tree_consulta_orc.selection()
        if not sel: return
        orc_id = self.tree_consulta_orc.item(sel[0], "values")[0]
        if messagebox.askyesno("Confirmar Estorno", f"Estornar Orçamento Nº {orc_id}?\nIsso apagará todas as parcelas e contas vinculadas."):
            conn = conectar_banco(); cursor = conn.cursor()
            cursor.execute("UPDATE orcamentos SET status = 'Aguardando Retorno' WHERE id = ?", (orc_id,))
            cursor.execute("DELETE FROM contas_receber WHERE orcamento_id = ?", (orc_id,))
            cursor.execute("DELETE FROM contas_pagar WHERE orcamento_id = ?", (orc_id,))
            conn.commit(); conn.close(); self.atualizar_todos_os_dados()

    def carregar_contas_receber(self):
        for item in self.tree_receber.get_children(): self.tree_receber.delete(item)
        conn = conectar_banco(); cursor = conn.cursor()
        cursor.execute('SELECT cr.id, cr.orcamento_id, c.nome, cr.num_parcela, cr.valor_parcela, cr.data_vencimento, cr.status_pago FROM contas_receber cr JOIN clientes c ON cr.cliente_id = c.id WHERE cr.data_vencimento LIKE ?', (f"%{self.txt_rec_filtro_data.get()}%",))
        total_futuro = 0.0
        for r in cursor.fetchall():
            tag = "pago" if r[6] == "Pago" else ""
            if r[6] == "A Receber":
                try:
                    if datetime.strptime(r[5], "%d/%m/%Y") >= datetime.now(): total_futuro += r[4]
                    else: tag = "atrasado"
                except ValueError: pass
            self.tree_receber.insert("", "end", values=(r[0], r[1], r[2], r[3], f"R$ {r[4]:.2f}", r[5], r[6]), tags=(tag,))
        self.lbl_total_futuro_rec.config(text=f"Valores a Receber Futuros: R$ {total_futuro:.2f}")
        conn.close()

    def baixar_contas_receber(self):
        sel = self.tree_receber.selection()
        if sel:
            conn = conectar_banco(); cursor = conn.cursor()
            cursor.execute("UPDATE contas_receber SET status_pago = 'Pago' WHERE id = ?", (self.tree_receber.item(sel[0], "values")[0],))
            conn.commit(); conn.close()
            self.carregar_contas_receber(); self.carregar_todos_orcamentos_consulta(); self.carregar_painel_fluxo_acumulado()

    def estornar_contas_receber(self):
        sel = self.tree_receber.selection()
        if not sel: return
        conn = conectar_banco(); cursor = conn.cursor()
        cursor.execute("UPDATE contas_receber SET status_pago = 'A Receber' WHERE id = ?", (self.tree_receber.item(sel[0], "values")[0],))
        conn.commit(); conn.close()
        self.carregar_contas_receber(); self.carregar_todos_orcamentos_consulta(); self.carregar_painel_fluxo_acumulado()

    def carregar_contas_pagar(self):
        for item in self.tree_pagar.get_children(): self.tree_pagar.delete(item)
        conn = conectar_banco(); cursor = conn.cursor()
        q = 'SELECT cp.id, cp.orcamento_id, f.nome_empresa, cp.num_parcela, cp.peca_descricao, cp.valor_custo, cp.data_vencimento, cp.status_pago FROM contas_pagar cp JOIN fornecedores f ON cp.fornecedor_id = f.id WHERE cp.data_vencimento LIKE ?'
        p = [f"%{self.txt_pag_filtro_data.get()}%"]
        if self.txt_pag_filtro_forn.get() and self.txt_pag_filtro_forn.get() != "Todos":
            q += " AND f.nome_empresa = ?"; p.append(self.txt_pag_filtro_forn.get())
        cursor.execute(q, p)
        total = 0.0
        for r in cursor.fetchall():
            if r[7] == "A Pagar": total += r[5]
            self.tree_pagar.insert("", "end", values=(r[0], r[1], r[2], r[3], r[4], f"R$ {r[5]:.2f}", r[6], r[7]), tags=("pago" if r[7] == "Pago" else "",))
        self.lbl_total_comprometido_pag.config(text=f"Total Comprometido: R$ {total:.2f}")
        conn.close()

    def baixar_contas_pagar(self):
        sel = self.tree_pagar.selection()
        if sel:
            conn = conectar_banco(); cursor = conn.cursor()
            cursor.execute("UPDATE contas_pagar SET status_pago = 'Pago' WHERE id = ?", (self.tree_pagar.item(sel[0], "values")[0],))
            conn.commit(); conn.close(); self.carregar_contas_pagar(); self.carregar_painel_fluxo_acumulado()

    def carregar_fornecedores(self, event=None):
        for item in self.tree_fornecedores.get_children(): self.tree_fornecedores.delete(item)
        termo_busca = self.txt_busca_fornecedor_live.get() if hasattr(self, 'txt_busca_fornecedor_live') else ""
        conn = conectar_banco(); cursor = conn.cursor()
        cursor.execute("SELECT id, nome_empresa, telefone FROM fornecedores WHERE nome_empresa LIKE ?", (f"%{termo_busca}%",))
        fornecedores_lista = cursor.fetchall()
        for r in fornecedores_lista: self.tree_fornecedores.insert("", "end", values=r)
        nomes_forn = [f[1] for f in fornecedores_lista]
        self.txt_item_fornecedor_combo['values'] = nomes_forn
        self.txt_pag_filtro_forn['values'] = ["Todos"] + nomes_forn
        conn.close()

    def ao_selecionar_grid_clientes(self, event):
        sel = self.tree_clientes.selection()
        if sel: self.buscar_e_preencher_cliente("id", self.tree_clientes.item(sel[0], "values")[0])

    def limpar_campos_cliente(self):
        self.txt_nome.set(""); self.txt_placa.set(""); self.txt_marca.set(""); self.txt_veiculo.set("")
        self.txt_contato.delete(0, "end"); self.txt_email.delete(0, "end"); self.txt_cor.delete(0, "end")
        self._atualizar_logo_marca("")

    def salvar_cliente(self):
        if not self.txt_nome.get() or not self.txt_placa.get(): return
        conn = conectar_banco(); cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO clientes (nome, placa, marca, modelo, ano, contato, email, cor, data_cadastro) VALUES (?,?,?,?,?,?,?,?,?)',
                           (self.txt_nome.get(), self.txt_placa.get().upper(), self.txt_marca.get(), self.txt_veiculo.get(), self.txt_ano.get(), self.txt_contato.get(), self.txt_email.get(), self.txt_cor.get(), datetime.now().strftime("%d/%m/%Y")))
            conn.commit(); self.carregar_marcas_e_clientes(); self.limpar_campos_cliente()
            messagebox.showinfo("CRM", "Cliente registrado!")
        except sqlite3.IntegrityError: messagebox.showwarning("Aviso", "Placa já cadastrada.")
        finally: conn.close()

    def editar_cliente(self):
        id_c = self.txt_orc_cliente_id.get()
        if not id_c: return
        conn = conectar_banco(); cursor = conn.cursor()
        cursor.execute('UPDATE clientes SET nome=?, placa=?, marca=?, modelo=?, ano=?, contato=?, email=?, cor=? WHERE id=?',
                       (self.txt_nome.get(), self.txt_placa.get().upper(), self.txt_marca.get(), self.txt_veiculo.get(), self.txt_ano.get(), self.txt_contato.get(), self.txt_email.get(), self.txt_cor.get(), id_c))
        conn.commit(); conn.close(); self.carregar_marcas_e_clientes()

    def excluir_cliente(self):
        id_c = self.txt_orc_cliente_id.get()
        if id_c:
            conn = conectar_banco(); cursor = conn.cursor()
            cursor.execute("DELETE FROM clientes WHERE id=?", (id_c,))
            conn.commit(); conn.close(); self.carregar_marcas_e_clientes()

    def filtrar_modelos_por_marca(self, event=None):
        marca = self.txt_marca.get()
        conn = conectar_banco(); cursor = conn.cursor()
        cursor.execute("SELECT modelo_motor FROM marcas_modelos_veiculos WHERE marca_nome = ? ORDER BY modelo_motor ASC", (marca,))
        self.txt_veiculo['values'] = [r[0] for r in cursor.fetchall()]; conn.close()
        # Atualiza o painel de logo ao selecionar a marca
        self._atualizar_logo_marca(marca)

    def ao_selecionar_item_carrinho(self, event):
        sel = self.tree_itens.selection()
        if sel: self.id_item_orcamento_selecionado_idx = self.tree_itens.index(sel[0])

    def excluir_item_lista(self):
        if self.id_item_orcamento_selecionado_idx is not None:
            self.lista_produtos_temporaria.pop(self.id_item_orcamento_selecionado_idx)
            self.id_item_orcamento_selecionado_idx = None; self.atualizar_treeview_carrinho_e_valores()

    def calcular_total_atual_memoria(self):
        t = sum(i['quantidade'] * i['valor_unitario'] for i in self.lista_produtos_temporaria)
        try:
            mo = float(str(self.txt_valor_mo.get() or 0).replace(",", "."))
        except ValueError:
            mo = 0.0
        return t + mo

    def recalcular_parcelas_dinamicas(self):
        tg = self.calcular_total_atual_memoria()
        usar_taxa = (
            hasattr(self, "cmb_forma_pagamento")
            and self.cmb_forma_pagamento.get() == "Cartão de Crédito"
        )
        for i in range(1, 11):
            lbl_val = self.labels_valores_parcelas[i - 1]
            lbl_det = self.labels_detalhe_parcelas[i - 1] if hasattr(self, "labels_detalhe_parcelas") else None
            if not lbl_val:
                continue
            parc_base = tg / i
            if usar_taxa:
                taxa = self._obter_taxa_parcela(i)
                total_com_juros = calcular_valor_com_juros(tg, taxa)
                parc = total_com_juros / i
                juros_parc = (total_com_juros - tg) / i
                lbl_val.config(text=f" R$ {parc:.2f}")
                if lbl_det:
                    lbl_det.config(
                        text=(
                            f"Base R$ {parc_base:.2f}/parc  |  "
                            f"Juros {taxa:.2f}% (+R$ {juros_parc:.2f}/parc)  |  "
                            f"Total c/ juros: R$ {total_com_juros:.2f}"
                        )
                    )
            else:
                lbl_val.config(text=f" R$ {parc_base:.2f}")
                if lbl_det:
                    lbl_det.config(text=f"Total do orçamento: R$ {tg:.2f}")
        if hasattr(self, "lbl_taxa_aplicada"):
            self._atualizar_label_taxa_aplicada()

    def ao_dar_duplo_clique_peca_catalogo(self, event):
        sel = self.tree_catalogo_orc.selection()
        if sel:
            v = self.tree_catalogo_orc.item(sel[0], "values")
            try:
                valor = float(str(v[2]).replace(",", "."))
            except ValueError:
                valor = 0.0
            self._aplicar_dados_peca_form({
                "codigo": str(v[0]),
                "nome": v[1],
                "valor": valor,
                "custo": valor,
                "fornecedor": v[3] if v[3] else "",
            })

    def carregar_catalogo_pecas(self, event=None):
        for item in self.tree_catalogo_orc.get_children(): self.tree_catalogo_orc.delete(item)
        for item in self.tree_catalogo.get_children(): self.tree_catalogo.delete(item)
        termo_busca = ""
        if hasattr(self, 'txt_busca_catalogo_live') and self.txt_busca_catalogo_live.get():
            termo_busca = self.txt_busca_catalogo_live.get()
        elif hasattr(self, 'txt_busca_peca_orc') and self.txt_busca_peca_orc.get():
            termo_busca = self.txt_busca_peca_orc.get()
        conn = conectar_banco(); cursor = conn.cursor()
        cursor.execute('SELECT cp.id, cp.codigo_fabrica, cp.nome_peca, cp.valor_compra, f.nome_empresa FROM catalogo_pecas cp LEFT JOIN fornecedores f ON cp.fornecedor_id = f.id WHERE cp.nome_peca LIKE ? OR cp.codigo_fabrica LIKE ?', (f"%{termo_busca}%", f"%{termo_busca}%"))
        for r in cursor.fetchall():
            self.tree_catalogo_orc.insert("", "end", values=(r[0], r[2], r[3], r[4]))
            self.tree_catalogo.insert("", "end", values=r)
        conn.close()

    def salvar_peca_catalogo(self):
        if not self.id_fornecedor_selecionado or not self.txt_cat_nome.get(): return
        conn = conectar_banco(); cursor = conn.cursor()
        cursor.execute("INSERT INTO catalogo_pecas (codigo_fabrica, nome_peca, valor_compra, fornecedor_id) VALUES (?,?,?,?)",
                       (self.txt_cat_codigo_fabrica.get(), self.txt_cat_nome.get(), float(self.txt_cat_valor.get() or 0), self.id_fornecedor_selecionado))
        conn.commit(); conn.close()
        self.txt_cat_codigo_fabrica.delete(0, "end"); self.txt_cat_nome.delete(0, "end"); self.txt_cat_valor.delete(0, "end")
        self.atualizar_todos_os_dados()

    def excluir_peca_catalogo(self):
        if not self.id_peca_selecionada: return
        if messagebox.askyesno("Confirmar", "Deseja remover esta peça?"):
            conn = conectar_banco(); cursor = conn.cursor()
            cursor.execute("DELETE FROM catalogo_pecas WHERE id = ?", (self.id_peca_selecionada,))
            conn.commit(); conn.close(); self.id_peca_selecionada = None; self.atualizar_todos_os_dados()

    def carregar_modelos_custom_grid(self):
        for item in self.tree_modelos_custom.get_children(): self.tree_modelos_custom.delete(item)
        conn = conectar_banco(); cursor = conn.cursor()
        cursor.execute("SELECT id, marca_nome, modelo_motor FROM marcas_modelos_veiculos ORDER BY id DESC")
        for r in cursor.fetchall(): self.tree_modelos_custom.insert("", "end", values=r)
        conn.close()

    def salvar_modelo_custom(self):
        if not self.txt_custom_marca.get(): return
        conn = conectar_banco(); cursor = conn.cursor()
        cursor.execute("INSERT INTO marcas_modelos_veiculos (marca_nome, modelo_motor) VALUES (?,?)", (self.txt_custom_marca.get(), self.txt_custom_modelo.get()))
        conn.commit(); conn.close()
        self.txt_custom_marca.delete(0, "end"); self.txt_custom_modelo.delete(0, "end")
        self.atualizar_todos_os_dados()

    def fazer_ocr_imagem(self):
        arq = filedialog.askopenfilename()
        if arq: self.caminho_imagem_selecionada = arq

    def ao_selecionar_nome(self, event): self.buscar_e_preencher_cliente("nome", self.txt_nome.get())
    def ao_selecionar_placa(self, event): self.buscar_e_preencher_cliente("placa", self.txt_placa.get())

    def autocomplete_nome_cliente_orc(self, event=None):
        if event and event.keysym in ("Up", "Down", "Return", "Tab"):
            return
        termo = self.txt_orc_cliente_nome.get().strip()
        conn = conectar_banco()
        cursor = conn.cursor()
        if termo:
            cursor.execute(
                "SELECT DISTINCT nome FROM clientes WHERE nome LIKE ? ORDER BY nome LIMIT 25",
                (f"%{termo}%",),
            )
        else:
            cursor.execute("SELECT DISTINCT nome FROM clientes ORDER BY nome LIMIT 25")
        nomes = [r[0] for r in cursor.fetchall()]
        conn.close()
        self.txt_orc_cliente_nome["values"] = nomes

    def ao_selecionar_nome_orc(self, event=None):
        nome = self.txt_orc_cliente_nome.get().strip()
        if not nome:
            return
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM clientes WHERE nome = ? ORDER BY id DESC LIMIT 1",
            (nome,),
        )
        r = cursor.fetchone()
        conn.close()
        if r:
            self.txt_orc_cliente_id.delete(0, "end")
            self.txt_orc_cliente_id.insert(0, str(r[0]))

    def _preencher_nome_por_id_orc(self, event=None):
        c_id = self.txt_orc_cliente_id.get().strip()
        if not c_id:
            return
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute("SELECT nome FROM clientes WHERE id = ?", (c_id,))
        r = cursor.fetchone()
        conn.close()
        if r and hasattr(self, "txt_orc_cliente_nome"):
            self.txt_orc_cliente_nome.set(r[0])

    def buscar_e_preencher_cliente(self, campo, valor):
        conn = conectar_banco(); cursor = conn.cursor()
        cursor.execute(f"SELECT id, nome, placa, marca, modelo, ano, contato, email, cor FROM clientes WHERE {campo} = ?", (valor,))
        r = cursor.fetchone()
        if r:
            c_id = r[0]
            self.txt_nome.set(r[1]); self.txt_placa.set(r[2]); self.txt_marca.set(r[3])
            self.filtrar_modelos_por_marca(); self.txt_veiculo.set(r[4]); self.txt_ano.set(r[5])
            self.txt_contato.delete(0, "end"); self.txt_contato.insert(0, r[6])
            self.txt_email.delete(0, "end"); self.txt_email.insert(0, r[7] if r[7] else "")
            self.txt_cor.delete(0, "end"); self.txt_cor.insert(0, r[8])
            self.txt_orc_cliente_id.delete(0, "end"); self.txt_orc_cliente_id.insert(0, str(c_id))
            if hasattr(self, "txt_orc_cliente_nome"):
                self.txt_orc_cliente_nome.set(r[1])
            cursor.execute("SELECT COUNT(*) FROM orcamentos WHERE cliente_id = ?", (c_id,))
            ef = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM orcamentos WHERE cliente_id = ? AND status = 'Executado'", (c_id,))
            ex = cursor.fetchone()[0]
            cursor.execute("SELECT servico_solicitado, data_orcamento FROM orcamentos WHERE cliente_id = ? AND status = 'Executado' ORDER BY id DESC LIMIT 1", (c_id,))
            ul = cursor.fetchone()
            self.lbl_crm_efetuados.config(text=f"Orçamentos Efetuados: {ef}")
            self.lbl_crm_executados.config(text=f"Orçamentos Executados: {ex}")
            self.lbl_crm_ultimo.config(text=f"Último Serviço Executado: {ul[0]} ({ul[1]})" if ul else "Último Serviço Executado: Nenhum")
        conn.close()

    def salvar_fornecedor(self):
        if not self.txt_f_empresa.get(): return
        conn = conectar_banco(); cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO fornecedores (nome_empresa, contato_pessoa, telefone, email, endereco, dias_atendimento, horario_funcionamento, previsao_entrega)
            VALUES (?,?,?,?,?,?,?,?)
        ''', (self.txt_f_empresa.get(), self.txt_f_pessoa.get(), self.txt_f_telefone.get(), self.txt_f_email.get(),
              self.txt_f_endereco.get(), self.txt_f_dias.get(), self.txt_f_horario.get(), self.txt_f_previsao.get()))
        conn.commit(); conn.close()
        self.txt_f_empresa.delete(0, "end"); self.txt_f_pessoa.delete(0, "end"); self.txt_f_telefone.delete(0, "end")
        self.atualizar_todos_os_dados()

    def excluir_fornecedor(self):
        if not self.id_fornecedor_selecionado: return
        if messagebox.askyesno("⚠️ CONFIRMAR", "Excluir este fornecedor removerá permanentemente TODAS as peças dele!"):
            conn = conectar_banco(); cursor = conn.cursor()
            cursor.execute("DELETE FROM catalogo_pecas WHERE fornecedor_id = ?", (self.id_fornecedor_selecionado,))
            cursor.execute("DELETE FROM fornecedores WHERE id = ?", (self.id_fornecedor_selecionado,))
            conn.commit(); conn.close(); self.id_fornecedor_selecionado = None; self.atualizar_todos_os_dados()

    def ao_selecionar_grid_fornecedores(self, event):
        sel = self.tree_fornecedores.selection()
        if sel: self.id_fornecedor_selecionado = self.tree_fornecedores.item(sel[0], "values")[0]

    def ao_selecionar_grid_catalogo(self, event):
        sel = self.tree_catalogo.selection()
        if sel: self.id_peca_selecionada = self.tree_catalogo.item(sel[0], "values")[0]


if __name__ == "__main__":
    # ── 1. Tela de compatibilidade ────────────────────────────────────────
    splash = TelaCompatibilidade()
    pode_continuar = splash.executar()

    if not pode_continuar:
        sys.exit(0)

    try:
        from modulo_licenca_trial import verificar_trial_ou_sair
        verificar_trial_ou_sair()
    except ImportError:
        pass

    # ── 2. DPI awareness (Windows 8.1+) ──────────────────────────────────
    aplicar_config_dpi()

    # ── 3. Banco de dados ─────────────────────────────────────────────────
    criar_backup_banco()
    inicializar_banco()

    # ── 4. App principal ──────────────────────────────────────────────────
    root = tk.Tk()

    # Configurações de DPI/escala para Windows mais antigos
    if sys.platform == "win32":
        try:
            root.tk.call("tk", "scaling", _detectar_escala())
        except Exception:
            logging.exception("Falha ao aplicar escala da interface")

    app = AplicacaoOficina(root)
    root.mainloop()
