# 수집된 문서 로드 및 전처리
# raw에 저장된 json, txt, pdf 파일을 읽어 텍스트 추출, 정제, 청킹 수행

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# PDF 리더 우선순위(pypdf > PyPDF2)
try:  # pragma: no cover - optional dependency discovery
    from pypdf import PdfReader as _PdfReader
except Exception:  # noqa: BLE001
    _PdfReader = None

try:  # pragma: no cover - optional fallback
    from PyPDF2 import PdfReader as _PyPdfReader  # type: ignore[import-untyped]
except Exception:  # noqa: BLE001
    _PyPdfReader = None


SUPPORTED_EXTENSIONS = {".txt", ".json", ".pdf"} # 지원되는 파일 확장자

# 데이터 클래스
@dataclass(frozen=True)
class Document: # 원본 문서 단위
    doc_id: str
    title: str
    source_path: Path
    file_format: str
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class DocumentChunk: # 청킹된 문서 단위
    chunk_id: str
    text: str
    metadata: dict[str, Any]

# 문서 로딩
def discover_sources(raw_dir: Path) -> list[Path]:
    """원천 디렉터리에서 지원 확장자 파일 탐색"""
    files = [path for path in raw_dir.rglob("*") if path.is_file()]
    filtered = [path for path in files if path.suffix.lower() in SUPPORTED_EXTENSIONS]
    skipped = {path for path in files if path not in filtered} # 지원되지 않는 파일 집합
    if skipped:
        for path in sorted(skipped):
            logger.warning("지원하지 않는 파일 형식이라 건너뜀: %s", path)
    return sorted(filtered)


def load_documents(raw_dir: Path) -> list[Document]:
    """텍스트 추출 + 정제 + 메타데이터 생성"""
    documents: list[Document] = []
    for source_path in discover_sources(raw_dir):
        try:
            raw_text = read_text_from_source(source_path)
            clean_text = normalize_text(raw_text)
        except Exception as exc:  # noqa: BLE001
            logger.exception("문서 로딩 실패: %s (%s)", source_path, exc)
            continue

        metadata = build_document_metadata(source_path, raw_text, clean_text)
        doc_id = make_document_id(metadata)
        document = Document(
            doc_id=doc_id,
            title=metadata["doc_title"],
            source_path=source_path,
            file_format=metadata["doc_format"],
            text=clean_text,
            metadata=metadata,
        )
        documents.append(document)
        logger.info("문서 로딩 완료: %s (문자 수=%d)", source_path.name, len(clean_text))

    return documents

# 파일별 텍스트 추출
def read_text_from_source(source_path: Path) -> str:
    """확장자에 따라 텍스트 추출"""
    suffix = source_path.suffix.lower()
    if suffix == ".txt":
        return source_path.read_text(encoding="utf-8")
    if suffix == ".json":
        return json_to_text(json.loads(source_path.read_text(encoding="utf-8")))
    if suffix == ".pdf":
        return read_pdf_text(source_path)
    raise ValueError(f"지원하지 않는 파일 확장자: {suffix}")


def read_pdf_text(source_path: Path) -> str:
    """PDF 파일에서 텍스트 추출"""
    reader_cls = _PdfReader or _PyPdfReader
    if reader_cls is None:
        raise RuntimeError(
            "PDF 텍스트를 추출하려면 'pypdf' 또는 'PyPDF2' 패키지가 필요합니다."
        )

    reader = reader_cls(str(source_path)) 
    pages: list[str] = []
    for page_index, page in enumerate(getattr(reader, "pages", [])):
        try:
            extracted = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "PDF 페이지 추출 실패: %s (page=%d, error=%s)",
                source_path.name,
                page_index,
                exc,
            )
            continue
        pages.append(extracted)
    if not pages:
        logger.warning("PDF에서 추출된 텍스트가 없음: %s", source_path.name)
    return "\n".join(pages)


def json_to_text(payload: Any, indent: int = 0) -> str:
    """JSON 객체를 사람이 읽기 쉬운 텍스트로 변환"""
    indent_str = " " * indent
    if isinstance(payload, dict):
        lines = []
        for key, value in payload.items():
            lines.append(f"{indent_str}{key}:")
            lines.append(json_to_text(value, indent + 2))
        return "\n".join(lines)
    if isinstance(payload, list):
        lines = []
        for index, item in enumerate(payload, start=1):
            lines.append(f"{indent_str}- 항목 {index}")
            lines.append(json_to_text(item, indent + 2))
        return "\n".join(lines)
    return f"{indent_str}{payload}"

# 텍스트 정제 및 메타데이터 생성
def normalize_text(text: str) -> str:
    """공백/개행 정리"""
    text = text.replace("\ufeff", "")
    text = text.replace("\xa0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +\n", "\n", text)
    return text.strip()


def build_document_metadata(source_path: Path, raw_text: str, clean_text: str) -> dict[str, Any]:
    """파일 메타데이터 생성"""
    stat = source_path.stat()
    title = derive_title(source_path)
    return {
        "doc_title": title,
        "doc_source": str(source_path),
        "doc_name": source_path.name,
        "doc_format": source_path.suffix.lower().lstrip("."),
        "doc_filesize": stat.st_size,
        "doc_modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "doc_raw_characters": len(raw_text),
        "doc_clean_characters": len(clean_text),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }


