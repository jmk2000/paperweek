# Official implementation references

References checked while building this source prototype on 5 September 2026. Code is pinned to LVGL 9.3.0 rather than following its development branch. These sources establish API/build behaviour; they do not imply this project's native app or live sign-in has been tested.

## Google

Python quickstart: Cloud project, Calendar API enablement, Desktop app client, local browser OAuth.
`https://developers.google.com/workspace/calendar/api/quickstart/python`

Calendar OAuth scopes: events.readonly and calendar.calendarlist.readonly.
`https://developers.google.com/workspace/calendar/api/auth`

Events list: pagination, recurrence expansion, time-zone-aware query bounds, cancellation and access rules.
`https://developers.google.com/workspace/calendar/api/v3/reference/events/list`

OAuth consent and Internal/External audience configuration.
`https://developers.google.com/workspace/guides/configure-oauth-consent`

Desktop/installed-app OAuth, including loopback redirects.
`https://developers.google.com/identity/protocols/oauth2/native-app`

Refresh-token expiration, including the seven-day External/Testing rule.
`https://developers.google.com/identity/protocols/oauth2#expiration`

Google auth-oauthlib flow reference.
`https://google-auth-oauthlib.readthedocs.io/en/latest/reference/google_auth_oauthlib.flow.html`

## LVGL

Pinned release.
`https://github.com/lvgl/lvgl/releases/tag/v9.3.0`

Pinned desktop build configuration (LV_BUILD_CONF_PATH; CONFIG_LV_BUILD_EXAMPLES/DEMOS flags).
`https://github.com/lvgl/lvgl/blob/v9.3.0/env_support/cmake/os_desktop.cmake`

Pinned label header, including LV_LABEL_LONG_MODE_DOTS.
`https://github.com/lvgl/lvgl/blob/v9.3.0/src/widgets/label/lv_label.h`

Desktop simulator overview.
`https://lvgl.io/docs/open/9.2/integration/ide/pc-simulator`

SDL integration overview. The prototype uses its own small SDL adapter, not LVGL's built-in SDL driver.
`https://lvgl.io/docs/open/9.5/integration/pc/sdl`

## Homebrew

SDL2 compatibility interface, currently also known as sdl2.
`https://formulae.brew.sh/formula/sdl2-compat`

Python 3.12 formula.
`https://formulae.brew.sh/formula/python@3.12`

## Physical sizing

The prototype's configured panel target is 1600 × 1200 pixels across approximately 270.4 × 202.8 mm, as discussed for the proposed panel. The density calculation is `1600 / (270.4 / 25.4) = 150.296 ppi`. Physical dimensions must still be checked against the exact hardware SKU before cutting a frame or mount. The representative RGB palette is not manufacturer calibration data.
