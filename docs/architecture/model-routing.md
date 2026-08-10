# Runtime Model Routing

## Principle

Following blowing fixes **logical roles**, not provider-specific model IDs:

- `FAST`
- `MAIN`
- `IMAGE`

The concrete model IDs are runtime-configurable in BYOK API Settings. Suggested model names are defaults for a compatible preset, not bundled access and not proof that a user's Provider exposes those models.

## Role contracts

| Logical role | Runtime field | Suggested value | Required capability |
| --- | --- | --- | --- |
| FAST | `fast_model` / `MODEL_FAST` | `gpt-5.6-luna` | Low-latency text and structured output |
| MAIN | `main_model` / `MODEL_MAIN` | `gpt-5.6-terra` | Structured reasoning, single-image vision, and ordered dual-image comparison |
| IMAGE | `image_model` / `IMAGE_MODEL` | `gpt-image-2` | Image generation and single-reference image editing |

The UI may suggest these values, but it does not silently replace a user-entered model ID. A configured model must exist on the chosen Provider and satisfy its role contract.

## Runtime configuration precedence

ProviderFactory resolves configuration in this order:

1. Current user's BYOK settings.
2. Environment variables supplied by a developer or deployment administrator.
3. Streamlit secrets supplied by an administrator for backward compatibility.
4. Demo providers when the user explicitly selects Demo or no live configuration is active.

Only the first available, internally consistent configuration is used. BYOK Release does not bundle credentials, and ordinary users configure the first layer through the application rather than editing files.

## Provider presets

The generic product contract is **OpenAI Compatible Provider**. A preset may fill public, non-secret suggestions but never an API Key.

| Preset | Base URL behavior | Model behavior | Credential behavior |
| --- | --- | --- | --- |
| Custom OpenAI Compatible | User enters the Provider URL | User enters all three model IDs | User enters their own Key |
| TeamoRouter | Suggest `https://api.teamorouter.com/v1` | Suggest Luna / Terra / GPT Image 2 IDs | Key remains empty until user enters it |

TeamoRouter is an optional preset, not an architectural dependency or exclusive Provider.

## Capability routing

| Capability | Owner | Logical route | Structured handoff |
| --- | --- | --- | --- |
| IP Preparation | Python | deterministic | Prepared IP asset and metadata |
| AI Supplement | Text model | FAST | Non-destructive suggestions |
| IP Intelligence | Vision-capable text model | MAIN | `IPIntelligenceResult` |
| Brand Intelligence | Vision-capable text model | MAIN | `BrandProfile` |
| Brand Collaboration reasoning | Text model | MAIN | Evidence-grounded collaboration rationale |
| Brand Feature | Text model | MAIN | `BrandFeaturePool` |
| Creative Brief | Text model | MAIN | `CreativeBrief` |
| Fusion Decision | Text model | MAIN | `FusionStrategy` and `FusionRelationship` |
| IP Adaptation | Text model | MAIN | `IPAdaptationPlan` |
| Fusion Generation | Image model | IMAGE | Candidate normalized as `CandidateDesign` |
| Pose-Aware Guardian | Vision-capable text model | MAIN | Ordered dual-image `GuardianVisionAssessment` |
| Ranking rationale | Text model | MAIN | `RankingNarrative` |
| Design Package copy | Text model | FAST | Plain text description |
| Package assembly | Python | deterministic | JSON, Markdown, hashes, manifest, and ZIP |

Vision does not create a fourth logical route. MAIN receives image inputs for IP Intelligence, Brand Intelligence, and Guardian; the configured MAIN model must support those requests.

## Connection validation

The standard **Test Connection** action validates live readiness without automatically incurring image-generation cost:

1. Query the Provider model catalog when supported.
2. Check that FAST, MAIN, and IMAGE model IDs are present or otherwise addressable.
3. Send a minimal FAST text request.
4. Send a minimal MAIN text request.
5. Validate IMAGE configuration without generating an image.

An advanced image test is a separate, explicit user action. Browser-facing failures are sanitized and never contain the submitted Key, authorization header, raw provider body, or full traceback.

## Search boundary

Search is not part of the first BYOK settings surface. It remains `demo/mock`, and its evidence mode must stay visible in outputs. A future search credential must use a separate capability test and security review.

## Python authority boundary

Models provide observations, rationale, and image output. Python remains authoritative for:

- Workflow DAG and branch selection.
- Run state, checkpoint, restore, and dependency invalidation.
- Structured-output and artifact validation.
- Guardian weighted identity score, compliance gates, and verdict.
- Ranking dimension scores, weights, and total.
- Retry counters and terminal state.
- File validation, asset storage, image hashes, manifests, ZIP, and export.

No provider response can override these deterministic results.

## Image-reference boundary

Fusion Generation and revision currently use the original IP as a single image reference. Brand constraints arrive through grounded text contracts.

- Single-reference edit: supported target route when the configured Provider and model pass readiness checks.
- Multiple-reference edit: `UNVERIFIED`.

No preset or adapter may imply verified multi-reference support without a separate capability test.

## Trace and credential separation

Execution traces record the logical route, resolved model ID, prompt ID, prompt version, and prompt hash. They never record the API Key, authorization headers, CredentialStore values, or complete runtime credential configuration.

