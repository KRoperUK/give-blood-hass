# Privacy

Every account endpoint in this API returns your **name, address, phone number, date of birth and donor
ID**. The integration only needs a fraction of that, so it is built so the rest does not surface where you
would not expect it.

## What is stored

| Where | What |
|---|---|
| Config entry (`.storage/core.config_entries`) | Email address, password, access and refresh tokens |
| Entity states and attributes | Blood group, credits, awards, appointment times, venue names and addresses |
| Recorder database | The above, as history |

Config entry storage is **unencrypted**. Anyone with filesystem access to your Home Assistant instance can
read it — the same is true of every cloud-polling integration.

## What is never published

Not exposed as a state or attribute on any entity:

- your name
- your home address or postcode
- your phone number
- your date of birth
- your donor ID
- your email address

Venue addresses *are* exposed on appointment entities and calendar events, because locating your
appointment is the point of them.

## The device is not named after you

The device is called **NHS Give Blood**, not your name. Device names appear in logs, diagnostics
downloads, screenshots and shared dashboards, and there is no reason for a donor's name to travel through
all of those.

## Diagnostics

Home Assistant's diagnostics download gets pasted into public GitHub issues. This integration's
diagnostics are built from an **allowlist** of explicitly non-identifying fields, not by dumping the
payload and redacting known-bad keys.

That direction matters. A redaction list fails open the moment NHSBT adds a field — and this is a
reverse-engineered API, so it will. An allowlist fails safe: a new field is absent until someone decides
it is safe to include.

Concretely:

- **Credentials appear as booleans only** — `has_username`, `has_password`, `has_stored_tokens`. No value
  at any level of detail.
- **Your donor ID appears as a 12-character SHA-256 prefix**, so two reports can be correlated as the same
  account without publishing the identifier.
- **Venues are reduced to capability flags** (`venue_is_donor_centre`, which procedures are supported).
  Venue name plus appointment dates is enough to place a person.
- **Contact details are counted, not listed** — `address_count`, `telephone_count`, `email_count`.
- **Unmodelled API fields are named, not valued** — the key names are the useful signal when NHSBT changes
  something; the values are not.

Two tests enforce this. One walks the diagnostics output looking for the synthetic values that stand in
for real PII. The other runs against a **real account** and searches for the actual values pulled from the
live payload, plus anything merely shaped like an email address or postcode.

It is still worth reading diagnostics before attaching them to a public issue.

## Logs

Debug logging records HTTP method, path, status and retry decisions — never credentials.

- The library's `TokenBundle` has a redacted `repr`, so a token cannot reach a log line through an
  incidental `%s`.
- API error summaries read only `errorCode` and `errorMessage`. The API's `attemptedValue` field echoes
  back whatever the caller sent, which on an auth endpoint can be a password, so it is never included.

## Network

The integration talks to `my.blood.co.uk` and nothing else. No telemetry, no analytics, no third-party
services.

The app itself additionally talks to Azure Application Insights, Firebase and Google Maps. None of that is
reimplemented here.

## Removing your data

Deleting the config entry:

1. signs out of the API, invalidating the stored refresh token server-side
2. removes the stored email address, password and tokens
3. removes all entities and the device

Recorder history survives entity removal. To purge it:

```yaml
action: recorder.purge_entities
target:
  entity_id:
    - sensor.nhs_give_blood_next_appointment
data:
  keep_days: 0
```

## Repository hygiene

Because this API's payloads are so saturated with PII, the repositories themselves are guarded against
committing it. Four layers run on every commit and in CI:

| Layer | Catches |
|---|---|
| `scripts/check_pii.py` | Emails, UK postcodes, UK phone numbers, JWTs, Bearer tokens, NHSBT donor and donation IDs, credential assignments |
| `detect-secrets` | High-entropy secrets, against an audited baseline |
| `bandit` | Insecure code patterns |
| Repository tests | Real values in test fixtures, and PII escaping into diagnostics |

Test fixtures use values drawn from ranges reserved by standard, so they can never collide with a real
person: RFC 6761 `.invalid` domains, Royal Mail's `ZZ99` outcode, and Ofcom's `07700 900xxx` drama range.