def derive_title(source_path: Path) -> str:
    """파일명으로부터 제목 생성"""
    stem = source_path.stem
    cleaned = re.sub(r"[_\-]+", " ", stem)
    return re.sub(r"\s+", " ", cleaned).strip()


def make_document_id(metadata: dict[str, Any]) -> str:
    """문서 고유 ID 생성"""
    base = f"{metadata['doc_source']}::{metadata['doc_modified_at']}"
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()
    return digest[:12]

# 청킹
def chunk_documents(
    documents: Iterable[Document],
    *,
    chunk_size: int,
    overlap: int,
    min_chunk_chars: int,
    ) -> list[DocumentChunk]:
    """문서 청킹"""
    chunks: list[DocumentChunk] = []
    for document in documents:
        document_chunks = list(
            chunk_single_document(
                document,
                chunk_size=chunk_size,
                overlap=overlap,
                min_chunk_chars=min_chunk_chars,
            )
        )
        chunks.extend(document_chunks)
        logger.info(
            "청킹 완료: %s (총 %d개)",
            document.source_path.name,
            len(document_chunks),
        )
    return chunks


def chunk_single_document(
    document: Document,
    *,
    chunk_size: int,
    overlap: int,
    min_chunk_chars: int,
) -> Iterable[DocumentChunk]:
    """한 문서를 일정 길이로 분할"""
    text = document.text
    text_length = len(text)
    start = 0
    chunk_index = 0
    while start < text_length:
        end = min(start + chunk_size, text_length)
        window = text[start:end]
        if end < text_length:
            best_break = find_best_break(window)
            if best_break is not None and best_break > overlap:
                end = start + best_break
                window = text[start:end]
        cleaned_window = window.strip()
        if not cleaned_window:
            start = max(end, start + overlap)
            continue
        if len(cleaned_window) < min_chunk_chars and end < text_length:
            start = max(end - overlap, start + 1)
            continue

        chunk_id = f"{document.doc_id}:{chunk_index:04d}"
        chunk_metadata = {
            "chunk_id": chunk_id,
            "chunk_index": chunk_index,
            "chunk_char_start": start,
            "chunk_char_end": end,
            "chunk_char_length": len(cleaned_window),
            **document.metadata,
        }
        yield DocumentChunk(chunk_id=chunk_id, text=cleaned_window, metadata=chunk_metadata)

        if end >= text_length:
            break
        start = max(end - overlap, 0)
        chunk_index += 1


def find_best_break(window: str) -> int | None:
    """문장 경계 기준으로 끊을 위치 탐색"""
    anchors = ["\n\n", "\n", ". ", "! ", "? "]
    best_position = -1
    best_anchor_length = 0
    for anchor in anchors:
        position = window.rfind(anchor)
        if position > best_position:
            best_position = position
            best_anchor_length = len(anchor)
    if best_position <= 0:
        return None
    return best_position + best_anchor_length

# 결과 저장
def write_chunks(chunks: Iterable[DocumentChunk], output_path: Path) -> None:
    """청크를 JSONL 파일로 저장"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for chunk in chunks:
            payload = {
                "id": chunk.chunk_id,
                "text": chunk.text,
                "metadata": chunk.metadata,
            }
            file.write(json.dumps(payload, ensure_ascii=False))
            file.write("\n")

# 실행
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"), help="원천 데이터 디렉터리")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/processed"), help="정제 결과 저장 디렉터리"
    )
    parser.add_argument(
        "--output-name",
        type=str,
        default="chunks.jsonl",
        help="청킹 결과 파일명 (JSONL)",
    )
    parser.add_argument("--chunk-size", type=int, default=800, help="청크 최대 길이(문자)")
    parser.add_argument("--chunk-overlap", type=int, default=120, help="청크 겹침 길이(문자)")
    parser.add_argument(
        "--min-chunk-chars",
        type=int,
        default=200,
        help="청크 최소 길이(문자). 부족하면 다음 윈도우와 병합",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="로깅 레벨",
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


def main() -> None:
    """전체 파이프라인 실행"""
    args = parse_args()
    configure_logging(args.log_level)

    raw_dir: Path = args.raw_dir
    if not raw_dir.exists():
        raise FileNotFoundError(f"원천 데이터 디렉터리를 찾을 수 없습니다: {raw_dir}")

    documents = load_documents(raw_dir)
    if not documents:
        logger.warning("처리할 문서를 찾지 못했습니다.")
        return

    chunks = chunk_documents(
        documents,
        chunk_size=args.chunk_size,
        overlap=args.chunk_overlap,
        min_chunk_chars=args.min_chunk_chars,
    )

    output_path = args.output_dir / args.output_name
    write_chunks(chunks, output_path)

    logger.info("총 %d개 문서에서 %d개 청크 생성", len(documents), len(chunks))
    logger.info("결과 저장: %s", output_path)


if __name__ == "__main__":
    main()
