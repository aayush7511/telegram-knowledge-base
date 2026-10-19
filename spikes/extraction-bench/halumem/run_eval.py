"""HaluMem eval of Graphiti with a fine-tuned extraction model (spec: specs/halumem-eval-35b.md).

Follows HaluMem's eval_zep.py with Zep's cloud calls swapped for local Graphiti; HaluMem's prompts and
scoring code (vendor/, from github.com/MemTensor/HaluMem eval/) run unchanged.

    # 1. add: needs the model served (GPU). Resumable; stop the Modal app right after.
    URL=https://...modal.run .venv/bin/python run_eval.py add --user 2 --sessions 2 --run test2
    # 2. collect: graph search + gpt-4o answers (no GPU)
    .venv/bin/python run_eval.py collect --user 2 --sessions 2 --run test2
    # 3. score: HaluMem's judge (gpt-4o)
    .venv/bin/python run_eval.py score --run test2

Routing: Graphiti's entity and fact extraction (ExtractedEntities / ExtractedEdges) go to the fine-tuned
model (`graphiti` LoRA, thinking off); every other Graphiti call goes to gpt-4.1-mini; search reranks
with gpt-4.1-nano. All OpenAI spend of a run is counted at list price and stops at --cap dollars.
"""
import argparse
import asyncio
import collections
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
BENCH = HERE.parent
sys.path[:0] = [str(BENCH), str(HERE / "vendor")]

import bench  # noqa: E402  (load_env, build_llm, parse_time, EMBEDDING_MODEL)

EXTRACTION = {"ExtractedEntities", "ExtractedEdges"}
PRICES = {"gpt-4o": (2.50, 10.00), "gpt-4.1-mini": (0.40, 1.60), "gpt-4.1-nano": (0.10, 0.40)}  # $/1M in, out
# Verbatim from HaluMem's eval_zep.py (not vendored: it imports the Zep SDK).
TEMPLATE = """
FACTS and ENTITIES represent relevant context to the current conversation.
# These are the most relevant facts for the conversation along with the datetime of the event that the fact refers to.
If a fact mentions something happening a week ago, then the datetime will be the date time of last week and not the datetime
of when the fact was stated.
Timestamps in memories represent the actual time the event occurred, not the time the event was mentioned in a message.
<FACTS>
{facts}
</FACTS>
# These are the most relevant entities
# ENTITY_NAME: entity summary
<ENTITIES>
{entities}
</ENTITIES>
"""


class SpendCapReached(RuntimeError):
    pass


class Spend:
    """OpenAI spend of this run at list price, persisted in the run folder so stages add up."""

    def __init__(self, path: Path, cap: float):
        self.path, self.cap = path, cap
        self.by_model = json.loads(path.read_text()) if path.exists() else {}

    def add(self, model: str, tokens_in: int, tokens_out: int) -> None:
        p_in, p_out = PRICES[model]
        m = self.by_model.setdefault(model, {"in": 0, "out": 0, "usd": 0.0})
        m["in"] += tokens_in
        m["out"] += tokens_out
        m["usd"] += (tokens_in * p_in + tokens_out * p_out) / 1e6
        self.path.write_text(json.dumps(self.by_model, indent=1))

    @property
    def total(self) -> float:
        return sum(m["usd"] for m in self.by_model.values())

    def check(self) -> None:
        if self.total >= self.cap:
            raise SpendCapReached(f"OpenAI spend ${self.total:.2f} reached the ${self.cap:.2f} cap")


def router_class():
    from graphiti_core.llm_client import LLMClient

    class RouterLLM(LLMClient):
        """Graphiti LLM client: extraction prompts to the fine-tuned model, everything else to gpt-4.1-mini.
        Graphiti requires an LLMClient instance; the routed clients do the real work (and keep their own
        token counts)."""

        def __init__(self, ft, mini):
            super().__init__(mini.config)
            self.ft, self.mini = ft, mini
            self.calls = collections.Counter()

        async def _generate_response(self, *args, **kwargs):  # never used: generate_response routes first
            raise NotImplementedError

        generate_response = _route

    return RouterLLM


async def _route(self, messages, response_model=None, *args, **kwargs):
    kind = getattr(response_model, "__name__", None) or kwargs.get("prompt_name") or "text"
    target, who = (self.ft, "fine-tuned") if kind in EXTRACTION else (self.mini, "gpt-4.1-mini")
    self.calls[(kind, who)] += 1
    return await target.generate_response(messages, response_model, *args, **kwargs)


def mini_usage(llm) -> tuple[int, int]:
    u = llm.token_tracker.get_usage().values()
    return sum(x.total_input_tokens for x in u), sum(x.total_output_tokens for x in u)


async def open_graph(name: str, llm, reranker=None):
    from graphiti_core import Graphiti
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
    driver = FalkorDriver(host="127.0.0.1", port=6379, database=name)
    embedder = OpenAIEmbedder(config=OpenAIEmbedderConfig(api_key=os.environ["OPENAI_API_KEY"],
                                                          embedding_model=bench.EMBEDDING_MODEL))
    g = Graphiti(graph_driver=driver, llm_client=llm, embedder=embedder, cross_encoder=reranker)
    if getattr(driver, "_init_task", None):
        await driver._init_task
    return g, driver


