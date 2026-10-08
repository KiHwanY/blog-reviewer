"""LLM 사용량 기록: 호출별 토큰 수와 예상 비용.

비용은 토큰 수에 모델의 공개 단가를 곱한 값이다. 실제 청구액은 Anthropic 콘솔에서 확인한다.
"""

from contextlib import contextmanager
from typing import Iterator

from langchain_core.callbacks import get_usage_metadata_callback

import config

# 100만 토큰당 달러 (입력, 출력). 출력에는 모델의 생각(thinking) 분량도 포함된다.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def cost(input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = PRICES[config.LLM_MODEL]
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


@contextmanager
def track(step: str) -> Iterator[dict]:
    """with 블록 안에서 일어난 LLM 호출의 사용량을 record에 채워 준다."""
    record = {"step": step, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}
    with get_usage_metadata_callback() as callback:
        yield record
    for model_usage in callback.usage_metadata.values():
        record["input_tokens"] += model_usage["input_tokens"]
        record["output_tokens"] += model_usage["output_tokens"]
    record["cost"] = cost(record["input_tokens"], record["output_tokens"])


def total(records: list[dict]) -> dict:
    """여러 기록을 합친다."""
    return {
        "step": "합계",
        "input_tokens": sum(r["input_tokens"] for r in records),
        "output_tokens": sum(r["output_tokens"] for r in records),
        "cost": sum(r["cost"] for r in records),
    }


def describe(record: dict) -> str:
    return (
        f"입력 {record['input_tokens']:,} / 출력 {record['output_tokens']:,} 토큰, "
        f"약 ${record['cost']:.3f}"
    )
