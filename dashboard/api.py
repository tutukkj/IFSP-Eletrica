import csv
import io
import math
from datetime import datetime, timedelta
from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context
from sqlalchemy import Integer, and_, case, cast, func, select
from .database import readings as table
from .metrics import METRICS, QUALITY_RULES, metric_expression

api = Blueprint('api', __name__, url_prefix='/api')
BUCKETS = {'minute': 60, '15min': 900, 'hour': 3600, 'day': 86400}


def engine():
    return current_app.extensions['db_engine']


@api.errorhandler(ValueError)
def bad_request(exc):
    return jsonify(error=str(exc)), 400


def integer(name, default, minimum, maximum):
    try:
        value = int(request.args.get(name, default))
    except ValueError as exc:
        raise ValueError(f'{name} deve ser um número inteiro.') from exc
    if not minimum <= value <= maximum:
        raise ValueError(f'{name} deve estar entre {minimum} e {maximum}.')
    return value


def filters():
    terms = []
    start, end = None, None
    station = request.args.get('station')
    if station:
        if len(station) > 120:
            raise ValueError('Estação inválida.')
        terms.append(table.c.station == station)
    for param in ('start', 'end'):
        raw = request.args.get(param)
        if not raw:
            continue
        try:
            value = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError(f'{param}: use data ISO, como 2026-09-23.') from exc
        if value.tzinfo:
            raise ValueError('Use datas locais sem fuso, como registradas na planilha.')
        if param == 'start':
            start = value
            terms.append(table.c.timestamp >= value)
        else:
            # Data final inclui o dia todo; datetime inclui o minuto selecionado.
            end = value + (timedelta(days=1) if len(raw) == 10 else timedelta(minutes=1))
            terms.append(table.c.timestamp < end)
    if start and end and start >= end:
        raise ValueError('O início deve ser anterior ao fim do período.')
    raw_clean = request.args.get('clean', '1')
    if raw_clean not in ('0', '1'):
        raise ValueError('clean deve ser 0 ou 1.')
    return and_(*terms) if terms else True, raw_clean == '1'


def iso(value):
    return value.isoformat(timespec='seconds') if value else None


@api.get('/metadata')
def metadata():
    with engine().connect() as connection:
        bounds = connection.execute(select(func.count(), func.min(table.c.timestamp), func.max(table.c.timestamp)).select_from(table)).one()
        stations = list(connection.execute(select(table.c.station).distinct().order_by(table.c.station)).scalars())
    return jsonify(total=bounds[0], start=iso(bounds[1]), end=iso(bounds[2]), stations=stations,
                   database=engine().dialect.name, metrics={key: {'label': spec[1], 'unit': spec[2]} for key, spec in METRICS.items()},
                   quality_rules=QUALITY_RULES, source='sensor_readings', timezone='Horário local da planilha; fuso não informado')


@api.get('/summary')
def summary():
    where, clean = filters()
    columns = [func.count().label('total'), func.min(table.c.timestamp).label('start'), func.max(table.c.timestamp).label('end'),
               func.sum(case((table.c.has_quality_issue == True, 1), else_=0)).label('quality_rows')]
    for key in METRICS:
        col = metric_expression(table, key, clean)
        columns.extend([func.min(col).label(key + '_min'), func.max(col).label(key + '_max'), func.count(col).label(key + '_count')])
        if key != 'wind_direction':
            columns.append(func.avg(col).label(key + '_avg'))
    with engine().connect() as connection:
        row = connection.execute(select(*columns).select_from(table).where(where)).mappings().one()
    metrics = {key: {'min': row[key + '_min'], 'max': row[key + '_max'], 'avg': row.get(key + '_avg'), 'count': row[key + '_count']} for key in METRICS}
    return jsonify(total=row['total'], start=iso(row['start']), end=iso(row['end']), quality_rows=row['quality_rows'] or 0, clean=clean, metrics=metrics)