async def add(args, run: Path, spend: Spend) -> None:
    from graphiti_core.nodes import EpisodeType
    url = os.environ["URL"].rstrip("/")
    mini, _ = bench.build_llm("baseline")  # gpt-4.1-mini, temperature 0
    if url == "openai":  # plumbing test without a GPU: gpt-4.1-mini stands in for the fine-tuned model
        ft, ft_usage = bench.build_llm("baseline")
    else:
        os.environ.update({"TEACHER_MODEL_FTNOTHINK": "graphiti", "TEACHER_BASE_URL_FTNOTHINK": url + "/v1",
                           "TEACHER_KEY_ENV_FTNOTHINK": "MODAL_VLLM_KEY"})
        ft, ft_usage = bench.build_llm("ftnothink")  # "nothink": chat_template_kwargs enable_thinking=False
    router = router_class()(ft, mini)
    g, driver = await open_graph(args.graph, router)
    added_path = run / "added.json"
    added = json.loads(added_path.read_text()) if added_path.exists() else {}
    if not added:  # a fresh run starts from an empty graph; a resumed one keeps what it built
        await driver.execute_query("MATCH (n) DETACH DELETE n")
        await g.build_indices_and_constraints()
    items = json.loads((BENCH / f"data/items-halumem-u{args.user}.json").read_text())[:args.sessions]
    m_in0, m_out0 = mini_usage(mini)
    for item in items:
        if item["id"] in added:
            continue
        spend.check()
        t0 = time.time()
        r = await g.add_episode(name=item["id"], episode_body=item["body"], source_description="halumem",
                                reference_time=bench.parse_time(item), group_id=args.graph,
                                source=EpisodeType.message)
        added[item["id"]] = {"episode": r.episode.uuid, "facts": [e.fact for e in r.edges],
                             "entities": [n.name for n in r.nodes], "seconds": round(time.time() - t0, 1)}
        added_path.write_text(json.dumps(added, indent=1, ensure_ascii=False))
        m_in, m_out = mini_usage(mini)
        spend.add("gpt-4.1-mini", m_in - m_in0, m_out - m_out0)
        m_in0, m_out0 = m_in, m_out
        print(f"{item['id']}: {len(r.nodes)} entities, {len(r.edges)} facts, {added[item['id']]['seconds']}s; "
              f"OpenAI so far ${spend.total:.3f}", flush=True)
    print("routing:", {f"{k} -> {w}": n for (k, w), n in sorted(router.calls.items())})
    print("fine-tuned model usage:", ft_usage())


