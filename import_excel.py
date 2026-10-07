"""Importador independente: python import_excel.py arquivo.xlsx --station principal."""
import argparse
from dashboard import create_app
from dashboard.importer import import_excel

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Importa XLSX para PostgreSQL ou SQLite via DATABASE_URL.')
    parser.add_argument('filename')
    parser.add_argument('--station', default='principal')
    parser.add_argument('--sheet')
    args = parser.parse_args()
    app = create_app()
    try:
        result = import_excel(app.extensions['db_engine'], args.filename, args.station, args.sheet, lambda n: print(f'Processadas: {n}') if n % 10000 == 0 else None)
    except Exception as exc:
        # Não exibe credenciais ou SQL do driver no terminal.
        parser.exit(1, f'Importação cancelada ({type(exc).__name__}). Confira o arquivo, os cabeçalhos e a conexão. Use o comando Flask para erros de validação detalhados.\n')
    print(result)
