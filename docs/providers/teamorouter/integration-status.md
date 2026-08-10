# TeamoRouter Integration Status

Project: Following blowing  
Build started: 2026-08-09 10:32 +08:00

## Route status

| Capability | Route | Model | Status |
| --- | --- | --- | --- |
| AI Supplement | FAST | `gpt-5.6-luna` | READY; real structured smoke PASS |
| Design Package copy | FAST | `gpt-5.6-luna` | READY |
| IP Intelligence | MAIN vision | `gpt-5.6-terra` | READY; real image smoke PASS |
| Brand Intelligence | MAIN vision | `gpt-5.6-terra` | READY; real image smoke PASS |
| Brand Collaboration reasoning | MAIN | `gpt-5.6-terra` | READY |
| Brand Feature | MAIN | `gpt-5.6-terra` | READY |
| Creative Brief | MAIN | `gpt-5.6-terra` | READY |
| Fusion Decision | MAIN | `gpt-5.6-terra` | READY |
| IP Adaptation | MAIN | `gpt-5.6-terra` | READY |
| Pose-Aware Guardian | MAIN multi-image | `gpt-5.6-terra` | READY |
| Ranking rationale | MAIN | `gpt-5.6-terra` | READY |
| Fusion Generation | IMAGE | `gpt-image-2` | READY; real generation smoke PASS |
| Single-reference image edit | IMAGE | `gpt-image-2` | READY; real edit smoke PASS |
| Multiple-reference image edit | IMAGE | `gpt-image-2` | **UNVERIFIED** |

`READY` for IP Adaptation and Pose-Aware Guardian means the model route and structured contract are available for the schema-v2 workflow. Python remains authoritative for schema validation, Guardian scoring and verdicts, checkpoints, retries, and export.

## Verified smoke evidence

### Real agent smoke

- Route assertion: Luna `gpt-5.6-luna`, Terra `gpt-5.6-terra`, image `gpt-image-2`.
- Luna AI Supplement returned a structured suggestion without overwriting the user constraint.
- Terra IP Intelligence returned image-grounded IP identity fields from the supplied IP reference.
- Terra Brand Intelligence returned an image-grounded `BrandProfile` without a hard-coded brand branch.
- Terra ordered dual-image Guardian rejected the known drift fixture; Python calculated the authoritative identity score and verdict.

The reproducible agent smoke remains an explicit opt-in operation and does not print credentials or endpoint configuration.

### Real IP Adaptation smoke

- Terra MAIN `gpt-5.6-terra`: PASS.
- One logical structured-output call returned a complete HIGH-transformation `IPAdaptationPlan` for a newly reconstructed seated pose, right-limb wave, and held-product interaction.
- The plan preserved identity anchors while explicitly re-posing the character and rejecting a frozen source-pose treatment.
- GPT Image 2 calls: 0.

### GPT Image 2 smoke

- Models endpoint verification: PASS.
- Image generation: PASS with a locally persisted, hash-validated artifact.
- Single-reference edit: PASS with a locally persisted, hash-validated artifact and matching source-reference hash.
- Multiple-reference edit: UNVERIFIED and disabled by default.

Production Fusion Generation continues to use only the original IP image as its image reference. Brand guidance enters through grounded text contracts. No current readiness claim implies multiple-reference support.

## Documented endpoints

| Endpoint | Status |
| --- | --- |
| `GET /v1/models` | DOCUMENTED |
| `POST /v1/responses` | DOCUMENTED |
| `POST /v1/chat/completions` | DOCUMENTED |
| `POST /v1/images/generations` | DOCUMENTED |
| `POST /v1/images/edits` | DOCUMENTED |

The verified TeamoRouter API documentation is unchanged; this file records integration readiness only.