async def collect(args, run: Path, spend: Spend) -> None:
    import llms  # HaluMem's gpt-4o client
    from prompts import PROMPT_ZEP
    from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
    from graphiti_core.llm_client import LLMConfig
    from graphiti_core.search.search_config_recipes import EDGE_HYBRID_SEARCH_CROSS_ENCODER, NODE_HYBRID_SEARCH_RRF
    count_openai(llms, spend)
    mini, _ = bench.build_llm("baseline")
    reranker = OpenAIRerankerClient(config=LLMConfig(api_key=os.environ["OPENAI_API_KEY"], model="gpt-4.1-nano"))
    g, _ = await open_graph(args.graph, mini, reranker)

    async def search(query: str, top_k: int) -> tuple[str, list[str]]:  # mirrors eval_zep.search_memory
        ec = EDGE_HYBRID_SEARCH_CROSS_ENCODER.model_copy(deep=True)
        ec.limit = top_k // 2
        nc = NODE_HYBRID_SEARCH_RRF.model_copy(deep=True)
        nc.limit = top_k - top_k // 2
        edges = (await g.search_(query, config=ec, group_ids=[args.graph])).edges
        nodes = (await g.search_(query, config=nc, group_ids=[args.graph])).nodes
        facts = [f"  - {e.fact} (event_time: {e.valid_at})" for e in edges]
        entities = [f"  - {n.name}: {n.summary}" for n in nodes]
        return TEMPLATE.format(facts="\n".join(facts), entities="\n".join(entities)), facts + entities

    added = json.loads((run / "added.json").read_text())
    user = json.loads((BENCH / "data/halumem_medium.jsonl").read_text().splitlines()[args.user])
    out = {"uuid": user["uuid"], "user_name": f"user{args.user}", "sessions": []}
    for i, s in enumerate(user["sessions"][:args.sessions]):
        if s.get("is_generated_qa_session"):
            out["sessions"].append(s)
            continue
        new = {"memory_points": [dict(m) for m in s["memory_points"]], "dialogue": s["dialogue"],
               "extracted_memories": added[f"session-{i:02d}"]["facts"]}
        for m in new["memory_points"]:  # updates: top 10, like eval_zep
            if m["is_update"] == "False" or not m["original_memories"]:
                continue
            spend.check()
            _, m["memories_from_system"] = await search(m["memory_content"][:395], 10)
        if "questions" in s:
            new["questions"] = []
            for qa in s["questions"]:
                spend.check()
                context, _ = await search(qa["question"], 20)
                new["questions"].append({**qa, "context": context,
                                         "system_response": llms.llm_request(PROMPT_ZEP.format(
                                             context=context, question=qa["question"]))})
        out["sessions"].append(new)
        print(f"session {i}: {len(new['extracted_memories'])} facts, "
              f"{sum('memories_from_system' in m for m in new['memory_points'])} update searches, "
              f"{len(new.get('questions', []))} questions; OpenAI so far ${spend.total:.3f}", flush=True)
    (run / "collected.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))


def count_openai(llms, spend: Spend) -> None:
    """Count HaluMem's gpt-4o calls toward the run's cap (same client object, so threads see it too)."""
    create = llms.client.chat.completions.create

    def counted(*a, **kw):
        spend.check()
        r = create(*a, **kw)
        if r.usage:
            spend.add("gpt-4o", r.usage.prompt_tokens or 0, r.usage.completion_tokens or 0)
        return r
    llms.client.chat.completions.create = counted


def score(args, run: Path, spend: Spend) -> None:
    import evaluation  # HaluMem's scorer, unchanged
    import llms
    count_openai(llms, spend)
    evaluation.ProcessPoolExecutor = ThreadPoolExecutor  # same work, in-process, so the spend cap sees it
    records = run / "records.json"
    if records.exists():  # judged already: only re-aggregate (no new gpt-4o calls)
        rec = json.loads(records.read_text())
    else:
        rec = evaluation.process_user(0, json.loads((run / "collected.json").read_text()))
        records.write_text(json.dumps(rec, indent=1, ensure_ascii=False, default=str))
    zero = {"memory_integrity_acc": 0, "memory_update_acc": 0, "total_num": 0}
    try:
        agg = aggregate(evaluation, rec, zero)
    except ZeroDivisionError:  # short test runs lack some record kinds (e.g. no interference memories yet)
        agg = {"note": "too few sessions for HaluMem's aggregate; simple counts from the same records",
               "counts": quick_counts(rec)}
    (run / "results.json").write_text(json.dumps(agg, indent=1, ensure_ascii=False, default=str))
    print(json.dumps(agg.get("overall_score", agg), indent=1, default=str)[:4000])


def quick_counts(rec: dict) -> dict:
    integ = [m for m in rec.get("memory_integrity_records", []) if m.get("memory_source") != "interference"]
    acc = rec.get("memory_accuracy_records", [])
    qa = collections.Counter(q.get("result_type") or q.get("evaluation_result") or "?"
                             for q in rec.get("question_answering_records", []))
    return {"gold_memories": len(integ), "fully_captured": sum(m.get("memory_integrity_score") == 2 for m in integ),
            "extracted_facts": len(acc), "accuracy_scores": collections.Counter(m.get("memory_accuracy_score") for m in acc),
            "updates": collections.Counter(m.get("memory_update_type") for m in rec.get("memory_update_records", [])),
            "qa": qa}


def aggregate(evaluation, rec: dict, zero: dict) -> dict:
    return evaluation.aggregate_eval_results({  # the skeleton HaluMem's evaluation.main() builds
        "overall_score": {"memory_integrity": {}, "memory_accuracy": {}, "memory_extraction_f1": 0,
                          "memory_update": {}, "question_answering": {},
                          "memory_type_accuracy": {t: dict(zero) for t in
                                                   ("Event Memory", "Persona Memory", "Relationship Memory")},
                          "time_consuming": {"add_dialogue_duration_time": 0, "search_memory_duration_time": 0,
                                             "total_duration_time": 0}},
        **{k: rec.get(k, []) for k in ("memory_integrity_records", "memory_accuracy_records",
                                       "memory_update_records", "question_answering_records")}})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["add", "collect", "score"])
    ap.add_argument("--user", type=int, default=2)
    ap.add_argument("--sessions", type=int, default=10**6)
    ap.add_argument("--run", required=True)
    ap.add_argument("--cap", type=float, default=15.0)
    args = ap.parse_args()
    bench.load_env()  # ../.env: OPENAI_API_KEY, MODAL_VLLM_KEY
    os.environ.setdefault("OPENAI_MODEL", "gpt-4o")  # HaluMem's judge / answer model
    for k, v in {"RETRY_TIMES": "5", "WAIT_TIME_LOWER": "2", "WAIT_TIME_UPPER": "20"}.items():
        os.environ.setdefault(k, v)  # HaluMem's llms.py reads these at import
    args.graph = "halumemft" + "".join(c for c in args.run if c.isalpha())  # FalkorDB fulltext breaks on "_"
    run = HERE / "out" / args.run
    run.mkdir(parents=True, exist_ok=True)
    spend = Spend(run / "spend.json", args.cap)
    try:
        if args.stage == "add":
            asyncio.run(add(args, run, spend))
        elif args.stage == "collect":
            asyncio.run(collect(args, run, spend))
        else:
            score(args, run, spend)
    finally:
        print(f"OpenAI spend this run: ${spend.total:.3f} of ${spend.cap:.2f} cap ({json.dumps(spend.by_model)})")


if __name__ == "__main__":
    main()
