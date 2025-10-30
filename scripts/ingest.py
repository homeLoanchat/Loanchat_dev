
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

import fitz
import requests
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv


SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
RAW_DIR = BASE_DIR / "data/raw"
CONFIG_PATH = BASE_DIR / "config/data_sources.yaml"
API_EXT_WHITELIST = {"json", "xml", "csv", "txt"}
LINE_SEPARATOR = "\n"


# ---------- 공통 유틸 ----------
def load_sources():
    """config/data_sources.yaml을 열어 'sources' 리스트를 읽어온다."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {CONFIG_PATH}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("sources", [])


def load_env():
    """.env 로드 (API 키 등)"""
    load_dotenv()


def today_str():
    """파일명에 붙일 날짜 문자열"""
    return datetime.now().strftime("%Y%m%d")


def safe_filename(name: str) -> str:
    """파일명에 부적합한 문자를 안전하게 치환"""
    return "".join(c if c.isalnum() or c in "._-+" else "_" for c in name)


def resolve_env(val):
    """YAML에서 ${ENV_KEY} 형태를 .env 환경변수 값으로 치환"""
    if isinstance(val, str) and val.startswith("${") and val.endswith("}"):
        return os.getenv(val[2:-1], "")
    return val


def default_api_params() -> dict:
    """ODCloud 호출 시 기본으로 사용할 파라미터."""
    params = {"page": 1, "perPage": 100}
    service_key = os.getenv("DATA_GO_KR_KEY")
    if service_key:
        params["serviceKey"] = service_key
    return params


# ---------- 수집기(HTML/PDF/API) ----------
def fetch_html(url: str) -> str:
    """HTML 페이지에서 텍스트만 추출"""
    res = requests.get(url, timeout=30)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    return soup.get_text(separator=LINE_SEPARATOR, strip=True)


def _pdf_filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    candidate = Path(parsed.path).name
    if not candidate:
        host_part = safe_filename(parsed.netloc) or "download"
        candidate = f"{host_part}.pdf"
    if not candidate.lower().endswith(".pdf"):
        candidate = f"{candidate}.pdf"
    return safe_filename(candidate)


def _resolve_file_url(path_url: str) -> Path:
    parsed = urlparse(path_url)
    if parsed.scheme != "file":
        raise ValueError("file URL이 아닙니다.")

    combined = (parsed.netloc or "") + (parsed.path or "")
    if not combined:
        raise ValueError("file URL에서 경로를 찾을 수 없습니다.")

    path = Path(unquote(combined))
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def fetch_pdf(url: str) -> str:
    """PDF 경로(HTTP/HTTPS/FILE)에서 페이지별 텍스트 추출"""
    parsed = urlparse(url)
    if parsed.scheme == "file":
        pdf_path = _resolve_file_url(url)
        if not pdf_path.exists():
            raise FileNotFoundError(f"로컬 PDF를 찾을 수 없습니다: {pdf_path}")
    else:
        res = requests.get(url, timeout=60)
        res.raise_for_status()
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        pdf_filename = _pdf_filename_from_url(url)
        pdf_path = RAW_DIR / pdf_filename
        pdf_path.write_bytes(res.content)

    text = ""
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text += page.get_text()
    return text


def fetch_api(api_cfg: dict) -> tuple[str, str]:
    """공공데이터/기관 API 호출 (원문과 포맷을 반환)."""
    endpoint = api_cfg.get("endpoint")
    if not endpoint:
        raise ValueError("API endpoint가 비어 있습니다.")

    method = (api_cfg.get("method") or "GET").upper()
    params = {k: resolve_env(v) for k, v in (api_cfg.get("params") or {}).items()}
    headers = api_cfg.get("headers") or {}
    timeout = api_cfg.get("timeout", 30)
    fmt = (api_cfg.get("format") or "json").lower()

    if method == "GET":
        res = requests.get(endpoint, params=params, headers=headers, timeout=timeout)
    elif method in ("POST", "PUT", "PATCH", "DELETE"):
        res = requests.request(method, endpoint, json=params, headers=headers, timeout=timeout)
    else:
        raise ValueError(f"지원하지 않는 HTTP 메서드: {method}")

    res.raise_for_status()
    return res.text, fmt


# ---------- 메인 ----------
def _iter_api_tasks(src: dict, topic: dict):
    topic_name = topic.get("name", "unknown_topic")

    base_defaults = {
        "method": (topic.get("method") or src.get("method") or "GET").upper(),
        "format": (topic.get("format") or src.get("format") or "json").lower(),
        "params": topic.get("params") or src.get("params") or {},
        "headers": topic.get("headers") or src.get("headers") or {},
        "timeout": topic.get("timeout") or src.get("timeout") or 30,
    }

    def merge_cfg(endpoint: str, overrides: dict | None = None) -> dict:
        overrides = overrides or {}
        method = (overrides.get("method") or base_defaults["method"]).upper()
        fmt = (overrides.get("format") or base_defaults["format"]).lower()
        params = {
            **default_api_params(),
            **base_defaults["params"],
            **(overrides.get("params") or {}),
        }
        headers = {
            **base_defaults["headers"],
            **(overrides.get("headers") or {}),
        }
        timeout = overrides.get("timeout") or base_defaults["timeout"]
        return {
            "endpoint": endpoint,
            "method": method,
            "format": fmt,
            "params": params,
            "headers": headers,
            "timeout": timeout,
        }

    api_cfg = topic.get("api")
    if api_cfg:
        endpoint = api_cfg.get("endpoint")
        if not endpoint:
            print(f"⚠️ [{src.get('name', 'unknown_source')} - {topic_name}] endpoint가 없어 API 호출을 건너뜁니다.")
        else:
            yield topic_name, merge_cfg(endpoint, api_cfg)

    auto_ids = topic.get("auto_topics") or []
    if not auto_ids:
        return

    base_url = topic.get("base_url") or src.get("base_url")
    if not base_url:
        print(f"⚠️ [{src.get('name', 'unknown_source')} - {topic_name}] base_url이 없어 auto_topics를 처리할 수 없습니다.")
        return

    for auto_id in auto_ids:
        endpoint = f"{base_url.rstrip('/')}/{auto_id}"
        auto_topic_name = f"{topic_name}_{auto_id}"
        yield auto_topic_name, merge_cfg(endpoint)


def main():
    load_env()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    try:
        sources = load_sources()
    except FileNotFoundError as err:
        print(f"[❌ 설정 파일 오류] {err}")
        return

    if not sources:
        print("⚠️ config/data_sources.yaml에서 sources가 비어있습니다.")
        return

    for src in sources:
        src_name = src.get("name", "unknown_source")
        topics = src.get("topics", [])
        if not topics:
            print(f"ℹ️ {src_name}: topics 없음, 스킵")
            continue

        for topic in topics:
            topic_name = topic.get("name", "unknown_topic")
            t = topic.get("type")
            try:
                if t == "html":
                    url = topic["url"]
                    text = fetch_html(url)
                    ext = "txt"
                    generated = [(topic_name, text, ext)]
                elif t == "pdf":
                    url = topic["url"]
                    text = fetch_pdf(url)
                    ext = "txt"
                    generated = [(topic_name, text, ext)]
                elif t == "api":
                    api_tasks = list(_iter_api_tasks(src, topic))
                    if not api_tasks:
                        print(f"⚠️ [{src_name} - {topic_name}] API 설정이 없어 스킵합니다.")
                        continue

                    generated = []
                    for task_name, api_cfg in api_tasks:
                        text, fmt = fetch_api(api_cfg)
                        ext = fmt if fmt in API_EXT_WHITELIST else "txt"
                        generated.append((task_name, text, ext))
                else:
                    print(f"⚠️ [{src_name} - {topic_name}] 지원하지 않는 형식(type): {t}, 스킵")
                    continue

                for out_topic_name, text, ext in generated:
                    fname = f"{safe_filename(src_name)}_{safe_filename(out_topic_name)}_{today_str()}.{ext}"
                    out_path = RAW_DIR / fname
                    out_path.write_text(text, encoding="utf-8")
                    print(f"[✅ 저장 완료] {src_name} - {out_topic_name} -> {out_path}")

            except requests.HTTPError as e:
                print(f"[❌ HTTP 오류] {src_name} - {topic_name}: {e}")
            except Exception as e:
                print(f"[❌ 처리 실패] {src_name} - {topic_name}: {e}")


if __name__ == "__main__":
    main()