@api.get('/series')
def series():
    where, clean = filters()
    interval = request.args.get('interval', 'auto')
    if interval not in (*BUCKETS, 'auto'):
        raise ValueError('Intervalo inválido: use auto, minute, 15min, hour ou day.')
    limit = integer('max_points', 1500, 50, 2000)
    db = engine()
    with db.connect() as connection:
        minimum, maximum = connection.execute(select(func.min(table.c.timestamp), func.max(table.c.timestamp)).where(where)).one()
        if minimum is None:
            return jsonify(points=[], interval=interval, clean=clean)
        seconds = (maximum - minimum).total_seconds()
        bucket_seconds = BUCKETS.get(interval, next((v for v in BUCKETS.values() if math.ceil(seconds / v) + 2 <= limit), 86400))
        if math.ceil(seconds / bucket_seconds) + 2 > limit:
            raise ValueError('Período muito grande para esse intervalo. Escolha automático ou uma agregação maior.')
        epoch = func.extract('epoch', table.c.timestamp) if db.dialect.name == 'postgresql' else (func.julianday(table.c.timestamp) - 2440587.5) * 86400
        bucket = cast(func.floor((epoch + 0.001) / bucket_seconds), Integer)
        aggregates = [bucket.label('bucket'), func.count().label('samples')]
        for key in METRICS:
            col = metric_expression(table, key, clean)
            if key == 'wind_direction':
                sx, cx = func.avg(func.sin(func.radians(col))), func.avg(func.cos(func.radians(col)))
                angle = func.degrees(func.atan2(sx, cx))
                aggregate = case((sx * sx + cx * cx < 1e-12, None), else_=case((angle < 0, angle + 360), else_=angle))
            else:
                aggregate = func.avg(col)
            aggregates.append(aggregate.label(key))
        rows = connection.execute(select(*aggregates).where(where).group_by(bucket).order_by(bucket).limit(limit)).mappings().all()
    points = []
    by_bucket = {row['bucket']: dict(row) for row in rows}
    # Intervalos sem registros continuam no eixo temporal, como ausências.
    # Evita comprimir lacunas e ligar leituras através de períodos sem dados.
    for bucket_id in range(rows[0]['bucket'], rows[-1]['bucket'] + 1):
        data = by_bucket.get(bucket_id, {'samples': 0, **{key: None for key in METRICS}})
        data.pop('bucket', None)
        data['timestamp'] = (datetime(1970, 1, 1) + timedelta(seconds=bucket_id * bucket_seconds)).isoformat()
        points.append(data)
    name = next(k for k, v in BUCKETS.items() if v == bucket_seconds)
    return jsonify(points=points, interval=name, clean=clean, aggregation='Média por intervalo; direção usa média circular. Precipitação absoluta não é somada.')


def serialize_row(row):
    result = dict(row)
    result['timestamp'] = iso(result['timestamp'])
    return result


@api.get('/readings')
def readings():
    where, _ = filters()
    page = integer('page', 1, 1, 10000000)
    size = integer('page_size', 25, 1, 200)
    with engine().connect() as connection:
        total = connection.execute(select(func.count()).select_from(table).where(where)).scalar_one()
        rows = connection.execute(select(table).where(where).order_by(table.c.timestamp.desc(), table.c.station).offset((page - 1) * size).limit(size)).mappings().all()
    return jsonify(rows=[serialize_row(row) for row in rows], total=total, page=page, page_size=size, pages=math.ceil(total / size))


@api.get('/export.csv')
def export_csv():
    where, _ = filters()
    db = engine()
    @stream_with_context
    def generate():
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=';')
        fields = ['station', 'timestamp', *METRICS, 'source_file', 'has_quality_issue']
        writer.writerow(fields)
        yield '\ufeff' + buffer.getvalue()
        buffer.seek(0); buffer.truncate(0)
        with db.connect() as connection:
            result = connection.execution_options(stream_results=True).execute(select(table).where(where).order_by(table.c.timestamp, table.c.station))
            for row in result.mappings():
                data = serialize_row(row)
                values = []
                for field in fields:
                    value = data[field]
                    if isinstance(value, float):
                        value = str(value).replace('.', ',')
                    elif isinstance(value, str) and value.startswith(('=', '+', '-', '@', '\t', '\r')):
                        value = "'" + value
                    values.append(value)
                writer.writerow(values)
                yield buffer.getvalue()
                buffer.seek(0); buffer.truncate(0)
    return Response(generate(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=leituras.csv'})
