# Fleet document pipeline

A driver sends a photo or PDF on WhatsApp. It is stored encrypted, read by the model (Meta Muse through the Meta
Model API), checked by plain rules, and the cab's record updates. The driver gets an answer in their own language:
"Received insurance for TS-09-XY-4521, valid till 18-05-2027", or the exact problem ("This bill shows a different
vehicle number. Please resend.").

Built for the Meta Global AI Developer Hackathon on the CDAI Fleet Compliance Dashboard. The public demo uses a
fictional client and synthetic drivers, cabs and documents only.

## Flow, and where each step lives

| # | Step | Code |
|---|------|------|
| 1 | Webhook `POST /wa/inbound`; Meta signature (`X-Hub-Signature-256`) checked; one-time GET handshake | `app.py`, `inbound.py` |
| 2 | Download the media; SHA-256 of the file | `bridge.graph_download_media`, `intake.py` |
| 3 | Phone to driver to cab. Unknown number: "not registered", nothing stored. No consent yet: consent request, nothing stored | `registry.py`, `intake.py` |
| 4 | Original to S3 with SSE-KMS: `fleet/{vehicle}/{yyyy-mm}/{sha256}.{ext}`; medical certificates under `restricted/medical/...` | `store.py` |
| 5 | Job to SQS, carrying a hashed sender id, never a phone number | `jobs.py` |
| 6 | For a photo: SAM 3.1 finds the paper; code crops, straightens and trims the page (scans skip this) | `photo.py` |
| 7 | Worker reads the page: Muse Spark vision call with JSON-schema structured output | `model.py`, `schema.py` |
| 7a | Rule checks in code, not AI | `rules.py` |
| 8 | Cab record, document log and open safety actions in DynamoDB | `records.py` |
| 9 | Reply in English, Hindi or Telugu, paced per driver, with the driver's own module link when a document is accepted | `replies.py`, `training.py` |
| 10 | The client dashboard reads the same records live: no rebuild, no export | `state.py`, `dashboard.py`, `dashboard/site/` |

All outbound HTTP (WhatsApp media, replies and the model) goes through `bridge.py` only.

## Photo step (`photo.py`)

A driver's photo of a bill is rarely flat or framed. For images with dark surroundings (a car seat, a counter),
SAM 3.1 is asked for the "paper document" through the Responses API; it answers with a box (in its token the `w`
and `h` are the image size, not the box). Code crops to the box, measures the text-line skew on the centre of the
crop, rotates against a dark fill and trims to the bright page. Scans whose paper already fills the frame skip the
call. A SAM failure is logged and the original photo is read. SAM finds; it never decides. On
`demo/synthetic/photo_TS09XY4521_tilted_demo.jpg` SAM returns the paper at 38% of the frame in about five seconds
and the page is straightened by its 7.5 degree tilt. `PHOTO_MODE=off` disables the step.

## Dashboard (`dashboard.py`, `state.py`, `dashboard/site/`)

One read-only function behind its own URL serves the page and answers `GET /api/state` from the records. The page
polls every 4 seconds with an ETag, so an unchanged fleet costs a 304 and nothing more; when a document lands, the
cab's row updates within seconds and the changed row flashes.

- **Access.** The page is public; the state needs the access code (`Authorization: Bearer`, compared in constant
  time) and fails closed when none is configured. The code lives in the secret as `DASHBOARD_KEY`;
  `infra/ensure_dashboard_key.py` adds one to an existing secret and prints it.
- **What it shows.** Fleet totals (consent, documents, accepted, rejected, open safety actions, papers due, median
  photo-to-reply seconds), live activity, every cab with its status, and per cab: consent, papers with validity,
  open safety actions, each document with what the model read, every rule flag, timings, and the module that went out.
- **What it never shows.** Phone numbers and learner links. Status is decided in a fixed order (`status_view`):
  open safety action, expired paper, resend requested, more proof requested, renewal due, nothing yet, up to date.
- **Hardening.** `default-src 'self'` CSP, no inline code, `noindex`, `nosniff`, `DENY` framing, one flat asset
  folder (no traversal), read-only IAM role (`dynamodb:Query`, `dynamodb:GetItem`, the secret).
- **Locally:** `python demo/rehearse.py` then `python dashboard/serve_local.py 8098` (access code `demo`).

## Train (`training.py`)

A reply that accepts a document also carries a short module in the driver's language, from D Advaya FM naipuNya's
driver programme (ten modules; the platform serves them in Telugu, Hindi, Kannada, Marathi, Tamil and English).
A workshop advisory on the cab points at vehicle care first; otherwise the next module in sequence goes out, one per
accepted document. Each driver holds one learner token on the training platform (`training_token` in the private
registry, enrolled once with `demo/mint_training_links.py`); a lesson page opened without a token is refused at the
edge. The record keeps the module and the link; the dashboard shows the module only.

## Reply pacing (`intake.reply`)

WhatsApp rejects a burst of messages to the same person, so a driver who sends ten bills at once would lose most of
the answers. Replies to one driver are spaced `REPLY_GAP_S` apart through a per-recipient send slot in the records
(an atomic conditional write, so parallel workers queue correctly). The worker waits for its slot (up to
`REPLY_MAX_WAIT_S`, then sends anyway and logs it); the webhook never waits: its "checking it now" note is dropped
when the slot is busy, and one-off replies such as consent go at once. A send accepted by the API is still not a
delivery: the `statuses` webhook receipts (`WA_STATUS` log lines) are the only proof.

## Rule checks (`rules.py`)

Each check is tested in `tests/test_rules.py`:

- **Vehicle number** on the document differs from the sender's cab: reject. One character off reads as "check the RC copy".
- **Date** in the future: reject.
- **No GSTIN** on a service invoice, job card, spares bill or cash memo: reject.
- **Odometer** below the last known reading: review.
- **Duplicates.** The same file or the same issuer and invoice number already filed for another cab: reject.
- **Partial proof.** A spares bill, payment receipt or estimate needs the job card or final invoice.
- **Billed to a bank** or other business: more proof needed.
- **Insurance, PUC, permit, fitness, road tax and RC:** expired, or due within 30 days.
- **Safety advisories** (tyres, brakes, clutch, steering, suspension, fuel system) open an action on the cab. A later bill whose work lines show the fix closes it.

The five problems found in the manual audit of real bills are tests, with synthetic data:

1. A future-dated memo.
2. A wrong vehicle number.
3. A bill in a bank's name.
4. A spares-only bill.
5. An invoice filed under the wrong cab.

## Changes from the build note

- **WhatsApp channel.** The note assumed Twilio. Instead, the pipeline uses Meta's WhatsApp Cloud API test number:
  - The Twilio number has been deactivated.
  - The live helpline already runs on AWS End User Messaging, which forwards Meta's own webhook format.
  - So one parser serves the demo now and the helpline later, unchanged.
- **Residency guard.** Meta's Model API is hosted outside India, and CDAI's rule is that personal data stays in India.
  - The worker refuses (`ResidencyError`) to send any document from a driver not marked `"synthetic": true` to a model where `in_india` is false.
  - Real fleets need a model hosted in Mumbai behind the same `extract()` interface.
- **Extra fields.** The model also returns:
  - `billed_to`, so bank-name bills are caught
  - `is_estimate`
  - a one-line `summary` for the dashboard
- **Extra document types:** `payment_receipt`, `police_verification` and `medical_certificate`.
- **Medical certificates.** A caption containing MEDICAL routes the file to the restricted prefix, and it is never sent to the model.

## Configuration

Set these as environment variables. In AWS they are loaded from the Secrets Manager secret named by `SECRET_ID`. Never put them in code or files.

| Variable | What |
|---|---|
| `MODEL_MODE` | `muse` (Meta Model API) or `standin` (prepared readings, offline) |
| `META_API_BASE_URL`, `META_API_KEY`, `MUSE_MODEL_ID` | Meta Model API, from the Meta developer console |
| `PHOTO_MODE`, `SAM_MODEL_ID` | `sam` runs the photo step with SAM 3.1 (default `sam-3.1`); `off` skips it |
| `WA_APP_SECRET`, `WA_VERIFY_TOKEN` | webhook signature and handshake |
| `WA_ACCESS_TOKEN`, `WA_PHONE_NUMBER_ID`, `GRAPH_API_VERSION` | WhatsApp Cloud API (permanent system-user token) |
| `S3_BUCKET`, `KMS_KEY_ID`, `SQS_QUEUE_URL`, `DDB_TABLE` | AWS, region fixed to ap-south-1 |
| `REGISTRY_FILE` | driver registry (synthetic example in `demo/`); the live file also carries each driver's `training_token` |
| `LOCAL_DATA_DIR` | development: keep files, queue and records on disk instead of AWS |
| `ACK_ON_RECEIPT` | send "Received. Checking it now." before the result (default true) |
| `REPLY_GAP_S`, `REPLY_MAX_WAIT_S` | spacing between replies to one driver (default 3 s) and the longest a worker holds one (60 s) |
| `DASHBOARD_KEY` | the dashboard access code (in the secret; the state endpoint fails closed without it) |

## Privacy (DPDP Act, 2023)

- **Consent.** Every driver gets a one-time consent message, and nothing they send is stored until they reply YES.
  - Replying STOP withdraws consent. From then on nothing is stored or read, including files already waiting in
    the queue. YES starts again.
  - Erasing documents filed before a withdrawal is not built yet. For now it is a manual step, on request.
- **Logs.** Logs carry hashed ids and cab ids only: no phone numbers, names, captions or document text.
  - Every model call (model, latency, tokens, document type, confidence) is logged.
  - Every rule decision (outcome, flag codes, actions opened or closed) is logged.
- **Records.** The record keeps the fields read from the document except `billed_to`. Only its flag is kept.
- **Medical certificates.** They live under their own prefix and never go to the model.
- **Real documents.** These cannot reach a model outside India: the residency guard above enforces it.

## Run

    python -m pytest -q                       # 62 tests, no network or AWS needed
    set LOCAL_DATA_DIR=local_data
    uvicorn pipeline.app:app --port 8100      # webhook on http://localhost:8100/wa/inbound
    python demo/rehearse.py                   # the whole flow offline, into local_data/rehearsal
    python dashboard/serve_local.py 8098      # the dashboard on those records (access code: demo)

## Deploy (AWS, ap-south-1 only)

    powershell -NoProfile -File infra\deploy.ps1                                   # synthetic registry
    powershell -NoProfile -File infra\deploy.ps1 -RegistryFile demo/registry.live.json   # with test phones

- `infra/template.yaml` is the whole stack (CloudFormation `fleet-doc-pipeline-demo`):
  - a KMS key and the documents bucket (`cdai-fleet-docs-demo-mumbai`: private, HTTPS only, demo files expire after
    90 days)
  - the jobs queue with a dead-letter queue after 3 tries
  - the DynamoDB table
  - least-privilege roles for each function
  - the webhook behind a function URL, the worker triggered by the queue, and the read-only dashboard behind its
    own function URL
- `infra/build_lambda.py` builds the package: the pipeline, the demo files, the dashboard site, and the dependencies
  as Linux wheels.
- The secret `fleet-doc-pipeline/demo` is created once with placeholders, a random `WA_VERIFY_TOKEN` and a random
  `DASHBOARD_KEY`. The account owner pastes the real values in the AWS console. Redeploy afterwards so running
  functions pick them up.
- Tear down after the hackathon: delete the stack, then empty and delete the two buckets and the secret.

## Status (3 Nov 2026, day 9)

- **Photo step live:** SAM 3.1 finds the paper in a driver's photo, code straightens it, Muse reads the clean page.
  Probed live on the synthetic car-seat photo: SAM 5.9 s, paper at 38% of the frame, straightened by 7.5 degrees,
  Muse 12.5 s at 0.98 confidence. Scans skip the call.
- Submission pack written (`SUBMISSION.md`); repository prepared.
- **Live run, 3 Nov 23:00 IST, from a phone on WhatsApp:** the tilted car-seat photo was found by SAM 3.1 at 38% of
  the frame and straightened by 7.5 degrees in 5.0 s, read by Muse in 12.5 s at 0.99, accepted with the tyre advisory,
  and answered with the Vehicle care link, 22 s from photo to reply; the wrong-vehicle bill was rejected
  (VEHICLE_MISMATCH) in 12 s and the future-dated memo (FUTURE_DATE, NO_GSTIN) in 11 s, both with the SAM call skipped
  because the paper fills the frame. Every reply delivered and read; the dashboard updated live.

## Status (2 Nov 2026, day 8)

- **Dashboard live:** `https://cyxor2eapkupuigulbufrif3py0tsvei.lambda-url.ap-south-1.on.aws/` (access code shared
  separately). Checked live: page and assets served with the hardening headers, state refused without the code,
  ETag 304 on repeat polls, traversal refused.
- **Train half wired:** the three demo drivers are enrolled on the training platform (ten modules each, in their
  language); an accepting reply now ends with the driver's module link.
- **Reply pacing** in place after the 1 Nov burst (six replies refused with HTTP 400 when twelve files arrived at once).
- Every decision now records `decided_at` and `read_ms`, so the dashboard can show photo-to-reply seconds.

## Status (1 Nov 2026, day 7)

- **Live end to end on WhatsApp:** consent, YES, then three synthetic bills: the future-dated cash memo rejected
  (FUTURE_DATE and NO_GSTIN), the clean invoice accepted with a tyre advisory, the wrong-vehicle bill rejected.
  Photo to reply took 8 to 12 seconds, model read 6 to 8 seconds. Demo store cleaned afterwards.
- Delivery receipts (`statuses`) are parsed and logged; a refused send logs Meta's error code and title.

## Status (27 Oct 2026, day 2)

- **AWS is live** in ap-south-1. Webhook: `https://onmse24geq3iutkeoard2tg5ue0gtzdl.lambda-url.ap-south-1.on.aws/wa/inbound`.
  It refuses unsigned calls and wrong handshake tokens (checked 27 Oct).
- **Consent wording signed off** 27 Oct, with the STOP withdrawal line.
- **Waiting on:**
  - the real values in the secret
  - the webhook registered in the Meta developer console
  - test phones in `demo/registry.live.json`

## Status (26 Oct 2026, day 1)

**Built and tested locally:**

- intake
- signature check
- registry
- consent
- storage layout
- queue
- model client and stand-in
- rules
- records
- replies in 3 languages
- worker
- web and Lambda entry points

**Next:**

1. **AWS, in ap-south-1:**
   - an S3 bucket with a KMS key
   - an SQS queue and a dead-letter queue
   - a DynamoDB table
   - two Lambdas: the webhook behind a function URL, and the worker triggered by SQS
2. **Dashboard builder:** records into the encrypted bundle, then an Amplify deploy for a separate demo dashboard with the fictional client.
3. **Inputs needed:**
   - the Meta Model API details and the WhatsApp test number details, into Secrets Manager
   - sign-off on the consent wording
   - a native speaker's check of the Hindi and Telugu replies
4. **Demo pack:** a set of synthetic documents that shows each rule, plus a timed run from photo to dashboard (target: under 2 minutes).
