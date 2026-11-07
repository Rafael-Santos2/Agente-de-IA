"""Tools com saída reduzida a dados validados, sem texto livre do provedor."""
import asyncio
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone

from strands import tool

MAX_CITY_CHARS = 100
MAX_RESPONSE_BYTES = 256_000
HTTP_TIMEOUT = 5
CITY_PATTERN = re.compile(r"^[^\W\d_]+(?:[ .,'’\-][^\W\d_]+)*$", re.UNICODE)


@tool
def current_datetime() -> str:
    """Retorna a data e hora atuais em UTC (ISO 8601)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _owm_get(endpoint: str, params: dict) -> dict:
    if endpoint not in {"weather", "forecast"}:
        raise ValueError("Endpoint não permitido.")
    url = "https://api.openweathermap.org/data/2.5/" + endpoint
    url += "?" + urllib.parse.urlencode(params)
    # Não seguir redirecionamentos carregando appid para outro destino.
    with urllib.request.build_opener(NoRedirect()).open(url, timeout=HTTP_TIMEOUT) as response:
        deadline = time.monotonic() + HTTP_TIMEOUT
        body = bytearray()
        while len(body) <= MAX_RESPONSE_BYTES:
            if time.monotonic() >= deadline:
                raise TimeoutError()
            chunk = response.read1(min(8192, MAX_RESPONSE_BYTES + 1 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("Resposta excessiva.")
    value = json.loads(body)
    if not isinstance(value, dict):
        raise ValueError("Resposta inválida.")
    return value


def _number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Valor meteorológico inválido.")
    return round(value, 2)


def _condition(block):
    # Ignorar description, main, icon, nomes de cidade e demais textos do servidor.
    code = block["weather"][0]["id"]
    if type(code) is not int:
        raise ValueError("Código inválido.")
    if 200 <= code <= 232:
        return "trovoadas"
    if 300 <= code <= 321:
        return "garoa"
    if 500 <= code <= 531:
        return "chuva"
    if 600 <= code <= 622:
        return "neve"
    if code in {701, 711, 721, 731, 741, 751, 761, 762, 771, 781}:
        return "fenômeno atmosférico"
    if code == 800:
        return "céu limpo"
    if 801 <= code <= 804:
        return "nuvens"
    raise ValueError("Código não reconhecido.")


def _error(code, message):
    return json.dumps({"ok": False, "erro": code, "mensagem": message}, ensure_ascii=False)


def _forecast(city):
    if not isinstance(city, str) or not 1 <= len(city) <= MAX_CITY_CHARS or not CITY_PATTERN.fullmatch(city):
        return _error("cidade_invalida", "Informe apenas cidade e país, até 100 caracteres.")
    api_key = (os.getenv("OPENWEATHER_API_KEY") or "").strip()
    if not api_key:
        return _error("nao_configurado", "Configure OPENWEATHER_API_KEY no .env.")
    params = {"q": city, "appid": api_key, "units": "metric", "lang": "pt_br"}
    try:
        current = _owm_get("weather", params)
        forecast = _owm_get("forecast", params)
        now = {
            "temperatura_c": _number(current["main"]["temp"], -100, 70),
            "sensacao_c": _number(current["main"]["feels_like"], -120, 100),
            "umidade_pct": _number(current["main"]["humidity"], 0, 100),
            "condicao": _condition(current),
        }
        items = forecast["list"]
        if not isinstance(items, list) or not 1 <= len(items) <= 40:
            raise ValueError("Quantidade inválida.")
        days = {}
        for item in items:
            timestamp = _number(item["dt"], 0, 4_102_444_800)
            day = datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()
            minimum = _number(item["main"]["temp_min"], -100, 70)
            maximum = _number(item["main"]["temp_max"], -100, 70)
            if minimum > maximum:
                raise ValueError("Intervalo inválido.")
            data = days.setdefault(day, {"min": minimum, "max": maximum, "desc": Counter()})
            data["min"] = min(data["min"], minimum)
            data["max"] = max(data["max"], maximum)
            data["desc"][_condition(item)] += 1
        return json.dumps({
            "ok": True, "fonte": "OpenWeatherMap", "cidade_consultada": city,
            "consultado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "agora": now,
            "previsao_por_dia_utc": [
                {"data": day, "min_c": data["min"], "max_c": data["max"],
                 "condicao": data["desc"].most_common(1)[0][0]}
                for day, data in sorted(days.items())
            ],
        }, ensure_ascii=False)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return _error("cidade_nao_encontrada", "Cidade não encontrada.")
        if error.code in (401, 403):
            return _error("autenticacao", "Verifique a chave da OpenWeatherMap.")
        return _error("indisponivel", "Serviço meteorológico indisponível.")
    except (TimeoutError, urllib.error.URLError, OSError):
        return _error("rede", "Não foi possível consultar o clima a tempo.")
    except (ValueError, KeyError, IndexError, TypeError, OverflowError, RecursionError):
        return _error("resposta_invalida", "O serviço retornou dados meteorológicos inválidos.")


@tool
async def weather_forecast(city: str) -> str:
    """Consulta tempo atual e próximos cinco dias, em °C e UTC.

    Args:
        city: Apenas nome da cidade e país, até 100 caracteres. Ex.: São Paulo,BR.
    """
    # Não bloquear o loop: o prazo global do turno continua funcionando.
    return await asyncio.to_thread(_forecast, city)
