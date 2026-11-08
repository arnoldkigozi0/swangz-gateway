"""Offline release trust. Empty until Arnold provisions reviewed production public keys.

At most two slots: {key_id: (4096-bit modulus, 65537)}. Never load keys from
the gateway, environment, application state or a downloaded manifest. Test keys
are patched by tests only; none ship in the client.
"""

KEYS = {}
ENABLED = False  # G8 release gate; a latest-client hint cannot enable updates.
CHANNEL = "pilot"
