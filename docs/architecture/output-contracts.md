# Output Contracts

## Contract authority

Model outputs are proposals until Python validates them against the corresponding schema. Python also owns persistence, hashes, scores, verdicts, completion, and export. Downstream agents consume normalized structured objects, not unvalidated provider text.

## Main contracts and handoffs

| Contract | Producer | Required consumers | Purpose |
| --- | --- | --- | --- |
| `IPIntelligenceResult` | IP Intelligence | Creative Brief, Fusion Decision, IP Adaptation, Guardian, export | Contains `IPDNA`, native `IPIdentityGrammar`, and optional compatibility `IdentityLock` |
| `IPIdentityGrammar` | IP Intelligence | Creative Brief, Fusion Decision, IP Adaptation, Generation prompt, Guardian | Defines legal transformation and forbidden identity drift |
| `BrandProfile` | Brand Intelligence | Brand Collaboration, Brand Feature, export | Image-grounded brand identity evidence; no hard-coded brand rules |
| `CollaborationResearchReasoning` | Brand Collaboration | Brand Feature | Grounded patterns and rationale over normalized sourced research |
| `BrandFeaturePool` | Brand Feature | Creative Brief, Fusion Decision, IP Adaptation, Generation prompt, export | Brand cues plus integration affordances, use guidance, attachment, scale, occlusion, and identity risks |
| `CreativeBrief` | Creative Brief | Fusion Decision, IP Adaptation, Guardian, Ranking, export | Auditable user goal contract with role, action, interaction, view, and transformation level |
| `FusionStrategy` | Fusion Decision | IP Adaptation, Generation prompt, Ranking, export | Approved fusion logic, visual selections, constraints, and nested `FusionRelationship` |
| `IPAdaptationPlan` | IP Adaptation | Fusion Generation, Guardian, Ranking, export | Pose blueprint, deformation map, identity preservation, brand attachment, interaction, and generation constraints |
| `CandidateDesign` | Fusion Generation adapter | Guardian, Ranking, Design Package | Persisted generated image reference and generation metadata; never authoritative Guardian metrics |
| `GuardianVisionAssessment` | Pose-Aware Guardian | Python Guardian scoring | Ten scored checks with reasons, drift findings, correction groups, and revision instruction |
| Guardian Report (`GuardianResult`) | Python | Retry gate, Ranking, Design Package, export | Authoritative weighted identity score, gates, verdict, findings, and corrections |
| `RankingNarrative` | Ranking rationale | Python Ranking assembly | Reasons, evidence, and explanation only |
| `RankingResult` | Python | Design Package and export | Fixed score breakdown and weighted total plus Terra narrative |
| `DesignPackage` | Python, with Luna copy | Export | Validated artifact inventory, copy, manifest, and archive metadata |

## Key schema requirements

### IPIdentityGrammar

The grammar covers character type, identity anchors, relational geometry, topology, proportion signature, line, facial, ear, and limb grammar; deformable and pose-dependent features; transformation and attachment rules; immutable and mutable features; forbidden drift; risks; unknowns; and confidence.

It cannot be reduced to “keep the source pose.”

### BrandFeaturePool

Each structured feature identifies evidence and one or more affordances from apparel, accessory, held object, product interaction, role, environment, narrative, graphic application, and color application. It also specifies preferred, secondary, and avoided uses; interaction modes; attachment targets; scale guidance; occlusion risk; and identity conflict risk.

### CreativeBrief

The brief retains the existing theme and constraint fields and adds desired character role, action, interaction, view, and `LOW`, `MEDIUM`, or `HIGH` transformation level. Its provenance must preserve the priority user free text > user-selected goals > adopted AI supplement.

### FusionStrategy and FusionRelationship

The relationship defines IP role, brand role, interaction, behavior, product interaction, apparel, graphics, color, scene, narrative, and fusion depth. Fusion depth is one of `STICKER`, `COLOR`, `ACCESSORY`, `APPAREL`, `PRODUCT_INTERACTION`, `BEHAVIOR`, `ROLE`, or `NARRATIVE`.

### IPAdaptationPlan

The plan includes target action, target pose, view angle, transformation level, pose blueprint, deformation map, identity-preservation rules, brand attachments, interaction plan, occlusion rules, attachment rules, generation instructions, and negative constraints.

A `HIGH` plan requires a meaningful pose or action transformation. Missing schema-v1 adaptation data must never be replaced with a fabricated default.

### Guardian Report

Terra's assessment supplies check values and reasons. Python creates the Guardian Report by applying the fixed identity weights and three compliance gates. The report includes the authoritative `identity_score`, verdict, pose context, legal transformations, drift findings, correction groups, and retry instruction.

### RankingResult

Python provides every numeric dimension and computes the weighted total. `ip_identity_consistency` reuses Guardian `identity_score` exactly. Terra may add `score_reasons`, `evidence`, and `explanation`, but cannot change numeric values.

### DesignPackage

Luna provides plain copy only. Python validates and assembles the package.

The package contains at least:

- `result.png` or the validated final image equivalent.
- `ip_identity_grammar.json`.
- `brand_profile.json`.
- `brand_feature_pool.json`.
- `creative_brief.json`.
- `fusion_strategy.json`.
- `ip_adaptation.json`.
- `guardian_report.json`.
- `ranking.json`.
- `workflow_trace.json`.
- `prompt_trace.json`.
- `design_guide.md`.
- A manifest with deterministic file hashes.

`ip_identity.json` may remain as a compatibility export, but `ip_identity_grammar.json` is the canonical identity artifact.

## Prompt and execution trace

Every real model-backed execution persists `prompt_id`, `prompt_version`, `prompt_hash`, model route, and resolved model with its normalized result. The workflow trace references these values without including credentials or authorization data.

An agent reaches `COMPLETED` only after provider success, schema validation, result persistence, and checkpoint success.

## Schema-v1 restore

Historical checkpoints remain readable:

1. Treat a missing workflow schema version as v1.
2. Parse legacy `IdentityLock` and preserve it for inspection.
3. Add a compatibility warning when native `IPIdentityGrammar` or `IPAdaptationPlan` is missing.
4. Invalidate IP Intelligence and downstream artifacts before continuing a v2 run.
5. Do not synthesize a completed adaptation plan.
6. Fresh competition runs and demo runs use schema v2 and all twelve agents.

