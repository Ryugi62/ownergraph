# Who may approve it, who actually decides, and why: Kubernetes governance in one FalkorDB graph

*Graph Hacks 2026, Track 03 Company Brain (also entered in Track 01). Code: <https://github.com/Ryugi62/ownergraph>*

Kubernetes is a public organisation of more than a thousand people that works like a company. It has teams (SIGs), approval rights (OWNERS files), design decisions (KEPs) and a long public record of who really approved what (merged pull requests). All of it is public, and none of it lives in the same place.

I built OwnerGraph to put those four things into one FalkorDB graph and let an agent answer one question with its work shown: *who may approve this change, who has actually been approving this area, and why was it decided that way?*

## The problem is a gap, not a lookup

An OWNERS file says who **may** approve. The pull request history says who **does**. In our snapshot, 99 of the 167 approver handles listed in OWNERS files approved nothing in the last 90 days, and 45 open KEPs list approvers who hold no current approver or SIG-chair role. A plain lookup of the OWNERS file hands you a list that is partly stale. The interesting answer needs several hops: a path to its OWNERS files (with inheritance and aliases), their approvers, the recent approvals around that path, and sometimes the KEP that justified the change.

## The graph

```
(Person)-[:APPROVER_IN]->(OwnersFile)-[:GOVERNS]->(Directory)-[:CHILD_OF]->(Directory)
(Person)-[:MEMBER_OF]->(Alias)-[:APPROVER_IN]->(OwnersFile)      (OwnersFile)-[:LABELS]->(Sig)
(Kep)-[:OWNED_BY]->(Sig)   (Person)-[:APPROVED_KEP]->(Kep)   (Kep)-[:INTRODUCES]->(FeatureGate)
(PR)-[:TOUCHES]->(Directory)   (Person)-[:APPROVED_PR]->(PR)   (PR)-[:IMPLEMENTS]->(Kep)
```

The load-bearing query is a variable-length walk: from the directory of a file up through `CHILD_OF*0..30`, stopping where an OWNERS file sets `no_parent_owners`, then through alias membership (`MEMBER_OF*0..3`) to the people. Without a graph engine you would re-implement this walk in application code on every question. A second FalkorDB feature does a different job: `algo.pageRank` runs over a derived `RELIES_ON` edge (author to approver) to find the reviewers other contributors depend on. The agent never writes: it uses Cypher templates, a keyword guard, and `GRAPH.RO_QUERY`. The model may suggest a query, a read-only query decides.

## What the measurements say

I wrote the evaluation plan into the spec before building, and I froze the question set in git before any agent ran.

- **E2, 60 frozen questions, same LLM, different source of facts.** On multi-hop questions the graph agent scores 95.0% and vector retrieval over the same raw files scores 22.5% (LLM alone: 0%). Taking the graph tools away costs 72.5 points. On single-hop lookups retrieval is competitive (95.0% vs 100.0%), and the README says so.
- **E1, 716 real merged pull requests after a time cut.** hit@3 is the share of evaluated pull requests whose real approver is among the top three suggested approvers. The graph reaches 80.3% against 76.4% for the strongest non-graph baseline (per-OWNERS-file approval counts with recency): +3.9 points, 95% CI +2.0 to +5.9. hit@1 is a tie (53.5% vs 54.2% for tf-idf retrieval). On the "hard segment" I pre-registered a +15 point target and got +5.2. I missed it, and the README says that too. The large gains (+57 points) sit in two small slices of 33 and 35 PRs where the baseline has nothing to look at, so I present them as a mechanism, not as a headline accuracy.

## Things the tests caught, and things I got wrong

- Writing the failing tests first found three real bugs before any number was reported: intermediate directories with no OWNERS file broke the walk (three-valued logic on a null property), the OWNERS node itself blocked its own `no_parent_owners` boundary, and negative list indexes in Cypher. Before those fixes the graph scored 39.8% hit@3.
- My first full E2 run scored 0% for every system because the model name was wrong. I had skipped a smoke test. I added an abort guard (more than 25% errors stops the run) and a smoke step, and re-ran from scratch.
- A four-question smoke run showed my retriever baseline could not find "KEP-4656" or file paths because of tokenisation. A baseline that cannot find an identifier is a strawman, so I fixed it before the frozen run and documented the change.

## What I learned

1. A graph earns its place on questions that need paths. For one-hop facts, a retriever was nearly as good, and saying so makes the multi-hop result easier to believe.
2. Make the system say "no evidence". The most useful screen in the demo is the one that refuses to answer.
3. Pre-registering a target and then missing it is uncomfortable and worth it. The miss told me exactly where the graph helps (back-off along parent OWNERS files) and where it does not (multi-owner directories, where it ties).

## Try it

```bash
git clone https://github.com/Ryugi62/ownergraph && cd ownergraph
make setup load demo    # then open http://127.0.0.1:8000
```

The repository also ships a docker image, a seven-tool MCP server and the exact Cypher the product depends on. Built with Claude Code, spec first and tests first; every number in the README is regenerated by `make eval`.
