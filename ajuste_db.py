import sqlite3

conn = sqlite3.connect("sistema_operacional.db")  # coloque o nome correto do seu DB
cursor = conn.cursor()

cursor.execute("ALTER TABLE entregas_efetuadas ADD COLUMN recebedor TEXT;")

conn.commit()
conn.close()

print("Coluna 'recebedor' adicionada com sucesso!")
