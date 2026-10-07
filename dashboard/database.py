import math
from sqlalchemy import Boolean, Column, DateTime, Float, Index, MetaData, String, Table, create_engine, event
from sqlalchemy.engine import make_url
from .metrics import METRICS

metadata = MetaData()
readings = Table(
    'sensor_readings', metadata,
    Column('station', String(120), primary_key=True),
    Column('timestamp', DateTime, primary_key=True),
    Column('source_file', String(255), nullable=False),
    Column('has_quality_issue', Boolean, nullable=False),
    *(Column(key, Float) for key in METRICS),
)
Index('ix_sensor_readings_timestamp', readings.c.timestamp)


def make_engine(url):
    options = {'connect_timeout': 10} if make_url(url).get_backend_name() == 'postgresql' else {}
    engine = create_engine(url, pool_pre_ping=True, connect_args=options)
    if engine.dialect.name not in ('sqlite', 'postgresql'):
        raise ValueError('Use uma DATABASE_URL SQLite ou PostgreSQL.')
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine, 'connect')
        def sqlite_functions(connection, _):
            for name, nargs, fn in [('sin', 1, math.sin), ('cos', 1, math.cos), ('atan2', 2, math.atan2), ('degrees', 1, math.degrees), ('radians', 1, math.radians), ('floor', 1, math.floor)]:
                connection.create_function(name, nargs, lambda *args, fn=fn: None if any(a is None for a in args) else fn(*args), deterministic=True)
            connection.execute('PRAGMA busy_timeout=10000')
    return engine
