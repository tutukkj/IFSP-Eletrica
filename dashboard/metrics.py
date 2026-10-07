"""Mapeamento da planilha e regras de qualidade (sem alterar valores brutos)."""
from sqlalchemy import and_, case

METRICS = {
    'albedo': ('Albedo', 'Albedo', 'razão'),
    'wind_direction': ('Direção Vetorial', 'Direção do vento', '°'),
    'albedo_index': ('Indice Albedo', 'Índice de albedo', '%'),
    'precipitation': ('Precipitação.Abs', 'Precipitação absoluta', 'unidade não informada'),
    'pressure': ('Pressão Absoluta', 'Pressão absoluta', 'hPa*'),
    'dew_point': ('Pto. Orvalho', 'Ponto de orvalho', '°C*'),
    'solar1': ('Radiacao.Solar1', 'Radiação solar 1', 'W/m²*'),
    'solar2': ('Radiacao.Solar2', 'Radiação solar 2', 'W/m²*'),
    'solar3': ('Radiacao.Solar3', 'Radiação solar 3', 'W/m²*'),
    'contact_temperature': ('Temp.Contato', 'Temperatura de contato', '°C*'),
    'temperature': ('Temperatura', 'Temperatura ambiente', '°C*'),
    'humidity': ('Umidade Relativa', 'Umidade relativa', '%*'),
    'wind_speed': ('Velocidade Média', 'Velocidade média do vento', 'unidade não informada'),
    'wind_gust': ('VelocidadeRajada', 'Rajada', 'unidade não informada'),
}

QUALITY_RULES = [
    'Dados brutos são preservados. A opção de qualidade atua por variável, sem remover linhas inteiras.',
    'Vento: valores 3276,7 são tratados como código suspeito; velocidades negativas e direção fora de 0–360 são excluídas.',
    'Radiação: valores negativos são excluídos, sem substituir por zero.',
    'Albedo: faixa 0–1; índice: 0–100. Ambos exigem Solar1 ≥ 20 para evitar razões instáveis com pouca luz.',
    'Umidade: faixa 0–100. Pressão: deve ser positiva. Precipitação: não negativa e nunca somada.',
    'Temperaturas não recebem limites presumidos. Rajada menor que média não é invalidada sem conhecer o sensor.',
    'Unidades com * são hipóteses baseadas nos nomes, não metadados confirmados. Datas representam o horário local registrado, sem fuso informado.',
]


def is_valid(key, value, row):
    if value is None:
        return False
    if key in ('wind_speed', 'wind_gust'):
        return value >= 0 and abs(value - 3276.7) > 0.001
    if key == 'wind_direction':
        return 0 <= value <= 360
    if key.startswith('solar') or key == 'precipitation':
        return value >= 0
    if key in ('albedo', 'albedo_index'):
        return 0 <= value <= (1 if key == 'albedo' else 100) and (row.get('solar1') or 0) >= 20
    if key == 'humidity':
        return 0 <= value <= 100
    if key == 'pressure':
        return value > 0
    return True


def metric_expression(table, key, clean=True):
    col = table.c[key]
    if not clean:
        return col
    conditions = []
    if key in ('wind_speed', 'wind_gust'):
        conditions = [col >= 0, (col - 3276.7 > 0.001) | (col - 3276.7 < -0.001)]
    elif key == 'wind_direction':
        conditions = [col.between(0, 360)]
    elif key.startswith('solar') or key == 'precipitation':
        conditions = [col >= 0]
    elif key in ('albedo', 'albedo_index'):
        conditions = [col.between(0, 1 if key == 'albedo' else 100), table.c.solar1 >= 20]
    elif key == 'humidity':
        conditions = [col.between(0, 100)]
    elif key == 'pressure':
        conditions = [col > 0]
    return case((and_(*conditions), col), else_=None) if conditions else col
