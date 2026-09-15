# Installation

## Requirements

- Home Assistant **2026.8.0** or newer
- An NHS Give Blood account (the same one you use in the app)

The [`nhs-give-blood`](https://github.com/KRoperUK/give-blood-py) library is installed automatically by
Home Assistant from `manifest.json`.

## Install

=== "HACS (recommended)"

    1. Open **HACS**
    2. Three-dot menu → **Custom repositories**
    3. Repository: `https://github.com/KRoperUK/give-blood-hass`, Category: **Integration**
    4. **Add**, then find **NHS Give Blood** and install it
    5. Restart Home Assistant

=== "Manual"

    1. Download the latest `nhs_give_blood.zip` from the
       [releases page](https://github.com/KRoperUK/give-blood-hass/releases)
    2. Extract it into `config/custom_components/nhs_give_blood/`
    3. Restart Home Assistant

    The zip's contents sit at the archive root, so `manifest.json` should end up directly inside
    `nhs_give_blood/`.

## Set up

**Settings → Devices & services → Add integration → NHS Give Blood**

Enter the email address and password you use for the NHS Give Blood app.

!!! info "Why the password is stored"

    Both credentials are stored in your Home Assistant config entry. The password is kept deliberately:
    NHSBT rotates refresh tokens, and when a stored one is rejected the integration logs in again rather
    than going unavailable until you notice. Without it, every rotation would need a manual
    reauthentication.

    Config entry data lives in `.storage/core.config_entries`, which is unencrypted. Anyone with
    filesystem access to your Home Assistant instance can read it — the same is true of every
    cloud-polling integration.

## Multiple accounts

Add the integration once per donor account. Accounts are keyed by donor ID rather than email address, so
changing your email in the app does not create a duplicate entry.

Each account produces its own device and its own set of entities. Re-authenticating an existing entry
with credentials for a *different* account is refused, because it would silently repoint every existing
entity at another person.

## Verify it worked

After setup you should have one device named **NHS Give Blood** with around 25 entities. Check:

```yaml
# Developer tools → Template
{{ states('sensor.nhs_give_blood_blood_group') }}
{{ states('sensor.nhs_give_blood_donation_credits') }}
{{ state_attr('sensor.nhs_give_blood_next_appointment', 'venue') }}
```

If everything is `unavailable`, see [Troubleshooting](troubleshooting.md).

## Uninstall

Deleting the config entry signs out of the API (invalidating the stored refresh token) and removes all
entities. The password is removed with the entry.
