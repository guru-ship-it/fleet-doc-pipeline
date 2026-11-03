# Verify and Train on WhatsApp: fleet documents read, checked and answered in seconds

**Meta Global AI Developer Hackathon, startup track. Compliance Desk AI, Hyderabad.**

A cab driver photographs a service bill and sends it on WhatsApp. Within seconds the bill is stored encrypted in
Mumbai, the paper is found in the photo by SAM 3.1, the page is read by Muse Spark with a strict JSON schema,
plain code checks it against the fleet's rules, the cab's record updates, the driver gets an answer in their own
language with the exact problem when there is one, and a link to a short training module in that language goes out
with an accepted bill. The fleet manager's dashboard reads the same records live.

The public demo uses a fictional client and synthetic drivers, cabs and documents only.

## The problem

Corporate cab fleets in India run on paper: service bills, insurance, PUC, permits, fitness certificates, police
verification. Transport teams collect them on WhatsApp and check them by hand, weeks later, if at all. In one manual
audit of a real fleet's bills we found a future-dated memo, a bill for a different vehicle, a bill in a bank's name,
a spares-only bill passed off as a service, and an invoice filed under the wrong cab. Each is a safety or fraud gap
that a human reviewer missed. The drivers who send these documents read Telugu or Hindi better than English, and
they are trained, when they are trained at all, with a slide deck in a classroom.

## What the agent does

This is a multimodal document agent with its verification layer in code, built the way the hackathon's
"verifiable agents" session taught it:

- **The model reads; code decides.** Muse Spark returns structured JSON (document type, vehicle number, date,
  odometer, GSTIN, work done, advisories, a one-line summary, confidence). Deterministic checks then decide the
  outcome: wrong vehicle, future date, missing GSTIN, duplicate file or invoice across cabs, bank-name bill, partial
  proof, expired paper, odometer going backwards. The model never decides whether a bill is acceptable.
- **The checks sit at the moment the agent would move on, not as a tool it can skip.** No record is written and
  no reply is sent until the rules have run.
- **A refusal goes back with the problem.** A rejected bill produces a reply such as "This document shows a
  different vehicle number (TS-09-XY-7730). Please resend the document for TS-09-XY-4521", in English, Hindi or
  Telugu.
- **Evidence is requested and tracked.** A workshop advisory on tyres, brakes, clutch, steering, suspension or the
  fuel system opens a safety action on the cab. It stays open until a later bill's work lines show the fix, which
  closes it. Spares bills and receipts are kept but marked "more proof needed" until the job card or final invoice
  arrives.
- **Human in the loop.** The dashboard is the fleet manager's review surface: every document, what the model
  read, every flag with its reason, and the open actions. Medical certificates never reach a model; they go to a
  restricted prefix for a person to review.
- **A check the model cannot skip.** Meta's Model API is hosted outside India. Indian data protection law keeps
  personal data in India, so the worker refuses to send any document from a driver not marked synthetic to a model
  hosted outside India. Real fleets use a model hosted in Mumbai behind the same interface.
- **Every model call and every decision is logged** with hashed ids, latency, tokens, document type and
  confidence, and never with a phone number, a name or document text.

## How Meta's tooling is used

| Meta product | Role in the pipeline |
|---|---|
| **Muse Spark 1.3** (Meta Model API, vision, JSON-schema structured output) | Reads each page: fourteen fields plus a one-sentence summary and a confidence score, at temperature 0 |
| **SAM 3.1** (Meta Model API, Responses API) | Finds the paper in a driver's photo. Code crops to the box it returns, measures the text-line skew, straightens and trims the page before Muse reads it. Skipped for scans whose paper already fills the frame |
| **WhatsApp Cloud API** | The whole driver interface: inbound media, consent, replies, delivery receipts. No app to install |

SAM finds and Muse reads; neither decides. On the synthetic car-seat photo in `demo/synthetic/`, SAM returns the
paper at 38% of the frame in about five seconds, code straightens it by the 7.5 degree tilt, and Muse reads the
clean page with 0.98 confidence.

## How it is built

One CloudFormation stack in ap-south-1 (Mumbai):

```
WhatsApp Cloud API -> webhook (Lambda, signature check, consent gate, pacing)
                   -> S3 with KMS (fleet/{cab}/{month}/{sha256}; medical under restricted/)
                   -> SQS (job carries a hashed sender id, never a phone number) -> worker (Lambda)
                        photo step: SAM 3.1 finds, code crops and straightens
                        read: Muse Spark, strict JSON schema
                        decide: rules.py
                        record: DynamoDB (cab profile, document log, open actions, send slots)
                        reply: WhatsApp, in the driver's language, paced per driver, with the Train link
                   -> dashboard (read-only Lambda, access code, ETag polling, live updates)
```

- `pipeline/rules.py` is the verification layer; each rule has a test. `pipeline/photo.py` is the SAM step.
  `pipeline/model.py` holds the Muse client behind an `extract()` interface so the model can be swapped.
- Replies to one driver are spaced three seconds apart through an atomic per-recipient slot in DynamoDB, because
  a driver who sends ten bills at once would otherwise lose most of the answers to WhatsApp's pair rate limit.
- Delivery receipts are parsed: "accepted by the API" is logged as exactly that, never as delivered.
- Consent is one message; STOP withdraws it and nothing more is stored or read, including files already queued.
- 62 tests run offline against stand-ins; no network or AWS is needed to exercise the whole flow
  (`python demo/rehearse.py`, then `python dashboard/serve_local.py`).

## The Train half

Each driver holds a learner token on D Advaya FM naipuNya's training platform, where ten short driver modules run
on a phone in Telugu, Hindi, Kannada, Marathi, Tamil and English. A reply that accepts a bill ends with the driver's
own link to the next module; a workshop advisory points at vehicle care first. The dashboard shows which module
went out, never the link.

## Demo

- Dashboard: the link and its access code are in the submission form. The page is public; the state behind it
  needs the code.
- Video: linked in the submission form. It shows the three synthetic bills sent from a phone, the replies, and the
  dashboard updating live.
- The webhook, worker and dashboard run live in ap-south-1 for the judging period.

## Status and what is next

Built in nine days by one founder with AI-assisted coding. Live end to end on WhatsApp since 1 November. Next:
a Mumbai-hosted model for real fleets, erasure on request, and the remaining document types' rules (permit and
fitness are read but have fewer checks than service bills).

## Team

Compliance Desk AI, Hyderabad. Contact: guru@compliancedesk.ai.
