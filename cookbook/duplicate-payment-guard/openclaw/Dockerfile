# Derived OpenClaw image that bakes the kiff-guard-demo plugin into the
# image's discovered extensions directory (/app/dist/extensions/<id>).
#
# Why bake instead of mount: the running gateway discovers plugins by
# scanning /app/dist/extensions/*. A bind-mount over /app/extensions
# shadows the bundled extensions; a config load-path is not scanned by
# the packaged runtime. Copying the plugin into the discovered dir at
# build time is the supported shape for a packaged image, and building
# as root lets us create the node_modules/openclaw peer link that an
# external plugin needs to resolve `openclaw/plugin-sdk/*`.
#
# Build context = the recipe root (so COPY can reach openclaw-plugin/,
# openclaw/, and vendor/).
#
# Pinned, NOT floating `:latest`. The gateway's connect policy is
# version-sensitive: the device-less "trusted backend over loopback"
# handshake this recipe uses (driver/ocgw.mjs: client.id "gateway-client",
# mode "backend", operator role + shared token) is admitted by
# shouldSkipLocalBackendSelfPairing(), which is gated on the gateway
# seeing a loopback remote (the `--network host` topology in
# start-openclaw.sh provides this). A floating `:latest` silently rolled
# this path stricter and the gated scenario started failing the connect
# with "device identity required" (NOT_PAIRED) — pure upstream drift, not
# a logic bug in ocgw.mjs. Pinning freezes a build empirically verified to
# honor the backend path (full operator scopes returned on loopback, no
# device identity required). Re-pin deliberately after testing a newer tag.
#
# 2026.6.6, by immutable multi-arch (amd64+arm64) index digest.
FROM ghcr.io/openclaw/openclaw:2026.6.6@sha256:4826ca6157377e93463786d5c16852e34eede9f4bd4be55e3773cdc509762857

USER root

# The id here MUST match openclaw.plugin.json "id" and the config's
# plugins.allow / plugins.entries keys.
ENV EXT=/app/dist/extensions/kiff-guard-demo

RUN mkdir -p "$EXT/node_modules/@kiff"

# 1. The compiled plugin (tsc output) + a minimal package.json that
#    points the runtime at the entrypoint. We deliberately ship a
#    dependency-free package.json so the runtime's cold dependencyStatus
#    check stays green; the imports resolve through the node_modules we
#    bake in below.
COPY openclaw-plugin/dist "$EXT/dist"
COPY openclaw/extension.package.json "$EXT/package.json"
COPY openclaw/openclaw.plugin.json "$EXT/openclaw.plugin.json"

# 2. The vendored kiff-guard SDK (self-contained: relative imports only,
#    no openclaw runtime dependency) — resolves `@kiff/kiff-guard` and
#    `@kiff/kiff-guard/adapters/openclaw`.
COPY vendor/kiff-guard "$EXT/node_modules/@kiff/kiff-guard"

# 3. The peer link: an external plugin importing `openclaw/plugin-sdk/*`
#    resolves it against the host package at /app.
RUN ln -sf /app "$EXT/node_modules/openclaw" \
 && chown -R node:node "$EXT"

USER node
