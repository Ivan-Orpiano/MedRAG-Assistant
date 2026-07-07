"""Evaluation harness — run retrieval and generation quality checks separately.

Usage (inside the api container or a venv with backend deps + a running stack):

    python -m eval.run_eval --file eval/eval_set.example.jsonl --k 8

Case format (JSONL), one of:
  {"question": ..., "expected_document_title": ..., "expected_answer_contains": [...]}
  {"question": ..., "expect_refusal": true}

Metrics reported:
  * retrieval recall@k  — did a chunk from the expected document reach the top k?
  * refusal accuracy    — did the grounding gate refuse out-of-corpus questions?
  * answer keyword hit  — cheap programmatic proxy; contains expected substrings?
  * faithfulness (opt.) — LLM-as-judge: every claim supported by the cited context?
                          Enable with --judge. Binary per case, rubric-driven.
"""
import argparse
import json
import sys

from app.db.session import SessionLocal
from app.services import generation
from app.services.retrieval.retriever import retrieve


def judge_faithfulness(question: str, answer: str, context: str) -> bool:
    from openai import OpenAI

    from app.core.config import get_settings

    client = OpenAI(api_key=get_settings().openai_api_key)
    rubric = (
        "You are grading a RAG answer. Reply with exactly YES or NO.\n"
        "YES only if EVERY factual claim in the answer is directly supported by the "
        "provided context. Any unsupported claim, invented number, or external "
        "knowledge means NO."
    )
    response = client.chat.completions.create(
        model=get_settings().openai_chat_model,
        temperature=0.0,
        max_tokens=3,
        messages=[
            {"role": "system", "content": rubric},
            {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}\n\nANSWER:\n{answer}"},
        ],
    )
    return (response.choices[0].message.content or "").strip().upper().startswith("YES")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--k", type=int, default=8)
    parser.add_argument("--judge", action="store_true", help="run LLM-as-judge faithfulness")
    parser.add_argument("--generate", action="store_true", help="also run generation (costs tokens)")
    args = parser.parse_args()

    cases = [json.loads(line) for line in open(args.file) if line.strip()]
    db = SessionLocal()
    recall_hits, recall_total = 0, 0
    refusal_correct, refusal_total = 0, 0
    keyword_hits, keyword_total = 0, 0
    faithful, faithful_total = 0, 0
    failures = []

    try:
        for case in cases:
            question = case["question"]
            result = retrieve(db, question, top_k=args.k)

            if case.get("expect_refusal"):
                refusal_total += 1
                if not result.grounded:
                    refusal_correct += 1
                else:
                    failures.append({"question": question, "failure": "should have refused, was grounded",
                                     "top_titles": [c.document_title for c in result.chunks[:3]]})
                continue

            expected_title = case.get("expected_document_title")
            if expected_title:
                recall_total += 1
                titles = [c.document_title for c in result.chunks]
                if expected_title in titles:
                    recall_hits += 1
                else:
                    failures.append({"question": question, "failure": f"recall miss for '{expected_title}'",
                                     "retrieved": titles})

            if args.generate and result.grounded:
                answer = "".join(generation.stream_grounded_answer(question, result.chunks, []))
                expected_substrings = case.get("expected_answer_contains", [])
                if expected_substrings:
                    keyword_total += 1
                    if all(s.lower() in answer.lower() for s in expected_substrings):
                        keyword_hits += 1
                    else:
                        failures.append({"question": question, "failure": "answer missing expected content",
                                         "answer": answer[:300]})
                if args.judge:
                    faithful_total += 1
                    context = generation.build_context_block(result.chunks)
                    if judge_faithfulness(question, answer, context):
                        faithful += 1
                    else:
                        failures.append({"question": question, "failure": "judge: unfaithful",
                                         "answer": answer[:300]})
    finally:
        db.close()

    def rate(hits, total):
        return f"{hits}/{total} ({hits / total:.0%})" if total else "n/a"

    print("\n=== MedAssist eval ===")
    print(f"retrieval recall@{args.k}: {rate(recall_hits, recall_total)}")
    print(f"refusal accuracy:      {rate(refusal_correct, refusal_total)}")
    print(f"answer keyword hit:    {rate(keyword_hits, keyword_total)}")
    print(f"faithfulness (judge):  {rate(faithful, faithful_total)}")
    if failures:
        print(f"\n--- {len(failures)} failures (read these, don't just watch the score) ---")
        for f in failures:
            print(json.dumps(f, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
