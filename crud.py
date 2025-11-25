# arquivo: berga_buerguers_with_login.py

# --- IMPORTAÇÕES ---
# Importa bibliotecas essenciais:
# os: para lidar com caminhos de arquivos e sistema operacional.
# sqlite3: para o banco de dados local.
# hashlib: para criptografar as senhas (segurança).
# tkinter: biblioteca padrão do Python para criar as janelas visuais.
# datetime/decimal: para lidar com datas e cálculos monetários precisos.
import os
import sqlite3
import hashlib
from tkinter import *
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

# --- CONFIGURAÇÃO DO BANCO DE DADOS ---
# Define onde o arquivo do banco de dados (bravus.db) será salvo.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bravus.db")

# --- FUNÇÕES DE BANCO DE DADOS (BACKEND) ---

# Função para conectar ao banco. Ativa 'foreign_keys' para garantir integridade entre tabelas.
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

# Função de Segurança: Transforma a senha digitada em um código hash (SHA256).
# Isso evita salvar a senha pura no banco de dados.
def _hash_pwd(pwd: str) -> str:
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()

# Inicializa o banco de dados. Cria as tabelas se elas não existirem.
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Tabela de Insumos: Guarda o estoque e custo médio de cada item.
    cur.execute('''
    CREATE TABLE IF NOT EXISTS insumos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE,
        categoria TEXT,
        unidade TEXT DEFAULT 'un',
        estoque_qtd REAL DEFAULT 0,
        custo_medio REAL DEFAULT 0
    )
    ''')

    # Tabela de Receitas: Produtos que são vendidos (ex: X-Burguer).
    cur.execute('''
    CREATE TABLE IF NOT EXISTS receitas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE,
        preco_venda REAL NOT NULL DEFAULT 0
    )
    ''')

    # Tabela de Vendas: Registro financeiro de cada venda.
    cur.execute('''
    CREATE TABLE IF NOT EXISTS vendas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receita_id INTEGER NOT NULL,
        quantidade INTEGER NOT NULL,
        preco_unit REAL NOT NULL,
        taxa_plataforma REAL NOT NULL DEFAULT 0,
        total_bruto REAL NOT NULL,
        custo_total REAL NOT NULL,
        lucro_liquido REAL NOT NULL,
        data TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (receita_id) REFERENCES receitas(id) ON DELETE CASCADE
    )
    ''')

    # Tabela de Compras: Histórico de entrada de produtos.
    cur.execute('''
    CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        quantidade REAL NOT NULL,
        preco REAL NOT NULL,
        data TEXT DEFAULT (datetime('now','localtime'))
    )
    ''')

    # Tabela de Usuários: Para o sistema de Login.
    cur.execute('''
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL
    )
    ''')

    # Cria um usuário padrão "admin" com senha "admin" se o banco estiver vazio.
    cur.execute("SELECT COUNT(*) FROM usuarios")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO usuarios (username, password_hash) VALUES (?, ?)",
                    ("admin", _hash_pwd("admin")))
    conn.commit()
    conn.close()

# Verifica se usuário e senha batem com o banco de dados.
def verify_user(username, password):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM usuarios WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False
    return row[0] == _hash_pwd(password)

# --- OPERAÇÕES CRUD (CREATE, READ, UPDATE, DELETE) ---

# Adiciona um novo insumo ao banco.
def add_produto(nome, categoria, unidade='un'):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO insumos (nome, categoria, unidade) VALUES (?, ?, ?)",
            (nome, categoria, unidade)
        )
        conn.commit()
        messagebox.showinfo("Sucesso", "Insumo adicionado com sucesso!")
    except sqlite3.IntegrityError:
        messagebox.showwarning("Atenção", "Este insumo já existe.")
    finally:
        conn.close()

# Atualiza dados de um insumo existente.
def update_insumo_db(insumo_id, nome, categoria, unidade):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE insumos SET nome=?, categoria=?, unidade=? WHERE id=?",
                    (nome, categoria, unidade, insumo_id))
        conn.commit()
        messagebox.showinfo("Sucesso", "Insumo atualizado!")
    except sqlite3.IntegrityError:
        messagebox.showwarning("Atenção", "Já existe um insumo com esse nome.")
    finally:
        conn.close()

