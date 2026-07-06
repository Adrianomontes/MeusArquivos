import sqlite3
import tkinter as tk
from tkinter import messagebox
import os

# Aponta cirurgicamente para o banco de dados oficial da produção do Adriano
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, 'sistema_operacional.db')

def salvar_flags():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    for nome_template, var_checkbox in flags_widgets.items():
        estado_ativo = var_checkbox.get()
        cursor.execute("""
            UPDATE templates_monitor 
            SET ativo = ? 
            WHERE nome_template = ?
        """, (estado_ativo, nome_template))
        
    conn.commit()
    conn.close()
    messagebox.showinfo("Sucesso", "Painel da TV Atualizado!\nO monitor localhost já vai se adaptar na próxima rotação.")

root = tk.Tk()
root.title("Orquestrador de Telas - Monitor da Portaria")
root.geometry("680x420")
root.configure(bg="#f1f5f9")

frame_topo = tk.Frame(root, bg="#0f172a", height=60)
frame_topo.pack(fill="x", side="top")
tk.Label(frame_topo, text="🖥️ GERENCIADOR DE RENDERIZAÇÃO DA TV", font=("Arial", 11, "bold"), bg="#0f172a", fg="white").pack(side="left", padx=15, pady=18)

frame_grid = tk.LabelFrame(root, text=" Selecione os painéis ativos para passar na TV ", bg="white", font=("Arial", 10, "bold"), pady=10)
frame_grid.pack(fill="both", expand=True, padx=15, pady=15)

tk.Label(frame_grid, text="EXIBIR?", font=("Arial", 9, "bold"), bg="#cbd5e1", relief="groove", width=12).grid(row=0, column=0, padx=10, pady=5)
tk.Label(frame_grid, text="NOME DO TEMPLATE / TELA", font=("Arial", 9, "bold"), bg="#cbd5e1", relief="groove", width=30, anchor="w", padx=5).grid(row=0, column=1, padx=5, pady=5)
tk.Label(frame_grid, text="CONTEÚDO DO MONITOR", font=("Arial", 9, "bold"), bg="#cbd5e1", relief="groove", width=38, anchor="w", padx=5).grid(row=0, column=2, padx=5, pady=5)

# Carrega os dados reais do banco de dados oficial
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()
cursor.execute("SELECT nome_template, descricao, ativo FROM templates_monitor")
templates_banco = cursor.fetchall()
conn.close()

flags_widgets = {}
for idx, (nome, descricao, ativo) in enumerate(templates_banco):
    row_num = idx + 1
    var_check = tk.IntVar(value=ativo)
    flags_widgets[nome] = var_check
    
    chk = tk.Checkbutton(frame_grid, variable=var_check, bg="white", activebackground="white", cursor="hand2")
    chk.grid(row=row_num, column=0, pady=6)
    
    lbl_nome = tk.Label(frame_grid, text=nome, font=("Arial", 9, "bold"), bg="white", fg="#1e293b", anchor="w")
    lbl_nome.grid(row=row_num, column=1, sticky="w", padx=5)
    
    lbl_desc = tk.Label(frame_grid, text=descricao, font=("Arial", 9), bg="white", fg="#64748b", anchor="w")
    lbl_desc.grid(row=row_num, column=2, sticky="w", padx=5)

btn_atualizar = tk.Button(
    root, 
    text="🔄 Aplicar Configuração no Monitor Localhost", 
    command=salvar_flags,
    bg="#10b981", fg="white", font=("Arial", 11, "bold"), height=2, cursor="hand2"
)
btn_atualizar.pack(fill="x", padx=15, pady=10)

root.mainloop()