# OwnerGraph - SPEC (SDD v0.3)

Built during Graph Hacks: Context for AI Agents (FalkorDB x WeMakeDevs). Only design notes and a graph-model sketch existed before the
hackathon window opened (2026-10-15 03:31 KST); the first commit in this repository is the failing test suite derived from section 11.

## 0. Purpose <!-- 목적 -->
Kubernetes is a public organisation of 1000+ people working like a company. OwnerGraph puts its teams (SIGs), approval rights
(OWNERS), decisions (KEPs) and real approval history (merged PRs) into one FalkorDB graph, so an agent can answer
"who *may* approve this, who *actually* decides, and why was it decided" with the executed Cypher, the path, and source links, and
can draft routing for a new issue. The point is not "who approves" (Prow already does that) but **governance drift**: the gap between
what OWNERS files say and who really approves.

## 1. Success conditions, deadline, non-goals <!-- 성공 조건 / 비목표 -->
- E1 (time split): cutoff 2026-08-01. Evaluate on kubernetes/kubernetes PRs merged after the cutoff that have at least one
  non-author approver; predict the actual non-author approvers, report hit@1, hit@3, MRR. Baselines: (a) Prow-style OWNERS
  (random permutation, greedy set cover), (b) text retrieval over past PRs, (e) per-OWNERS-file past approval counts with recency
  (the strongest non-graph baseline). Success = on the **hard segment** (no approval history in the governing OWNERS directory,
  or several OWNERS files, or KEP-linked PRs) the graph method's hit@3 >= baseline (e) + 15 percentage points, and overall >= (e).
  All numbers are published whatever they turn out to be.
- E2 (multi-hop questions): >= 50 held-out questions (>= 15 single-hop, >= 35 multi-hop) with answer keys computed from the raw
  YAML by a script that does not use the graph; agent with graph tools vs. the same LLM with vector RAG; ablation removes the graph tools.
- E3 (issue routing): needs-sig issues that later received a sig label.
- Live: median answer latency <= 15 s over 20 runs, opened without login.
- Tests >= 40 passing; `make eval` regenerates the numbers in the README.
- Floor: if E1 does not beat the baselines this is stated in the README and the project is judged on traceability and
  explainability instead.
- Non-goals: ranking people by "inactivity" (health is aggregated per OWNERS file only - no personal profiling); writing comments or
  labels to the real Kubernetes repositories (routing is a draft in the UI); model training or fine-tuning; Slack/mailing-list
  ingestion; multi-user accounts; paid infrastructure.

## 2. Constraints
1. If the product still works with FalkorDB removed, the graph is decoration: every answer is produced by a FalkorDB query; the
   LLM only interprets the question and words the result.
2. Public data only. People are GitHub handles only; name/company/email are dropped before loading (AC-9).
3. Agent path is read-only: Cypher templates, a keyword guard, and the `GRAPH.RO_QUERY` connection (AC-15).
4. Cost 0: GitHub GraphQL with a personal token (5,000 points/h), embedded FalkorDB (falkordblite) or the FalkorDB docker image.

## 3. Ubiquitous language (identifier = term)
Org, Person(login), Sig, Directory(path), OwnersFile, Alias, EligibleApprover (`eligible_approvers`), Decider (`deciders`),
Kep(number), FeatureGate(name), DecisionTrail, RouteProposal, OrphanedDecision, GovernanceDrift, OwnersHealth, HardSegment,
EvidencePath, Abstention, Cutoff.

## 4. Graph model
```
(Person)-[:APPROVER_IN]->(OwnersFile)-[:GOVERNS]->(Directory)-[:CHILD_OF]->(Directory)
(Person)-[:MEMBER_OF]->(Alias)-[:APPROVER_IN]->(OwnersFile)      (OwnersFile)-[:LABELS]->(Sig)
(Person)-[:CHAIRS|LEADS]->(Sig)
(Kep)-[:OWNED_BY|PARTICIPATES]->(Sig)   (Person)-[:AUTHORED_KEP|APPROVED_KEP]->(Kep)   (Kep)-[:INTRODUCES]->(FeatureGate)
(PR)-[:TOUCHES]->(Directory)   (Person)-[:AUTHORED_PR]->(PR)   (Person)-[r:APPROVED_PR {at}]->(PR)   (PR)-[:IMPLEMENTS]->(Kep)
```
Layers: `domain/` (pure) <- `application/` (use cases, ports) <- `adapters/` (FalkorDB, GitHub, MCP, HTTP) <- `infrastructure/` (CLI, composition).