# Remove um insumo.
def delete_insumo_db(insumo_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM insumos WHERE id = ?", (insumo_id,))
    conn.commit()
    conn.close()
    messagebox.showinfo("Sucesso", "Insumo removido.")

# Lista todos os insumos para exibir na tabela.
def listar_insumos():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM insumos ORDER BY nome")
    rows = cur.fetchall()
    conn.close()
    return rows

# IMPORTANTE: Registra compra e calcula o CUSTO MÉDIO PONDERADO.
# Se eu já tinha 10 itens a R$5 e compro 10 a R$10, o novo custo médio será R$7,50.
def registrar_compra_db(nome, quantidade, preco_unit):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO compras (nome, quantidade, preco) VALUES (?, ?, ?)",
            (nome, quantidade, float(preco_unit))
        )
        # Verifica se o insumo já existe para atualizar o estoque/custo
        cur.execute("SELECT id, estoque_qtd, custo_medio FROM insumos WHERE nome = ?", (nome,))
        row = cur.fetchone()
        if not row:
            # Se não existe, cria um novo
            cur.execute(
                "INSERT INTO insumos (nome, categoria, unidade, estoque_qtd, custo_medio) VALUES (?, ?, ?, ?, ?)",
                (nome, "", "un", float(quantidade), float(preco_unit))
            )
        else:
            # Se existe, calcula a média ponderada do custo e soma o estoque
            insumo_id, est_ant, custo_ant = row
            est_ant = float(est_ant or 0)
            custo_ant = float(custo_ant or 0)
            qtd = float(quantidade)
            custo_novo = float(preco_unit)
            novo_estoque = est_ant + qtd
            if novo_estoque > 0:
                novo_custo_medio = (est_ant * custo_ant + qtd * custo_novo) / novo_estoque
            else:
                novo_custo_medio = custo_novo
            cur.execute(
                "UPDATE insumos SET estoque_qtd = ?, custo_medio = ? WHERE id = ?",
                (novo_estoque, novo_custo_medio, insumo_id)
            )
        conn.commit()
        messagebox.showinfo("Sucesso", "Compra registrada e estoque atualizado!")
    finally:
        conn.close()

def listar_compras():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM compras ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return rows

def delete_compra_db(compra_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM compras WHERE id=?", (compra_id,))
    conn.commit()
    conn.close()
    messagebox.showinfo("Sucesso", "Compra removida.")

# --- CRUD RECEITAS ---
def add_receita(nome, preco_venda):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO receitas (nome, preco_venda) VALUES (?, ?)",
            (nome, float(preco_venda))
        )
        conn.commit()
        messagebox.showinfo("Sucesso", "Receita cadastrada!")
    except sqlite3.IntegrityError:
        messagebox.showwarning("Atenção", "Já existe uma receita com esse nome.")
    finally:
        conn.close()

def update_receita_db(receita_id, nome, preco_venda):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE receitas SET nome=?, preco_venda=? WHERE id=?",
                    (nome, float(preco_venda), receita_id))
        conn.commit()
        messagebox.showinfo("Sucesso", "Receita atualizada!")
    except sqlite3.IntegrityError:
        messagebox.showwarning("Atenção", "Já existe uma receita com esse nome.")
    finally:
        conn.close()

