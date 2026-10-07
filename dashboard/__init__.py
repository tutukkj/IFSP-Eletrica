import os
from pathlib import Path
import click
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template
from sqlalchemy.exc import SQLAlchemyError
from .database import make_engine, metadata


def create_app():
    project = Path(__file__).resolve().parent.parent
    load_dotenv(project / '.env')
    app = Flask(__name__, instance_path=str(project / 'instance'))
    Path(app.instance_path).mkdir(exist_ok=True)
    url = os.getenv('DATABASE_URL') or f'sqlite:///{(Path(app.instance_path) / "monitoramento.sqlite").as_posix()}'
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql+psycopg://', 1)
    elif url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
    app.extensions['db_engine'] = make_engine(url)
    from .api import api
    app.register_blueprint(api)

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.errorhandler(SQLAlchemyError)
    def database_error(exc):
        app.logger.error('Falha de banco (%s)', type(exc).__name__)
        return jsonify(error='Banco indisponível ou tabela ainda não criada. Confira a conexão e execute o importador.'), 503

    @app.cli.command('init-db')
    def init_db():
        metadata.create_all(app.extensions['db_engine'])
        click.echo('Tabela sensor_readings criada.')

    @app.cli.command('import-excel')
    @click.argument('filename', type=click.Path(exists=True, dir_okay=False))
    @click.option('--station', default='principal', show_default=True)
    @click.option('--sheet', default=None)
    def import_command(filename, station, sheet):
        from .importer import import_excel
        try:
            result = import_excel(app.extensions['db_engine'], filename, station, sheet, lambda count: click.echo(f'Processadas: {count}', nl=True) if count % 10000 == 0 else None)
        except (ValueError, KeyError, SQLAlchemyError, OSError) as exc:
            if isinstance(exc, SQLAlchemyError):
                raise click.ClickException('Falha ao conectar/importar no banco. Verifique DATABASE_URL; os dados desta importação foram revertidos.') from exc
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Lidas: {result['read']} | Inseridas: {result['inserted']} | Duplicatas ignoradas: {result['duplicates']} | Linhas com alertas na origem: {result['quality_rows']}")

    return app