## 5. Use cases
UC-1 AskQuestion, UC-2 ApproversForPath, UC-3 ExplainDecision, UC-4 RouteIssue (draft only), UC-5 SyncOrg (incremental),
UC-6 StaleDecisions, UC-7 RunEvalE1, UC-9 DriftReport (per OWNERS file), UC-10 RunEvalE3, UC-11 ReviewerCentrality (PageRank, `Which reviewers are load-bearing?`).

## 6. Acceptance criteria (Given/When/Then)
- AC-1 Given OWNERS in `a/` (approvers [x]) and `a/b/` ([y]) When eligible_approvers("a/b/c/f.go") Then {x, y}.
- AC-2 Given `a/b` has no_parent_owners When same query Then {y} only.
- AC-3 Given an approver that is an alias When resolved Then it expands to its members (cycles terminate).
- AC-4 Given the PR author is an eligible approver When ranking Then the author is excluded from candidates and from the truth set.
- AC-5 Given approvers x (5 recent approvals below the path) and y (none) When ranked Then x is above y.
- AC-6 Given prediction [x,y,z], truth {z} Then hit@1 = 0, hit@3 = 1.
- AC-7 Given a query with no graph path When asked Then Abstention ("no evidence", attempted Cypher), no answer sentence generated.
- AC-8 Given a KEP whose approvers hold no current approver/leadership role When UC-6 Then it is an OrphanedDecision.
- AC-9 Given sigs.yaml person records {github, name, company, email} When PiiFilter Then {login} only.
- AC-10 Given Prow APPROVALNOTIFIER comments When parsed Then the last APPROVED comment wins, self-approval and NOT APPROVED are ignored.
- AC-11 Given a successful answer Then the response carries >= 1 executed Cypher and >= 1 GitHub URL.
- AC-12 Given an issue text When routed Then SIG, top-3 approvers and a related KEP are returned as a draft.
- AC-13 Given last snapshot T When synced Then only items updated after T are upserted and changed KEP statuses are listed.
- AC-14 Given E1 When a training PR was merged at or after the cutoff Then the run aborts with a leakage error.
- AC-15 Given the agent path When a query contains CREATE/MERGE/DELETE/SET/REMOVE (outside string literals) Then it is rejected.
- AC-16 Given the MCP server When tools/list Then exactly seven tools (the seventh, `reviewer_centrality`, runs FalkorDB PageRank over the derived `RELIES_ON` edges) with input schemas.
- AC-17 Given POST /api/ask When an example question is sent Then 200 with an evidence path, server time <= 1 s (fake LLM).
- AC-18 Given the results JSON When the README numbers are checked Then any mismatch fails.
- AC-19 Given E1 feature extraction Then only fields known when the PR opened (title, body, files, author) are used - never comments.
- AC-20 Given a question When answered Then the deterministic graph path exists before (and without) the LLM summary.
- AC-21 Given an OWNERS file with 4 listed approvers, 1 active in 90 days Then OwnersHealth = 0.25 with no per-person field.

## 7. UI acceptance criteria <!-- UI 수용기준 -->
First screen: one question input and three example chips. Answer card order: one-sentence answer, path graph, "Show Cypher",
sources. Loading text "Querying the graph". Captured at 390 px and 1280 px, contrast AA (>= 4.5:1), light and dark.
- UI-2 A ranking card (`#ranking`) lists every eligible approver with the approvals counted in the window and tags approvers with
  0 recent approvals as dormant; non-ranking answers (KEP trails, stale decisions) render their rows as a table (`#rows`).
- UI-3 A governance-drift banner (`#drift`) shows the aggregate from `/api/drift` (inactive approvers / all approvers, window in days) - no per-person data.

## 11. Test plan
The test names in `tests/` map 1:1 to the AC list above (domain, application, adapters, infrastructure), plus boundary tests
(empty OWNERS, cyclic alias, root path, deleted directory, missing KEP fields, bot-comment variants). Integration tests run
against an embedded FalkorDB (no docker, no network).