def delete_receita_db(receita_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM receitas WHERE id = ?", (receita_id,))
    conn.commit()
    conn.close()
    messagebox.showinfo("Sucesso", "Receita removida.")

def listar_receitas():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, nome, preco_venda FROM receitas ORDER BY nome")
    rows = cur.fetchall()
    conn.close()
    return rows

# --- LÓGICA DE VENDAS ---
# Calcula o lucro líquido subtraindo taxas da plataforma (iFood, etc).
def registrar_venda(receita_id, quantidade, preco_unit, taxa_plataforma):
    conn = get_conn()
    cur = conn.cursor()
    total_bruto = float(preco_unit) * int(quantidade)
    custo_total = 0.0 # Nota: O custo do insumo não está sendo descontado automaticamente aqui.
    desp_plataforma = total_bruto * float(taxa_plataforma)
    lucro_liquido = total_bruto - desp_plataforma - custo_total
    
    cur.execute('''
        INSERT INTO vendas (receita_id, quantidade, preco_unit, taxa_plataforma, total_bruto, custo_total, lucro_liquido, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (receita_id, int(quantidade), float(preco_unit), float(taxa_plataforma),
          total_bruto, custo_total, lucro_liquido, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    messagebox.showinfo("Sucesso", "Venda registrada com sucesso!")

def listar_vendas():
    conn = get_conn()
    cur = conn.cursor()
    # Faz um JOIN para pegar o nome da receita através do ID salvo na venda
    cur.execute("""
        SELECT v.id, r.nome, v.quantidade, v.preco_unit, v.taxa_plataforma,
               v.total_bruto, v.custo_total, v.lucro_liquido, v.data
        FROM vendas v
        JOIN receitas r ON r.id = v.receita_id
        ORDER BY v.id DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

def delete_venda_db(venda_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM vendas WHERE id=?", (venda_id,))
    conn.commit()
    conn.close()
    messagebox.showinfo("Sucesso", "Venda removida.")

# --- FUNÇÕES UTILITÁRIAS ---
# Formata números para o padrão brasileiro (R$ e vírgula)
def fmt_money(val):
    try:
        return f"R$ {float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"R$ {val}"

def fmt_qty(val):
    try:
        return f"{float(val):.3f}".replace(".", ",")
    except Exception:
        return f"{val}"

# --- INTERFACE GRÁFICA (TKINTER) ---
# Classe principal da aplicação
class BravusApp(Tk):
    def __init__(self):
        super().__init__()
        self.title("BRAV'US BURGUER - Sistema Restaurante")
        self.geometry("1040x680") # Tamanho da janela
        self.minsize(960, 600)

        # Criação das abas (Notebook)
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_insumos = ttk.Frame(nb)
        self.tab_compras = ttk.Frame(nb)
        self.tab_receitas = ttk.Frame(nb)
        self.tab_vendas = ttk.Frame(nb)
        self.tab_rel = ttk.Frame(nb)

        nb.add(self.tab_insumos, text="Insumos")
        nb.add(self.tab_compras, text="Compras")
        nb.add(self.tab_receitas, text="Receitas")
        nb.add(self.tab_vendas, text="Vendas")
        nb.add(self.tab_rel, text="Relatórios")

        # Constrói o conteúdo de cada aba
        self.build_insumos()
        self.build_compras()
        self.build_receitas()
        self.build_vendas()
        self.build_relatorios()

    # --- ABA DE INSUMOS ---
    def build_insumos(self):
        frm = self.tab_insumos
        top = ttk.LabelFrame(frm, text="Cadastro de Insumos")
        top.pack(fill="x", padx=8, pady=8)

        # Variáveis ligadas aos campos de texto
        self.in_nome = StringVar()
        self.in_categoria = StringVar()
        self.in_unidade = StringVar(value="un")

        # Layout dos campos (Grid) e botões
        ttk.Label(top, text="Nome:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(top, textvariable=self.in_nome, width=28).grid(row=0, column=1, padx=4, pady=4)

        ttk.Label(top, text="Categoria:").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        ttk.Entry(top, textvariable=self.in_categoria, width=20).grid(row=0, column=3, padx=4, pady=4)

        ttk.Label(top, text="Unidade:").grid(row=0, column=4, sticky="w", padx=4, pady=4)
        ttk.Combobox(top, textvariable=self.in_unidade, values=["un", "g", "kg", "ml", "l"], width=7, state="readonly").grid(row=0, column=5, padx=4, pady=4)

        ttk.Button(top, text="Salvar", command=self.salvar_insumo).grid(row=0, column=6, padx=8)

        # Tabela (Treeview) para mostrar os dados
        mid = ttk.LabelFrame(frm, text="Estoque Atual")
        mid.pack(fill="both", expand=True, padx=8, pady=8)

        cols = ("id", "nome", "categoria", "unidade", "estoque", "custo_medio")
        self.tree_insumos = ttk.Treeview(mid, columns=cols, show="headings", selectmode="browse")
        # Configuração das colunas e cabeçalhos
        for c, txt, w in [("id", "ID", 60), ("nome", "Nome", 220), ("categoria", "Categoria", 150),
                          ("unidade", "Un", 60), ("estoque", "Estoque", 120), ("custo_medio", "Custo Médio", 120)]:
            self.tree_insumos.heading(c, text=txt)
            self.tree_insumos.column(c, width=w, anchor="w")
        self.tree_insumos.pack(fill="both", expand=True, side="left")
        
        # Barra de rolagem
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree_insumos.yview)
        self.tree_insumos.configure(yscroll=sb.set)
        sb.pack(side="right", fill="y")

        # Botões de ação inferiores
        btns = ttk.Frame(frm)
        btns.pack(fill="x", padx=8, pady=4)
        ttk.Button(btns, text="Recarregar", command=self.load_insumos).pack(side="left")
        ttk.Button(btns, text="Editar selecionado", command=self.edit_insumo_dialog).pack(side="left", padx=6)
        ttk.Button(btns, text="Excluir selecionado", command=self.delete_insumo_selected).pack(side="left", padx=6)

        self.load_insumos()

    def salvar_insumo(self):
        nome = self.in_nome.get().strip()
        categoria = self.in_categoria.get().strip()
        unidade = self.in_unidade.get().strip()
        if not nome:
            messagebox.showwarning("Aviso", "Informe o nome do insumo.")
            return
        add_produto(nome, categoria, unidade)
        self.in_nome.set("")
        self.in_categoria.set("")
        self.in_unidade.set("un")
        self.load_insumos()

    # Preenche a tabela com dados do banco
    def load_insumos(self):
        for i in self.tree_insumos.get_children():
            self.tree_insumos.delete(i)
        for r in listar_insumos():
            self.tree_insumos.insert("", "end", values=(r[0], r[1], r[2], r[3], fmt_qty(r[4]), fmt_money(r[5])))

    # Abre uma janela pop-up (Toplevel) para editar
    def edit_insumo_dialog(self):
        sel = self.tree_insumos.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione um insumo para editar.")
            return
        iid = sel[0]
        vals = self.tree_insumos.item(iid, "values")
        insumo_id = int(vals[0])

        top = Toplevel(self)
        top.title("Editar Insumo")
        Label(top, text="Nome:").grid(row=0, column=0, padx=6, pady=6)
        e_nome = Entry(top); e_nome.grid(row=0, column=1, padx=6, pady=6); e_nome.insert(0, vals[1])
        Label(top, text="Categoria:").grid(row=1, column=0, padx=6, pady=6)
        e_cat = Entry(top); e_cat.grid(row=1, column=1, padx=6, pady=6); e_cat.insert(0, vals[2])
        Label(top, text="Unidade:").grid(row=2, column=0, padx=6, pady=6)
        e_un = Entry(top); e_un.grid(row=2, column=1, padx=6, pady=6); e_un.insert(0, vals[3])

        def _save():
            nome_n = e_nome.get().strip()
            cat_n = e_cat.get().strip()
            un_n = e_un.get().strip() or "un"
            if not nome_n:
                messagebox.showwarning("Aviso", "Nome obrigatório.")
                return
            update_insumo_db(insumo_id, nome_n, cat_n, un_n)
            top.destroy()
            self.load_insumos()

        ttk.Button(top, text="Salvar", command=_save).grid(row=3, column=0, columnspan=2, pady=8)

    def delete_insumo_selected(self):
        sel = self.tree_insumos.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione um insumo para excluir.")
            return
        iid = sel[0]
        vals = self.tree_insumos.item(iid, "values")
        insumo_id = int(vals[0])
        if messagebox.askyesno("Confirmar", f"Excluir insumo '{vals[1]}'?"):
            delete_insumo_db(insumo_id)
            self.load_insumos()

    # --- ABA DE COMPRAS ---
    def build_compras(self):
        frm = self.tab_compras
        top = ttk.LabelFrame(frm, text="Cadastro de Compras")
        top.pack(fill="x", padx=8, pady=8)

        self.comp_nome = StringVar()
        self.comp_qtd = StringVar()
        self.comp_preco = StringVar()

        ttk.Label(top, text="Produto:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(top, textvariable=self.comp_nome, width=28).grid(row=0, column=1, padx=4, pady=4)

        ttk.Label(top, text="Quantidade:").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        ttk.Entry(top, textvariable=self.comp_qtd, width=10).grid(row=0, column=3, padx=4, pady=4)

        ttk.Label(top, text="Preço Unit.:").grid(row=0, column=4, sticky="w", padx=4, pady=4)
        ttk.Entry(top, textvariable=self.comp_preco, width=12).grid(row=0, column=5, padx=4, pady=4)

        ttk.Button(top, text="Registrar Compra", command=self._registrar_compra).grid(row=0, column=6, padx=8)

        mid = ttk.LabelFrame(frm, text="Compras Recentes")
        mid.pack(fill="both", expand=True, padx=8, pady=8)

        cols = ("id", "produto", "quantidade", "preco", "data")
        self.tree_compras = ttk.Treeview(mid, columns=cols, show="headings")
        for c, txt, w in [("id", "ID", 60), ("produto", "Produto", 220), ("quantidade", "Qtd", 100),
                          ("preco", "Preço Unit.", 120), ("data", "Data", 160)]:
            self.tree_compras.heading(c, text=txt)
            self.tree_compras.column(c, width=w, anchor="w")
        self.tree_compras.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree_compras.yview)
        self.tree_compras.configure(yscroll=sb.set)
        sb.pack(side="right", fill="y")

        btns = ttk.Frame(frm)
        btns.pack(fill="x", padx=8, pady=4)
        ttk.Button(btns, text="Recarregar", command=self.load_compras).pack(side="left")
        ttk.Button(btns, text="Excluir selecionado", command=self.delete_compra_selected).pack(side="left", padx=6)

        self.load_compras()

    def _registrar_compra(self):
        nome = self.comp_nome.get().strip()
        try:
            quantidade = float(self.comp_qtd.get().replace(",", "."))
            preco = Decimal(self.comp_preco.get().replace(",", "."))
        except (InvalidOperation, ValueError):
            messagebox.showwarning("Aviso", "Quantidade e preço devem ser numéricos.")
            return

        if not nome or quantidade <= 0 or preco <= 0:
            messagebox.showwarning("Aviso", "Preencha todos os campos corretamente.")
            return

        registrar_compra_db(nome, quantidade, preco)
        self.comp_nome.set("")
        self.comp_qtd.set("")
        self.comp_preco.set("")
        self.load_compras()
        self.load_insumos()  # Atualiza a tabela de insumos para refletir novo estoque

    def load_compras(self):
        for i in self.tree_compras.get_children():
            self.tree_compras.delete(i)
        for r in listar_compras():
            self.tree_compras.insert("", "end", values=(r[0], r[1], fmt_qty(r[2]), fmt_money(r[3]), r[4]))

    def delete_compra_selected(self):
        sel = self.tree_compras.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione uma compra para excluir.")
            return
        iid = sel[0]
        vals = self.tree_compras.item(iid, "values")
        compra_id = int(vals[0])
        if messagebox.askyesno("Confirmar", f"Excluir compra ID {compra_id}?"):
            delete_compra_db(compra_id)
            self.load_compras()
            self.load_insumos()

    # --- ABA DE RECEITAS ---
    def build_receitas(self):
        frm = self.tab_receitas

        top = ttk.LabelFrame(frm, text="Cadastro de Receitas")
        top.pack(fill="x", padx=8, pady=8)

        self.rec_nome = StringVar()
        self.rec_preco = StringVar()

        ttk.Label(top, text="Nome:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(top, textvariable=self.rec_nome, width=28).grid(row=0, column=1, padx=4, pady=4)

        ttk.Label(top, text="Preço de venda:").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        ttk.Entry(top, textvariable=self.rec_preco, width=12).grid(row=0, column=3, padx=4, pady=4)

        ttk.Button(top, text="Salvar", command=self._salvar_receita).grid(row=0, column=4, padx=8)

        mid = ttk.LabelFrame(frm, text="Receitas Cadastradas")
        mid.pack(fill="both", expand=True, padx=8, pady=8)

        cols = ("id", "nome", "preco")
        self.tree_receitas = ttk.Treeview(mid, columns=cols, show="headings")
        for c, txt, w in [("id", "ID", 60), ("nome", "Nome", 280), ("preco", "Preço Venda", 150)]:
            self.tree_receitas.heading(c, text=txt)
            self.tree_receitas.column(c, width=w, anchor="w")
        self.tree_receitas.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree_receitas.yview)
        self.tree_receitas.configure(yscroll=sb.set)
        sb.pack(side="right", fill="y")

        btns = ttk.Frame(frm)
        btns.pack(fill="x", padx=8, pady=4)
        ttk.Button(btns, text="Recarregar", command=self.load_receitas).pack(side="left")
        ttk.Button(btns, text="Editar selecionado", command=self.edit_receita_dialog).pack(side="left", padx=6)
        ttk.Button(btns, text="Excluir selecionado", command=self.delete_receita_selected).pack(side="left", padx=6)

        self.load_receitas()

    def _salvar_receita(self):
        nome = self.rec_nome.get().strip()
        try:
            preco = float(self.rec_preco.get().replace(",", "."))
        except ValueError:
            messagebox.showwarning("Aviso", "Preço inválido.")
            return
        if not nome or preco <= 0:
            messagebox.showwarning("Aviso", "Preencha o nome e um preço válido.")
            return
        add_receita(nome, preco)
        self.rec_nome.set("")
        self.rec_preco.set("")
        self.load_receitas()
        self._reload_receitas_combo()  # Atualiza lista suspensa na aba vendas

    def load_receitas(self):
        for i in self.tree_receitas.get_children():
            self.tree_receitas.delete(i)
        for r in listar_receitas():
            self.tree_receitas.insert("", "end", values=(r[0], r[1], fmt_money(r[2])))

    def edit_receita_dialog(self):
        sel = self.tree_receitas.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione uma receita para editar.")
            return
        iid = sel[0]
        vals = self.tree_receitas.item(iid, "values")
        receita_id = int(vals[0])

        top = Toplevel(self)
        top.title("Editar Receita")
        Label(top, text="Nome:").grid(row=0, column=0, padx=6, pady=6)
        e_nome = Entry(top); e_nome.grid(row=0, column=1, padx=6, pady=6); e_nome.insert(0, vals[1])
        Label(top, text="Preço:").grid(row=1, column=0, padx=6, pady=6)
        e_pre = Entry(top); e_pre.grid(row=1, column=1, padx=6, pady=6); e_pre.insert(0, vals[2].replace("R$ ", "").replace(".", "").replace(",", "."))

        def _save():
            nome_n = e_nome.get().strip()
            try:
                preco_n = float(e_pre.get().replace(",", "."))
            except ValueError:
                messagebox.showwarning("Aviso", "Preço inválido.")
                return
            if not nome_n or preco_n <= 0:
                messagebox.showwarning("Aviso", "Nome e preço válidos necessários.")
                return
            update_receita_db(receita_id, nome_n, preco_n)
            top.destroy()
            self.load_receitas()
            self._reload_receitas_combo()

        ttk.Button(top, text="Salvar", command=_save).grid(row=2, column=0, columnspan=2, pady=8)

    def delete_receita_selected(self):
        sel = self.tree_receitas.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione uma receita para excluir.")
            return
        iid = sel[0]
        vals = self.tree_receitas.item(iid, "values")
        receita_id = int(vals[0])
        if messagebox.askyesno("Confirmar", f"Excluir receita '{vals[1]}'?"):
            delete_receita_db(receita_id)
            self.load_receitas()
            self._reload_receitas_combo()

    # --- ABA DE VENDAS ---
    def build_vendas(self):
        frm = self.tab_vendas

        top = ttk.LabelFrame(frm, text="Registrar Venda")
        top.pack(fill="x", padx=8, pady=8)

        self.vnd_receita = StringVar()
        self.vnd_quantidade = StringVar(value="1")
        self.vnd_preco = StringVar()
        self.vnd_taxa = StringVar(value="0")

        ttk.Label(top, text="Receita:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        # Combobox (lista suspensa) para selecionar receitas
        self.combo_receitas = ttk.Combobox(top, textvariable=self.vnd_receita, width=35, state="readonly")
        self.combo_receitas.grid(row=0, column=1, padx=4, pady=4, sticky="w")
        self.combo_receitas.bind("<<ComboboxSelected>>", self._on_receita_selected)

        ttk.Label(top, text="Quantidade:").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        ttk.Entry(top, textvariable=self.vnd_quantidade, width=8).grid(row=0, column=3, padx=4, pady=4)

        ttk.Label(top, text="Preço unit.:").grid(row=0, column=4, sticky="w", padx=4, pady=4)
        ttk.Entry(top, textvariable=self.vnd_preco, width=12).grid(row=0, column=5, padx=4, pady=4)

        ttk.Label(top, text="Taxa plataforma:").grid(row=0, column=6, sticky="w", padx=4, pady=4)
        ttk.Entry(top, textvariable=self.vnd_taxa, width=8).grid(row=0, column=7, padx=4, pady=4)
        ttk.Label(top, text="% ou fração").grid(row=0, column=8, sticky="w")

        ttk.Button(top, text="Registrar", command=self._registrar_venda).grid(row=0, column=9, padx=8)

        mid = ttk.LabelFrame(frm, text="Vendas Recentes")
        mid.pack(fill="both", expand=True, padx=8, pady=8)

        cols = ("id", "receita", "qtd", "preco_unit", "taxa", "bruto", "custo", "lucro", "data")
        self.tree_vendas = ttk.Treeview(mid, columns=cols, show="headings")
        headers = [("id", "ID", 60), ("receita", "Receita", 200), ("qtd", "Qtd", 60),
                   ("preco_unit", "Preço Unit.", 110), ("taxa", "Taxa", 80),
                   ("bruto", "Total Bruto", 110), ("custo", "Custo", 100),
                   ("lucro", "Lucro Líquido", 120), ("data", "Data", 160)]
        for c, txt, w in headers:
            self.tree_vendas.heading(c, text=txt)
            self.tree_vendas.column(c, width=w, anchor="w")
        self.tree_vendas.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree_vendas.yview)
        self.tree_vendas.configure(yscroll=sb.set)
        sb.pack(side="right", fill="y")

        btns = ttk.Frame(frm)
        btns.pack(fill="x", padx=8, pady=4)
        ttk.Button(btns, text="Recarregar", command=self.load_vendas).pack(side="left")
        ttk.Button(btns, text="Excluir selecionado", command=self.delete_venda_selected).pack(side="left", padx=6)

        self._reload_receitas_combo()
        self.load_vendas()

    # Atualiza o Combobox com as receitas cadastradas
    def _reload_receitas_combo(self):
        recs = listar_receitas()
        nomes = [f"{r[0]} - {r[1]}" for r in recs]
        self.combo_receitas["values"] = nomes
        if nomes and not self.vnd_receita.get():
            self.combo_receitas.current(0)
            self._on_receita_selected()

    # Preenche o preço automaticamente ao selecionar uma receita
    def _on_receita_selected(self, *_):
        try:
            sel = self.vnd_receita.get()
            if not sel:
                return
            rec_id = int(sel.split(" - ")[0])
            for r in listar_receitas():
                if r[0] == rec_id:
                    self.vnd_preco.set(str(r[2]).replace(".", ","))
                    break
        except Exception:
            pass

    def _registrar_venda(self):
        sel = self.vnd_receita.get().strip()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione uma receita.")
            return
        try:
            receita_id = int(sel.split(" - ")[0])
            quantidade = int(self.vnd_quantidade.get())
            preco_unit = float(self.vnd_preco.get().replace(",", "."))
            taxa_in = self.vnd_taxa.get().replace("%", "").strip()
            taxa = float(taxa_in.replace(",", "."))
            if taxa > 1:
                taxa = taxa / 100.0
            if quantidade <= 0 or preco_unit <= 0 or taxa < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Aviso", "Verifique quantidade, preço e taxa.")
            return

        registrar_venda(receita_id, quantidade, preco_unit, taxa)
        self.load_vendas()
        self.load_relatorios_data() # Atualiza os relatórios instantaneamente

    def load_vendas(self):
        for i in self.tree_vendas.get_children():
            self.tree_vendas.delete(i)
        for v in listar_vendas():
            taxa_pct = f"{round(v[4]*100, 2)}%"
            self.tree_vendas.insert("", "end", values=(
                v[0], v[1], v[2], fmt_money(v[3]), taxa_pct, fmt_money(v[5]),
                fmt_money(v[6]), fmt_money(v[7]), v[8]
            ))

    def delete_venda_selected(self):
        sel = self.tree_vendas.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione uma venda para excluir.")
            return
        iid = sel[0]
        vals = self.tree_vendas.item(iid, "values")
        venda_id = int(vals[0])
        if messagebox.askyesno("Confirmar", f"Excluir venda ID {venda_id}?"):
            delete_venda_db(venda_id)
            self.load_vendas()
            self.load_relatorios_data()

    # --- ABA DE RELATÓRIOS ---
    def build_relatorios(self):
        frm = self.tab_rel
        self.cards = ttk.Frame(frm)
        self.cards.pack(fill="x", padx=8, pady=8)

        self.var_card_hoje = StringVar()
        self.var_card_7d = StringVar()
        self.var_card_30d = StringVar()
        self.var_card_all = StringVar()

        def card(parent, title, var):
            box = ttk.LabelFrame(parent, text=title)
            box.pack(side="left", expand=True, fill="x", padx=6)
            ttk.Label(box, textvariable=var, font=("TkDefaultFont", 12, "bold")).pack(padx=8, pady=8)

        card(self.cards, "Hoje", self.var_card_hoje)
        card(self.cards, "Últimos 7 dias", self.var_card_7d)
        card(self.cards, "Últimos 30 dias", self.var_card_30d)
        card(self.cards, "Geral", self.var_card_all)

        mid = ttk.LabelFrame(frm, text="Vendas (Geral)")
        mid.pack(fill="both", expand=True, padx=8, pady=8)

        cols = ("periodo", "qtd_vendas", "qtd_itens", "faturamento", "lucro")
        self.tree_rel = ttk.Treeview(mid, columns=cols, show="headings")
        for c, txt, w in [("periodo", "Período", 160), ("qtd_vendas", "Vendas", 90),
                          ("qtd_itens", "Itens", 90), ("faturamento", "Faturamento", 140),
                          ("lucro", "Lucro Líquido", 140)]:
            self.tree_rel.heading(c, text=txt)
            self.tree_rel.column(c, width=w, anchor="w")
        self.tree_rel.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree_rel.yview)
        self.tree_rel.configure(yscroll=sb.set)
        sb.pack(side="right", fill="y")

        self.load_relatorios_data()

    # Agrega dados do banco por data para gerar os relatórios
    def _agg_vendas(self, dt_ini=None, dt_fim=None):
        conn = get_conn()
        cur = conn.cursor()
        sql = "SELECT COUNT(*), SUM(quantidade), SUM(total_bruto), SUM(lucro_liquido) FROM vendas WHERE 1=1"
        params = []
        if dt_ini:
            sql += " AND datetime(data) >= datetime(?)"
            params.append(dt_ini)
        if dt_fim:
            sql += " AND datetime(data) < datetime(?)"
            params.append(dt_fim)
        cur.execute(sql, params)
        row = cur.fetchone()
        conn.close()
        if not row or row[0] is None:
            return 0, 0, 0.0, 0.0
        return row[0] or 0, row[1] or 0, float(row[2] or 0.0), float(row[3] or 0.0)

    def load_relatorios_data(self):
        hoje_ini = datetime.now().strftime("%Y-%m-%d 00:00:00")
        amanha_ini = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
        d7_ini = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d 00:00:00")
        d30_ini = (datetime.now() - timedelta(days=29)).strftime("%Y-%m-%d 00:00:00")

        c_hoje = self._agg_vendas(hoje_ini, amanha_ini)
        c_7 = self._agg_vendas(d7_ini, amanha_ini)
        c_30 = self._agg_vendas(d30_ini, amanha_ini)
        c_all = self._agg_vendas()

        self.var_card_hoje.set(f"Vendas: {c_hoje[0]}  |  Itens: {c_hoje[1]}  |  Fat: {fmt_money(c_hoje[2])}  |  Lucro: {fmt_money(c_hoje[3])}")
        self.var_card_7d.set(  f"Vendas: {c_7[0]}    |  Itens: {c_7[1]}    |  Fat: {fmt_money(c_7[2])}    |  Lucro: {fmt_money(c_7[3])}")
        self.var_card_30d.set( f"Vendas: {c_30[0]}   |  Itens: {c_30[1]}   |  Fat: {fmt_money(c_30[2])}   |  Lucro: {fmt_money(c_30[3])}")
        self.var_card_all.set( f"Vendas: {c_all[0]}  |  Itens: {c_all[1]}  |  Fat: {fmt_money(c_all[2])}  |  Lucro: {fmt_money(c_all[3])}")

        for i in self.tree_rel.get_children():
            self.tree_rel.delete(i)
        self.tree_rel.insert("", "end", values=("Hoje", c_hoje[0], c_hoje[1], fmt_money(c_hoje[2]), fmt_money(c_hoje[3])))
        self.tree_rel.insert("", "end", values=("Últimos 7 dias", c_7[0], c_7[1], fmt_money(c_7[2]), fmt_money(c_7[3])))
        self.tree_rel.insert("", "end", values=("Últimos 30 dias", c_30[0], c_30[1], fmt_money(c_30[2]), fmt_money(c_30[3])))
        self.tree_rel.insert("", "end", values=("Geral", c_all[0], c_all[1], fmt_money(c_all[2]), fmt_money(c_all[3])))

# --- TELA DE LOGIN ---
class LoginWindow(Tk):
    def __init__(self):
        super().__init__()
        self.title("Login - Brav'us")
        self.geometry("320x160")
        self.resizable(False, False)

        self.user_var = StringVar()
        self.pwd_var = StringVar()

        frm = ttk.Frame(self, padding=12)
        frm.pack(expand=True, fill="both")

        ttk.Label(frm, text="Usuário:").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(frm, textvariable=self.user_var).grid(row=0, column=1, pady=6)

        ttk.Label(frm, text="Senha:").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(frm, textvariable=self.pwd_var, show="*").grid(row=1, column=1, pady=6)

        ttk.Button(frm, text="Entrar", command=self.try_login).grid(row=2, column=0, columnspan=2, pady=10)

    # Verifica o login. Se correto, fecha essa janela e abre a principal.
    def try_login(self):
        u = self.user_var.get().strip()
        p = self.pwd_var.get()
        if not u or not p:
            messagebox.showwarning("Aviso", "Preencha usuário e senha.")
            return
        if verify_user(u, p):
            self.destroy() # Fecha a janela de login
            app = BravusApp() # Cria a janela principal
            app.mainloop() # Inicia o loop da aplicação
        else:
            messagebox.showerror("Erro", "Usuário ou senha inválidos.")

# --- PONTO DE PARTIDA ---
if __name__ == "__main__":
    init_db() # Garante que o banco existe
    LoginWindow().mainloop() # Abre a tela de login