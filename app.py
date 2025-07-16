from flask import Flask, render_template
import pandas as pd
from datetime import datetime
import os
import requests
from io import StringIO
import unicodedata

app = Flask(__name__)

# Configurações
GOOGLE_SHEETS_URL = "https://docs.google.com/spreadsheets/d/1-w7GAzxvB-Ugb7cRzTA2jodaJtSrrQpf/export?format=csv&gid=442377092"
LOCAL_BACKUP = "provas_backup.csv"

def normalize_text(text):
    """Normaliza texto para lidar com problemas de codificação"""
    if isinstance(text, str):
        return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    return text

def download_sheets_data():
    try:
        # Baixa os dados do Google Sheets
        response = requests.get(GOOGLE_SHEETS_URL)
        response.encoding = 'utf-8'  # Força a codificação UTF-8
        response.raise_for_status()
        
        # Salva um backup local
        #with open(LOCAL_BACKUP, 'w', encoding='utf-8') as f:
        #    f.write(response.text)
            
        # Lê o CSV garantindo a codificação correta
        df = pd.read_csv(StringIO(response.text), encoding='utf-8')
        
        # Normaliza os textos
        text_columns = ['PROVA', 'RESPONSAVEL', 'CLASSIFICACAO']
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].apply(normalize_text)
        
        return df
    
    except Exception as e:
        print(f"Erro ao baixar do Google Sheets: {e}")
        if os.path.exists(LOCAL_BACKUP):
            print("Usando backup local...")
            try:
                df = pd.read_csv(LOCAL_BACKUP, encoding='utf-8')
                text_columns = ['PROVA', 'RESPONSAVEL', 'CLASSIFICACAO']
                for col in text_columns:
                    if col in df.columns:
                        df[col] = df[col].apply(normalize_text)
                return df
            except UnicodeDecodeError:
                try:
                    df = pd.read_csv(LOCAL_BACKUP, encoding='latin-1')
                    text_columns = ['PROVA', 'RESPONSAVEL', 'CLASSIFICACAO']
                    for col in text_columns:
                        if col in df.columns:
                            df[col] = df[col].apply(normalize_text)
                    return df
                except Exception as e:
                    print(f"Erro ao ler backup local: {e}")
                    raise
        raise

@app.after_request
def add_charset(response):
    """Garante que todas as respostas tenham charset UTF-8"""
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    return response

def get_provas_data():
    try:
        # Lê os dados
        df = download_sheets_data()
        
        # Verifica e padroniza os nomes das colunas
        df.columns = df.columns.str.strip().str.upper()
        
        # Mapeamento de colunas alternativas
        column_mapping = {
            'DATA': ['DATA', 'DT_PROVA', 'DATAS'],
            'PROVA': ['PROVA', 'NOME', 'EVENTO'],
            'CONCLUSAO': ['CONCLUSAO', 'STATUS', 'FEITO?', 'REALIZADO'],
            'RESPONSAVEL': ['RESPONSÁVEL', 'RESPONSAVEL', 'RESP', 'PROFESSOR'],
            'CLASSIFICACAO': ['CLASSIFICACAO', 'CLASSIFICAÇÃO', 'CLASSIFIC', 'MEDALHA', 'PODIO']
        }
        
        # Tenta encontrar as colunas correspondentes
        found_columns = {}
        for standard_col, alternatives in column_mapping.items():
            for alt in alternatives:
                if alt in df.columns:
                    found_columns[standard_col] = alt
                    break
            else:
                if standard_col != 'CLASSIFICACAO':  # CLASSIFICACAO é opcional
                    return {'error': f'Coluna {standard_col} não encontrada. Colunas disponíveis: {list(df.columns)}'}, None
        
        # Renomeia as colunas para os nomes padrão
        df = df.rename(columns=found_columns)
        
        # Se não encontrou CLASSIFICACAO, cria coluna vazia
        if 'CLASSIFICACAO' not in df.columns:
            df['CLASSIFICACAO'] = ''
        
        # Filtra provas não concluídas (considerando variações)
        concluido_values = df['CONCLUSAO'].str.strip().str.upper()
        df = df[~concluido_values.isin(['SIM', 'S', 'CONCLUSAO', 'CONCLUIDO', 'FEITO', 'OK'])]
        
        # Converte a coluna de data para datetime
        df['DATA'] = pd.to_datetime(df['DATA'], dayfirst=True, errors='coerce')
        
        # Remove linhas com datas inválidas
        df = df.dropna(subset=['DATA'])
        
        # Ordena por data
        df = df.sort_values(by='DATA')
        
        # Separa provas em andamento e próximas
        now = datetime.now()
        provas_agora = df[(df['DATA'] <= now)]
        proximas_provas = df[(df['DATA'] > now)]
        
        return None, {
            'provas_agora': provas_agora.to_dict('records'),
            'proximas_provas': proximas_provas.to_dict('records'),
            'atualizado_em': now.strftime('%d/%m/%Y %H:%M:%S')
        }
    
    except Exception as e:
        return {'error': str(e)}, None

@app.route('/')
def kanban_provas():
    error, data = get_provas_data()
    
    if error:
        print("ERRO:", error)
        return render_template('error.html', error=error)
    
    return render_template('kanban.html', 
                         provas_agora=data['provas_agora'],
                         proximas_provas=data['proximas_provas'],
                         atualizado_em=data['atualizado_em'])

# Nada — Remova totalmente o `if __name__ == '__main__':` se usar Gunicorn
# O Gunicorn vai importar e usar a variável 'app' automaticamente