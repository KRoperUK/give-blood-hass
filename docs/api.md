# The API

This integration is a thin Home Assistant layer over the
[`nhs-give-blood`](https://github.com/KRoperUK/give-blood-py) library, which talks to the private API
behind the NHS Give Blood mobile app.

!!! warning "Unofficial and unsupported"

    NHS Blood and Transplant publishes no contract for these endpoints, does not support this client, and
    may change or break it without notice.

## Where it came from

The endpoints, payload shapes and authentication flow were recovered from the public Android app
(`com.savant.mobile.nhs.nhsgiveblood` 4.9.1) and then verified against the live API.

The app is React Native with Hermes bytecode, so the logic is not in the DEX files — it is in
`assets/index.android.bundle`, compiled JavaScript. Decompiling that recovers the route table and the HTTP
client configuration as ordinary object literals.

**[Full API reference in the library repository →](https://github.com/KRoperUK/give-blood-py/blob/main/docs/api-reference.md)**

That document covers every endpoint, the authentication flow, error envelope shapes, and how to reproduce
the analysis.

## What this integration reads

| Endpoint | Feeds |
|---|---|
| `POST /api/auth/v2/login` | Sign-in; also returns the full account payload |
| `POST /api/auth/refresh` | Token rotation |
| `GET /api/account/v2/details` | Most sensors |
| `GET /api/appointments/future` | Appointments, calendar |
| `GET /api/account/donation-history` | Last donation, donations recorded |
| `GET /api/messages` | Donor messages |
| `GET /api/features` | (fetched; not currently surfaced) |
| `GET /api/features/failover` | Booking system problem |

Write endpoints (`book`, `replace`, `DELETE`) exist in the API and in the library.
**This integration calls none of them** — see [Design decisions](design.md#why-read-only).

## Wire quirks worth knowing

These bite anyone reading the raw API. The library normalises all of them, so you should never see them —
but they explain some of the integration's behaviour.

| Quirk | Detail |
|---|---|
| `0001-01-01T00:00:00` is null | .NET's `DateTime.MinValue`, used instead of `null` |
| Datetimes are naive but not UTC | They are venue-local wall-clock time; the library localises to `Europe/London` |
| A session date is never a start time | Its time component is always midnight; the appointment's own `time` field supplies the clock |
| Two clock formats | Appointments use `THHMM`, session periods use bare `HHMM` |
| `freeSlots: "-1"` is not zero | A string, and -1 means "not disclosed" |
| Two procedure vocabularies | An appointment's platelet code is `PLT`; the donor's registered code for the same thing is `PL1` |
| Donation history is truncated | `hasFurtherDonations` says so; the list length is a lower bound |
| Messages arrive for every blood group | Filtering is the client's job |
| Donation `type` codes are undocumented | A/B/L/R observed; NHSBT publishes no mapping, so they are passed through verbatim |

## Using the library directly

```bash
pip install nhs-give-blood
```

```python
import aiohttp
from nhs_give_blood import GiveBloodClient

async with aiohttp.ClientSession() as session:
    client = GiveBloodClient(session, username="you@example.com", password="…")
    snapshot = await client.async_get_snapshot()
    print(snapshot.account.blood_group, snapshot.account.donation_credit)
```

There is also a CLI, with every write gated behind `--yes`:

```bash
give-blood whoami
give-blood appointments
give-blood venues "SW1A 1AA"
give-blood cancel APPT123 --yes
```

## Rate limiting and etiquette

This is a public health service's infrastructure. Both projects are built to be light on it:

- 30-minute default poll interval, with a 5-minute floor
- Automatic backoff to 4 hours on sustained failure
- One aggregate read per poll rather than a request per sensor
- `Retry-After` honoured; exponential backoff with jitter, so many Home Assistant instances do not retry
  in lockstep
- Logins are never retried automatically — a retried login is a second password attempt against an
  account-lockout policy
