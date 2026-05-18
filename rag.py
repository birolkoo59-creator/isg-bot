import sqlite3
import re
import os

def init_rag_db():
    conn = sqlite3.connect("isg_bot.db")
    c = conn.cursor()
    c.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS law_chunks
        USING fts5(source, content, tokenize='unicode61')
    """)
    conn.commit()
    conn.close()

def extract_text_from_pdf(pdf_path):
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        print(f"PDF okuma hatası {pdf_path}: {e}")
        return ""

def chunk_text(text, chunk_size=800, overlap=100):
    text = re.sub(r'\s+', ' ', text).strip()
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start += chunk_size - overlap
    return chunks

def load_pdfs_to_db():
    conn = sqlite3.connect("isg_bot.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM law_chunks")
    count = c.fetchone()[0]
    conn.close()

    if count > 0:
        return

    pdf_files = [f for f in os.listdir(".") if f.lower().endswith(".pdf")]

    if not pdf_files:
        print("Hiç PDF dosyası bulunamadı.")
        return

    conn = sqlite3.connect("isg_bot.db")
    c = conn.cursor()

    for filename in pdf_files:
        print(f"{filename} yükleniyor...")
        text = extract_text_from_pdf(filename)
        if not text:
            print(f"{filename} okunamadı, atlanıyor.")
            continue
        source = os.path.splitext(filename)[0]
        chunks = chunk_text(text)
        for chunk in chunks:
            c.execute("INSERT INTO law_chunks (source, content) VALUES (?, ?)", (source, chunk))
        print(f"{filename}: {len(chunks)} parça yüklendi.")

    conn.commit()
    conn.close()
    print("Tüm dosyalar veritabanına yüklendi.")

def search_laws(query, top_k=4):
    try:
        conn = sqlite3.connect("isg_bot.db")
        c = conn.cursor()
        safe_query = re.sub(r'[^\w\s]', ' ', query)
        c.execute("""
            SELECT source, content FROM law_chunks
            WHERE law_chunks MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (safe_query, top_k))
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception:
        return []

def build_context(query):
    results = search_laws(query)
    if not results:
        return ""
    parts = []
    for source, content in results:
        parts.append(f"[{source} Sayılı Kanun]\n{content}")
    return "\n\n---\n\n".join(parts)
