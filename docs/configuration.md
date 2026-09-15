# Configuration

**Settings → Devices & services → NHS Give Blood → Configure**

| Option | Default | Range |
|---|---|---|
| Update interval | 30 minutes | 5–1440 minutes |
| Fetch donation history | on | — |

## Update interval

Donor data changes on the order of days: eligibility dates move after a donation, appointments when you
book one. The default of 30 minutes already makes a booking made in the app appear promptly.

Polling faster mostly asks a public health service for data that cannot have changed. There is no
benefit and it is not neighbourly. The floor of 5 minutes exists to stop an accidental
one-minute setting.

### Automatic backoff

On sustained failure the interval doubles, up to a ceiling of **4 hours**, after three consecutive
failed polls. NHSBT maintenance windows last hours; hammering through one achieves nothing.

Once a poll succeeds, your configured interval is restored immediately.

Backoff does **not** apply to authentication failures. A rejected credential needs you, not patience, so
Home Assistant opens a reauthentication prompt instead.

## Fetch donation history

Controls whether `/api/account/donation-history` is called on each update. It powers:

- `sensor.nhs_give_blood_last_donation`
- `sensor.nhs_give_blood_donations_recorded`

Turning it off makes each update one request lighter and leaves both sensors unavailable.

## Changing options

Options changes reload the integration. Token refreshes do not — the integration distinguishes the two,
because reloading on a token write would produce an endless loop.

## YAML configuration

Not supported, and not planned. This integration is config-flow only, which is where Home Assistant has
been heading for years and is a requirement for the quality scale it targets.

## Logging

```yaml
logger:
  default: info
  logs:
    # The integration
    custom_components.nhs_give_blood: debug
    # The underlying library — HTTP requests, token refreshes, retries
    nhs_give_blood: debug
```

Debug logging never records credentials or tokens: the library's `TokenBundle` has a redacted `repr`,
and API error summaries deliberately read only `errorCode` and `errorMessage`, never the
`attemptedValue` field that echoes back whatever was sent.
